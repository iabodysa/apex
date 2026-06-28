# Copyright (c) 2026, AFMCO and contributors
"""Resilience tests for the Salis accrual engines.

Covers two regressions in the per-row accrual loops:

* T-670 — ``accrue_fuel_consumption``'s Done-Fuel-Request loop re-queries the
  ``ledgered=0`` set in a ``while True``. A request that deterministically fails
  to ledger stays ``ledgered=0``; combined with the old whole-transaction
  ``frappe.db.rollback()`` (which also discarded the good rows' ``ledgered=1``
  flag) this spun forever, pinning CPU and zeroing the day's accrual. The loop
  must now RETURN: good rows are ledgered and stay ledgered, the bad row is
  attempted once, logged, and skipped.

* T-671 — a single per-row failure in a daily/weekly accrual loop used a bare
  ``frappe.db.rollback()``, which in one request transaction discarded every
  sibling row already inserted in the same job. A failing row must now roll back
  ONLY itself (savepoint isolation); its siblings persist.

Failures are injected by patching the engine's own insert helper to raise for one
designated source — a deterministic ledger-time failure that exercises the
savepoint + termination paths without depending on which field validation fires.
"""

import signal

import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch

import apex_habitat.salis.fuel_engine as fuel_engine
import apex_habitat.salis.rental_engine as rental_engine
from apex_habitat.salis.fuel_engine import accrue_fuel_consumption
from apex_habitat.salis.rental_engine import daily_rental_accrual


def _run_bounded(fn, seconds=30):
    """Run ``fn`` with a hard wall-clock deadline and fail if it overruns.

    A non-terminating loop (the T-670 bug) would otherwise hang the whole test
    run; a SIGALRM deadline turns that hang into a fast, deterministic failure.
    The call runs on the *main* thread on purpose: ``frappe.local`` is a
    thread-local, so a worker thread would have no bound site/DB connection and
    the engine would raise ``object is not bound`` before reaching the loop under
    test (it would also not see this test's uncommitted setup rows). SIGALRM only
    arms on the main thread, which is where the test runner already is.
    """

    def _on_timeout(signum, frame):
        raise AssertionError(
            f"{getattr(fn, '__name__', fn)} did not terminate within {seconds}s "
            "- the accrual loop is not provably terminating (T-670)."
        )

    previous = signal.signal(signal.SIGALRM, _on_timeout)
    signal.alarm(seconds)
    try:
        fn()
        return True
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


