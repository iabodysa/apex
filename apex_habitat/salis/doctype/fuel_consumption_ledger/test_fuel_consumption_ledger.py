# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Fuel Consumption Ledger — focused on the reversal path.

When a ledgered fuel source is corrected — a Done Fuel Request is cancelled, or a
Fuel Daily Log is deleted — its consumption must be netted out of the Fuel
Consumption Ledger by a negative mirror row whose ``reversal_of`` points at the
original. The fuel ledger carries no ``is_cancelled`` flag, so this mirrors the
Habitat Accommodation Ledger idiom (``utility_bill_entry.before_cancel``): only an
ORIGINAL row is ever negated, and a row that already has a reversal is skipped.

These tests prove: the reversal nets litres+amount to zero, sets ``reversal_of``,
and is idempotent (no double reversal on a second call / cancel).
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, today

from apex_habitat.salis.fuel_engine import accrue_fuel_consumption, reverse_fuel_ledger

LEDGER = "Fuel Consumption Ledger"

# [#t0h2nq]
test_ignore = [
    "Company",
    "Cost Center",
    "Employee",
    "Project",
    "Role",
    "Supplier",
    "User",
]


def _rows_for_original(original):
    """All ledger rows tied to one original: the original plus its reversal (the
    reversal carries ``reversal_of`` but no ``source_name``)."""
    names = [original] + frappe.get_all(LEDGER, filters={"reversal_of": original}, pluck="name")
    return frappe.get_all(LEDGER, filters={"name": ["in", names]}, fields=["litres", "amount"])


class TestFuelLedgerReversalDirect(FrappeTestCase):
    """Drive the engine helper directly against a hand-posted original row."""

    SOURCE = "FCL REV DIRECT 1"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.vehicle = frappe.db.get_value("Salis Vehicle", {"plate_number": "FCL REV 1"}, "name")
        if not cls.vehicle:
            cls.vehicle = frappe.get_doc(
                {"doctype": "Salis Vehicle", "plate_number": "FCL REV 1", "status": "Active"}
            ).insert(ignore_permissions=True).name

    def setUp(self):
        frappe.set_user("Administrator")
        self._purge()
        # [#ih09ij]
        frappe.get_doc(
            {
                "doctype": LEDGER,
                "vehicle": self.vehicle,
                "period_month": today()[:7],
                "litres": 40,
                "amount": 600,
                "source_type": "Fuel Daily Log",
                "source_doctype": "Fuel Daily Log",
                "source_name": self.SOURCE,
            }
        ).insert(ignore_permissions=True)

    def tearDown(self):
        frappe.set_user("Administrator")
        self._purge()

    def _purge(self):
        originals = frappe.get_all(
            LEDGER,
            filters={"source_type": "Fuel Daily Log", "source_name": self.SOURCE},
            pluck="name",
        )
        for orig in originals:
            frappe.db.delete(LEDGER, {"reversal_of": orig})
        frappe.db.delete(LEDGER, {"source_type": "Fuel Daily Log", "source_name": self.SOURCE})

    def test_reversal_nets_to_zero_and_links(self):
        original = frappe.get_value(
            LEDGER, {"source_type": "Fuel Daily Log", "source_name": self.SOURCE}, "name"
        )

        posted = reverse_fuel_ledger("Fuel Daily Log", self.SOURCE)
        self.assertEqual(posted, 1, "Exactly one reversal row must be posted.")

        # [#1wtbow]
        rev = frappe.get_all(
            LEDGER,
            filters={"reversal_of": original},
            fields=["litres", "amount", "vehicle", "period_month"],
        )
        self.assertEqual(len(rev), 1)
        self.assertEqual(flt(rev[0].litres), -40.0)
        self.assertEqual(flt(rev[0].amount), -600.0)
        self.assertEqual(rev[0].vehicle, self.vehicle)

        # [#e2ktzb]
        rows = _rows_for_original(original)
        self.assertEqual(flt(sum(flt(r.litres) for r in rows)), 0.0)
        self.assertEqual(flt(sum(flt(r.amount) for r in rows)), 0.0)

    def test_reversal_is_idempotent(self):
        first = reverse_fuel_ledger("Fuel Daily Log", self.SOURCE)
        second = reverse_fuel_ledger("Fuel Daily Log", self.SOURCE)
        self.assertEqual(first, 1, "First call posts one reversal.")
        self.assertEqual(second, 0, "Second call must NOT double-reverse.")

        original = frappe.get_value(
            LEDGER, {"source_type": "Fuel Daily Log", "source_name": self.SOURCE}, "name"
        )
        rows = _rows_for_original(original)
        self.assertEqual(len(rows), 2, "Exactly one original + one reversal must exist.")
        self.assertEqual(flt(sum(flt(r.litres) for r in rows)), 0.0)

    def test_unledgered_source_is_noop(self):
        posted = reverse_fuel_ledger("Fuel Daily Log", "NEVER LEDGERED XYZ")
        self.assertEqual(posted, 0, "A source that was never ledgered reverses nothing.")


