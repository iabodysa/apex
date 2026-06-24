"""Masar worker boarding self-confirm ("I'm at the pickup") — T-323.

``confirm_boarding`` (salis/api/masar.py) lets a tokenized worker self-confirm
boarding: it resolves the worker from the personal Masar token (the SOLE
identity chokepoint — the client never supplies a worker id), finds that
worker's relevant today's Dispatch Trip from their OWN manifest membership, and
appends a ``method = Worker`` Trip Boarding Event onto the trip's draft Trip
Start Log — reusing the SAME child table + get-or-create log the driver QR scan
writes, never a parallel one.

These cases prove the goal and the fail-closed contract on a migrated site with
no production data:
  * a valid worker/trip creates exactly one boarding row, scoped to that worker,
    with method ``Worker`` (the goal);
  * re-confirming is idempotent (no duplicate headcount);
  * a blank token is refused (PermissionError) before any write;
  * a worker with no boardable trip today is a clean no-op (no row written).
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex_habitat.salis.api import masar
from apex_habitat.tests.test_driver_portal import _ensure_test_driver
from apex_habitat.tests.test_masar_worker_movement import (
    _WorkerTripMixin,
    _building,
    _employee,
    _project,
)


class TestMasarConfirmBoarding(_WorkerTripMixin, FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.project = _project("Masar CB Project")
        cls.building = _building("Masar CB Building")
        cls.driver = _ensure_test_driver()

    def setUp(self):
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")

    def _worker(self, suffix):
        """A worker unique to THIS test method, so a boarding written in one test
        never bleeds into another (the endpoint scopes by employee, and workers
        would otherwise be shared by name across methods)."""
        return _employee(f"Masar CB {self._testMethodName} {suffix}")

    def _purge_trip_logs(self, dispatch_trip):
        """Drop any Trip Start Log the endpoint opened for a trip — the trip-mixin
        cleanup removes the Dispatch Trip but not the log this endpoint creates."""
        frappe.set_user("Administrator")
        for name in frappe.get_all(
            "Trip Start Log", filters={"dispatch_trip": dispatch_trip}, pluck="name"
        ):
            doc = frappe.get_doc("Trip Start Log", name)
            if doc.docstatus == 1:
                try:
                    doc.cancel()
                except Exception:
                    pass
            frappe.delete_doc("Trip Start Log", name, ignore_permissions=True, force=True)

    def _token_for(self, employee):
        """Issue an enabled Masar Worker Token for ``employee`` and return the
        minted token string (server-generated, read back)."""
        existing = frappe.db.get_value(
            "Masar Worker Token", {"employee": employee}, "name"
        )
        if existing:
            doc = frappe.get_doc("Masar Worker Token", existing)
            if not doc.enabled:
                doc.db_set("enabled", 1)
            return doc.token
        doc = frappe.get_doc(
            {
                "doctype": "Masar Worker Token",
                "party_type": "Employee",
                "party": employee,
                "employee": employee,
                "enabled": 1,
            }
        ).insert(ignore_permissions=True)
        return doc.token

    def _boarding_rows_for(self, dispatch_trip, employee):
        """Trip Boarding Event rows for ``employee`` across this trip's Trip Start
        Log(s) — the actual proof a boarding event was created and scoped."""
        logs = frappe.get_all(
            "Trip Start Log", filters={"dispatch_trip": dispatch_trip}, pluck="name"
        )
        if not logs:
            return []
        return frappe.get_all(
            "Trip Boarding Event",
            filters={
                "parenttype": "Trip Start Log",
                "parent": ["in", logs],
                "worker": employee,
            },
            fields=["name", "worker", "method", "parent"],
        )

    def test_valid_worker_confirms_boarding_creates_scoped_event(self):
        """The goal: a tokenized worker on today's trip self-confirms -> exactly one
        Trip Boarding Event is created for THAT worker, method ``Worker``."""
        w1 = self._worker("a")
        w2 = self._worker("b")
        tr, rp, dt = self._worker_trip(
            self.driver, self.project, self.building, [w1, w2], "CB Route A"
        )
        self.addCleanup(lambda: self._purge_trip_logs(dt.name))
        token = self._token_for(w1)
        # Non-vacuous: no boarding row exists for this worker yet.
        self.assertEqual(self._boarding_rows_for(dt.name, w1), [])

        res = masar.confirm_boarding(token=token, transport_request=tr.name)
        self.assertTrue(res["created"], "a valid worker/trip must create a boarding row")
        self.assertEqual(res["dispatch_trip"], dt.name)
        self.assertEqual(res["transport_request"], tr.name)

        rows = self._boarding_rows_for(dt.name, w1)
        self.assertEqual(len(rows), 1, "exactly one boarding event for this worker")
        self.assertEqual(rows[0]["worker"], w1, "row scoped to the token's worker")
        self.assertEqual(rows[0]["method"], "Worker", "method is the worker self-confirm value")
        # Scope: the OTHER worker on the same trip got no row from w1's confirm.
        self.assertEqual(
            self._boarding_rows_for(dt.name, w2), [], "must not board another worker"
        )

    def test_reconfirm_is_idempotent(self):
        """A second confirm of the same worker on the same trip adds no row."""
        w1 = self._worker("a")
        tr, rp, dt = self._worker_trip(
            self.driver, self.project, self.building, [w1], "CB Route B"
        )
        self.addCleanup(lambda: self._purge_trip_logs(dt.name))
        token = self._token_for(w1)

        first = masar.confirm_boarding(token=token, transport_request=tr.name)
        self.assertTrue(first["created"])
        second = masar.confirm_boarding(token=token, transport_request=tr.name)
        self.assertFalse(second["created"], "re-confirm must not create a second row")

        self.assertEqual(
            len(self._boarding_rows_for(dt.name, w1)), 1, "still exactly one row"
        )

    def test_blank_token_is_rejected(self):
        """The write endpoint funnels through _resolve_worker, so a blank/missing
        token fails closed (PermissionError) before any boarding is considered."""
        for blank in (None, "", "   "):
            with self.assertRaises(frappe.PermissionError):
                masar.confirm_boarding(token=blank)

    def test_unknown_token_is_rejected(self):
        """A well-formed but non-existent token must 403 (no row -> fail closed),
        so a tampered/blank link can never write a boarding event."""
        bogus = frappe.generate_hash(length=48)
        self.assertFalse(frappe.db.exists("Masar Worker Token", {"token": bogus}))
        with self.assertRaises(frappe.PermissionError):
            masar.confirm_boarding(token=bogus)

    def test_worker_with_no_trip_today_is_noop(self):
        """A valid worker who is on no boardable trip today is a clean no-op — the
        token resolves, but nothing is written."""
        # A fresh worker registered on NO transport request.
        lonely = self._worker("lonely")
        token = self._token_for(lonely)
        # Non-vacuous: the token genuinely resolves to this worker.
        self.assertEqual(masar._resolve_worker(token), lonely)

        res = masar.confirm_boarding(token=token)
        self.assertIsNone(res.get("trip"), "no boardable trip -> {'trip': None}")
        self.assertFalse(res.get("created"))