class TestFuelAccrualLoopResilience(FrappeTestCase):
    """T-670 + T-671 for ``accrue_fuel_consumption``'s Done-Fuel-Request loop."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.vehicle = frappe.db.get_value(
            "Salis Vehicle", {"plate_number": "ACCR RESIL 1"}, "name"
        )
        if not cls.vehicle:
            cls.vehicle = frappe.get_doc(
                {
                    "doctype": "Salis Vehicle",
                    "plate_number": "ACCR RESIL 1",
                    "status": "Active",
                }
            ).insert(ignore_permissions=True).name

    def _make_done_request(self):
        """Create one submitted Done Fuel Request via the legal workflow path,
        falling back to direct save+submit on a site without the workflow seeded
        (mirrors the helper in ``test_salis_engines``)."""
        from frappe.model.workflow import apply_workflow, get_workflow_name
        from frappe.utils import today

        doc = frappe.get_doc(
            {
                "doctype": "Fuel Request",
                "vehicle": self.vehicle,
                "request_date": today(),
                "requested_litres": 5,
                "amount": 75,
                "status": "Pending",
            }
        )
        doc.insert(ignore_permissions=True)
        if get_workflow_name("Fuel Request") == "Fuel Request Workflow":
            if doc.requested_by == frappe.session.user:
                doc.db_set("requested_by", "Guest")  # segregation-of-duties gate
                doc.reload()
            apply_workflow(doc, "Approve")
            doc.reload()
            apply_workflow(doc, "Complete")
        else:
            doc.status = "Approved"
            doc.save(ignore_permissions=True)
            doc.status = "Done"
            doc.save(ignore_permissions=True)
            doc.submit()
        self.addCleanup(self._cleanup, doc.name)
        return doc.name

    def _cleanup(self, name):
        frappe.set_user("Administrator")
        frappe.db.delete(
            "Fuel Consumption Ledger",
            {"source_type": "Fuel Request", "source_name": name},
        )

    def test_failing_done_request_does_not_hang_or_discard_good_rows(self):
        # Two good requests + one that deterministically fails to ledger.
        good_a = self._make_done_request()
        good_b = self._make_done_request()
        bad = self._make_done_request()
        for n in (good_a, good_b, bad):
            frappe.db.delete(
                "Fuel Consumption Ledger",
                {"source_type": "Fuel Request", "source_name": n},
            )

        real_insert = fuel_engine._insert_ledger_row
        attempts = {"bad": 0}

        def _insert_or_fail(**kwargs):
            # Fail ledgering for the bad request only; everything else is real.
            if kwargs.get("source_name") == bad:
                attempts["bad"] += 1
                raise frappe.ValidationError("injected ledger failure")
            return real_insert(**kwargs)

        with patch.object(fuel_engine, "_insert_ledger_row", side_effect=_insert_or_fail):
            # _run_bounded turns the old infinite loop into a fast failure.
            ok = _run_bounded(accrue_fuel_consumption, seconds=30)
        self.assertTrue(ok, "accrue_fuel_consumption raised instead of returning")

        # the always-failing row is attempted ONCE then skipped, not spun on.
        self.assertEqual(
            attempts["bad"], 1,
            "Bad request must be attempted exactly once, then excluded from re-query "
            "(termination guard) - a >1 count means the loop re-attempts it.",
        )

        # both good siblings are ledgered and STAY ledgered (savepoint
        # isolation - the bad row's rollback must not discard them).
        for n in (good_a, good_b):
            rows = frappe.db.count(
                "Fuel Consumption Ledger",
                {"source_type": "Fuel Request", "source_name": n},
            )
            self.assertEqual(rows, 1, f"Good request {n} must be ledgered exactly once.")
            self.assertEqual(
                frappe.db.get_value("Fuel Request", n, "ledgered"), 1,
                f"Good request {n} must remain flagged ledgered after the bad row failed.",
            )

        # The bad row is left un-ledgered (its work rolled back), ready to retry
        # on a later run once its cause is fixed.
        self.assertEqual(
            frappe.db.count(
                "Fuel Consumption Ledger",
                {"source_type": "Fuel Request", "source_name": bad},
            ),
            0,
            "Failed request must not leave a partial ledger row.",
        )
        self.assertEqual(
            frappe.db.get_value("Fuel Request", bad, "ledgered"), 0,
            "Failed request must stay ledgered=0 so a later run can retry it.",
        )

    def test_good_rows_survive_when_first_row_in_batch_fails(self):
        # ordering variant: the FAILING row is processed first (order_by
        # modified asc -> created earliest). The bare-rollback bug would have
        # discarded the later good rows; savepoint isolation keeps them.
        bad = self._make_done_request()
        good = self._make_done_request()
        for n in (bad, good):
            frappe.db.delete(
                "Fuel Consumption Ledger",
                {"source_type": "Fuel Request", "source_name": n},
            )

        real_insert = fuel_engine._insert_ledger_row

        def _insert_or_fail(**kwargs):
            if kwargs.get("source_name") == bad:
                raise frappe.ValidationError("injected ledger failure")
            return real_insert(**kwargs)

        with patch.object(fuel_engine, "_insert_ledger_row", side_effect=_insert_or_fail):
            ok = _run_bounded(accrue_fuel_consumption, seconds=30)
        self.assertTrue(ok)

        self.assertEqual(
            frappe.db.count(
                "Fuel Consumption Ledger",
                {"source_type": "Fuel Request", "source_name": good},
            ),
            1,
            "A good row after a failing row in the same batch must persist.",
        )


class TestRentalAccrualLoopResilience(FrappeTestCase):
    """T-671 for ``daily_rental_accrual``: a failing vehicle must not discard the
    accrual memos already written for its siblings in the same run."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.office = frappe.db.get_value(
            "Rental Office", {"office_name": "Resil Rental Office"}, "name"
        )
        if not cls.office:
            cls.office = frappe.get_doc(
                {
                    "doctype": "Rental Office",
                    "office_name": "Resil Rental Office",
                    "status": "Active",
                }
            ).insert(ignore_permissions=True).name
        cls.good_vehicle = cls._rented_vehicle("RESIL RENT GOOD")
        cls.bad_vehicle = cls._rented_vehicle("RESIL RENT BAD")

    @classmethod
    def _rented_vehicle(cls, plate):
        name = frappe.db.get_value("Salis Vehicle", {"plate_number": plate}, "name")
        if not name:
            name = frappe.get_doc(
                {
                    "doctype": "Salis Vehicle",
                    "plate_number": plate,
                    "ownership": "Rented",
                    "status": "Active",
                }
            ).insert(ignore_permissions=True).name
        # An open Receipt makes the vehicle in-service so the engine accrues it.
        if not frappe.db.exists(
            "Rental Vehicle Movement",
            {"vehicle": name, "movement_type": "Receipt", "docstatus": 1},
        ):
            m = frappe.get_doc(
                {
                    "doctype": "Rental Vehicle Movement",
                    "movement_type": "Receipt",
                    "vehicle": name,
                    "rental_office": cls.office,
                    "movement_date": frappe.utils.today(),
                    "daily_rate": 100,
                }
            ).insert(ignore_permissions=True)
            m.submit()
        return name

    def test_one_failing_vehicle_does_not_discard_sibling_accruals(self):
        from frappe.utils import today

        posting = today()
        for v in (self.good_vehicle, self.bad_vehicle):
            frappe.db.delete(
                "Rental Accrual Ledger", {"vehicle": v, "accrual_date": posting}
            )

        # frappe.get_doc is the engine's insert path; fail it for the bad vehicle
        # only (a deterministic mid-loop failure), pass everything else through.
        # Pass through with the ORIGINAL args/kwargs untouched: the engine's
        # except-branch calls frappe.log_error, which itself calls get_doc with
        # keyword-only args, so a forced positional (arg=None) would raise
        # "First non keyword argument must be a string or dict" and mask the test.
        real_get_doc = rental_engine.frappe.get_doc

        def _get_doc_or_fail(*args, **kwargs):
            first = args[0] if args else None
            if (
                isinstance(first, dict)
                and first.get("doctype") == "Rental Accrual Ledger"
                and first.get("vehicle") == self.bad_vehicle
            ):
                raise frappe.ValidationError("injected accrual failure")
            return real_get_doc(*args, **kwargs)

        with patch.object(rental_engine.frappe, "get_doc", side_effect=_get_doc_or_fail):
            ok = _run_bounded(daily_rental_accrual, seconds=30)
        self.assertTrue(ok, "daily_rental_accrual raised instead of returning")

        self.assertEqual(
            frappe.db.count(
                "Rental Accrual Ledger",
                {"vehicle": self.good_vehicle, "accrual_date": posting},
            ),
            1,
            "Good vehicle's accrual memo must survive a sibling vehicle's failure.",
        )
        self.assertEqual(
            frappe.db.count(
                "Rental Accrual Ledger",
                {"vehicle": self.bad_vehicle, "accrual_date": posting},
            ),
            0,
            "Failed vehicle must not leave a partial accrual memo.",
        )