class TestFuelDailyLogDeleteReverses(FrappeTestCase):
    """Deleting a ledgered Fuel Daily Log must net its consumption out via on_trash."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.vehicle = frappe.db.get_value("Salis Vehicle", {"plate_number": "FCL REV LOG 1"}, "name")
        if not cls.vehicle:
            cls.vehicle = frappe.get_doc(
                {"doctype": "Salis Vehicle", "plate_number": "FCL REV LOG 1", "status": "Active"}
            ).insert(ignore_permissions=True).name

    def test_delete_log_posts_reversal(self):
        frappe.set_user("Administrator")
        log = frappe.get_doc(
            {
                "doctype": "Fuel Daily Log",
                "vehicle": self.vehicle,
                "log_date": today(),
                "litres": 30,
                "amount": 450,
            }
        ).insert(ignore_permissions=True)
        log_name = log.name
        self.addCleanup(
            lambda: frappe.db.delete(LEDGER, {"source_type": "Fuel Daily Log", "source_name": log_name})
        )

        # [#dxreq2]
        accrue_fuel_consumption()
        original = frappe.get_value(
            LEDGER, {"source_type": "Fuel Daily Log", "source_name": log_name}, "name"
        )
        self.assertTrue(original, "Daily log must be ledgered by accrual before the delete test.")
        self.addCleanup(lambda: frappe.db.delete(LEDGER, {"reversal_of": original}))

        # [#6h15qh]
        frappe.delete_doc("Fuel Daily Log", log_name, force=True, ignore_permissions=True)

        rev = frappe.get_all(LEDGER, filters={"reversal_of": original}, fields=["litres", "amount"])
        self.assertEqual(len(rev), 1, "Deleting the log must post one reversal row.")
        self.assertEqual(flt(rev[0].litres), -30.0)
        self.assertEqual(flt(rev[0].amount), -450.0)

        rows = _rows_for_original(original)
        self.assertEqual(flt(sum(flt(r.litres) for r in rows)), 0.0)
        self.assertEqual(flt(sum(flt(r.amount) for r in rows)), 0.0)


class TestFuelRequestCancelReverses(FrappeTestCase):
    """Cancelling a Done Fuel Request that was already ledgered must net its
    consumption out of the Fuel Consumption Ledger (and not double-reverse)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.vehicle = frappe.db.get_value("Salis Vehicle", {"plate_number": "FCL REV REQ 1"}, "name")
        if not cls.vehicle:
            cls.vehicle = frappe.get_doc(
                {"doctype": "Salis Vehicle", "plate_number": "FCL REV REQ 1", "status": "Active"}
            ).insert(ignore_permissions=True).name

    def _make_done_request(self):
        """Walk a Standard request Pending -> Approved -> Done via the workflow when
        seeded, else the direct save+submit fallback (mirrors test_salis_engines)."""
        from frappe.model.workflow import apply_workflow, get_workflow_name

        doc = frappe.get_doc(
            {
                "doctype": "Fuel Request",
                "vehicle": self.vehicle,
                "request_date": today(),
                "requested_litres": 25,
                "amount": 375,
                "status": "Pending",
            }
        )
        doc.insert(ignore_permissions=True)
        if get_workflow_name("Fuel Request") == "Fuel Request Workflow":
            if doc.requested_by == frappe.session.user:
                doc.db_set("requested_by", "Guest")
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
        doc.reload()
        return doc

    def test_cancel_done_request_reverses_ledger(self):
        frappe.set_user("Administrator")
        doc = self._make_done_request()
        name = doc.name
        self.addCleanup(
            lambda: frappe.db.delete(LEDGER, {"source_type": "Fuel Request", "source_name": name})
        )

        frappe.db.delete(LEDGER, {"source_type": "Fuel Request", "source_name": name})
        accrue_fuel_consumption()
        original = frappe.get_value(
            LEDGER, {"source_type": "Fuel Request", "source_name": name}, "name"
        )
        self.assertTrue(original, "Done request must be ledgered before cancel.")
        self.addCleanup(lambda: frappe.db.delete(LEDGER, {"reversal_of": original}))

        # [#fwj30h]
        doc.reload()
        doc.cancel()

        rev = frappe.get_all(LEDGER, filters={"reversal_of": original}, fields=["litres", "amount"])
        self.assertEqual(len(rev), 1, "Cancelling a ledgered Done request must post one reversal.")
        self.assertEqual(flt(rev[0].litres), -25.0)
        self.assertEqual(flt(rev[0].amount), -375.0)

        rows = _rows_for_original(original)
        self.assertEqual(flt(sum(flt(r.litres) for r in rows)), 0.0)

        # [#8b8d5n]
        again = reverse_fuel_ledger("Fuel Request", name)
        self.assertEqual(again, 0, "A second reversal pass must not double-post.")
