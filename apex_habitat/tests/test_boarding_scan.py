# Copyright (c) 2026, AFMCO and contributors
"""QR boarding-pass + scan-validate tests (Salis driver passenger-boarding).

Proves the end-to-end boarding flow on ``salis.api.boarding``:

  1. a Valid scan of an issued pass appends ONE Trip Boarding Event row to the
     trip's Trip Start Log AND writes a Boarding Scan Log audit row (result Valid,
     boarding_event_created set) — the core goal: a scan logs a row;
  2. a second scan of the same worker is a Duplicate — no second boarding row,
     but the duplicate attempt is still audited;
  3. a forged/tampered token is Invalid Token and creates no boarding row;
  4. a pass for a worker not on the trip's manifest is rejected at issue time, and
     a hand-built token for an off-manifest worker scans as Wrong Trip;
  5. the issued pass never leaks the raw token into the audit row (only its hash).

The trip fixture reuses the proven worker-trip builder from the Masar movement
tests; everything is created as Administrator with ignore_permissions, then the
scan endpoint is exercised directly.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex_habitat.salis.api import boarding
from apex_habitat.tests.factories import (
    WorkerTripMixin as _WorkerTripMixin,
    make_masar_building as _building,
    make_test_driver as _ensure_test_driver,
    make_worker_employee as _employee,
    make_project as _project,
)


class TestBoardingScan(_WorkerTripMixin, FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.project = _project("Boarding Scan Project")
        cls.building = _building("Boarding Scan Building")
        cls.driver = _ensure_test_driver()
        cls.w1 = _employee("Boarding Worker One")
        cls.w2 = _employee("Boarding Worker Two")
        # An employee deliberately NOT placed on the trip manifest.
        cls.off_manifest = _employee("Boarding Off Manifest")

    @classmethod
    def tearDownClass(cls):
        # setUpClass commits a per-class Project OUTSIDE the per-method savepoint
        # rollback; delete it so the committed Project does not leak across the
        # test DB. (Site/Building/Employees are reuse-or-create shared fixtures.)
        frappe.set_user("Administrator")
        if frappe.db.exists("Project", cls.project):
            frappe.delete_doc("Project", cls.project, ignore_permissions=True, force=True)
        frappe.db.commit()
        super().tearDownClass()

    def setUp(self):
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")

    def _cleanup_logs(self, dispatch_trip):
        """Drop any Trip Start Log + Boarding Scan Log rows the scan created."""
        def _purge():
            frappe.set_user("Administrator")
            for name in frappe.get_all(
                "Boarding Scan Log",
                filters={"dispatch_trip": dispatch_trip},
                pluck="name",
            ):
                frappe.delete_doc("Boarding Scan Log", name, ignore_permissions=True, force=True)
            for name in frappe.get_all(
                "Trip Start Log",
                filters={"dispatch_trip": dispatch_trip},
                pluck="name",
            ):
                doc = frappe.get_doc("Trip Start Log", name)
                if doc.docstatus == 1:
                    try:
                        doc.cancel()
                    except Exception:
                        pass
                frappe.delete_doc("Trip Start Log", name, ignore_permissions=True, force=True)

        self.addCleanup(_purge)

    def test_valid_scan_creates_boarding_and_audit_rows(self):
        """The core goal: a valid scan appends one Trip Boarding Event row to the
        trip's Trip Start Log and writes a Valid Boarding Scan Log row."""
        tr, rp, dt = self._worker_trip(
            self.driver, self.project, self.building, [self.w1, self.w2], "Scan Route A"
        )
        self._cleanup_logs(dt.name)

        pass_data = boarding.get_boarding_pass(dt.name, self.w1)
        self.assertIn("pass_token", pass_data)
        self.assertEqual(pass_data["worker"], self.w1)

        res = boarding.scan_boarding_pass(
            pass_data["pass_token"], accommodation_building=self.building
        )
        self.assertEqual(res["result"], "Valid")

        # The Trip Start Log gained exactly one boarding row for this worker.
        log = frappe.get_doc("Trip Start Log", res["trip_start_log"])
        self.assertEqual(log.boarded_count, 1)
        self.assertEqual(len(log.boarding_events), 1)
        row = log.boarding_events[0]
        self.assertEqual(row.worker, self.w1)
        self.assertEqual(row.method, "QR")
        self.assertEqual(row.accommodation_building, self.building)

        # An audit row was written, flagged as having created the boarding event.
        scan = frappe.get_doc("Boarding Scan Log", res["scan_log"])
        self.assertEqual(scan.result, "Valid")
        self.assertEqual(scan.worker, self.w1)
        self.assertEqual(scan.dispatch_trip, dt.name)
        self.assertEqual(scan.trip_start_log, log.name)
        self.assertEqual(scan.boarding_event_created, 1)

    def test_duplicate_scan_logs_no_second_boarding_row(self):
        tr, rp, dt = self._worker_trip(
            self.driver, self.project, self.building, [self.w1], "Scan Route B"
        )
        self._cleanup_logs(dt.name)
        pass_data = boarding.get_boarding_pass(dt.name, self.w1)

        first = boarding.scan_boarding_pass(pass_data["pass_token"])
        self.assertEqual(first["result"], "Valid")
        second = boarding.scan_boarding_pass(pass_data["pass_token"])
        self.assertEqual(second["result"], "Duplicate")

        log = frappe.get_doc("Trip Start Log", first["trip_start_log"])
        self.assertEqual(log.boarded_count, 1)

        # Both attempts are audited (1 Valid + 1 Duplicate).
        rows = frappe.get_all(
            "Boarding Scan Log",
            filters={"dispatch_trip": dt.name, "worker": self.w1},
            fields=["result"],
        )
        results = sorted(r["result"] for r in rows)
        self.assertEqual(results, ["Duplicate", "Valid"])

    def test_forged_token_is_invalid_and_creates_no_boarding(self):
        tr, rp, dt = self._worker_trip(
            self.driver, self.project, self.building, [self.w1], "Scan Route C"
        )
        self._cleanup_logs(dt.name)
        pass_data = boarding.get_boarding_pass(dt.name, self.w1)
        # Tamper the signature.
        forged = pass_data["pass_token"][:-4] + "0000"

        res = boarding.scan_boarding_pass(forged)
        self.assertEqual(res["result"], "Invalid Token")

        # No Trip Start Log boarding row exists for this trip.
        logs = frappe.get_all("Trip Start Log", filters={"dispatch_trip": dt.name})
        self.assertEqual(logs, [])
        # The rejected attempt is still audited.
        self.assertTrue(frappe.db.exists("Boarding Scan Log", res["scan_log"]))

    def test_pass_for_off_manifest_worker_rejected_at_issue(self):
        tr, rp, dt = self._worker_trip(
            self.driver, self.project, self.building, [self.w1], "Scan Route D"
        )
        self._cleanup_logs(dt.name)
        with self.assertRaises(frappe.ValidationError):
            boarding.get_boarding_pass(dt.name, self.off_manifest)

    def test_off_manifest_token_scans_as_wrong_trip(self):
        """A token minted for an off-manifest worker (bypassing issue-time guard)
        is rejected at scan time as Wrong Trip and creates no boarding row."""
        tr, rp, dt = self._worker_trip(
            self.driver, self.project, self.building, [self.w1], "Scan Route E"
        )
        self._cleanup_logs(dt.name)
        token = boarding._issue_token(dt.name, self.off_manifest)
        res = boarding.scan_boarding_pass(token)
        self.assertEqual(res["result"], "Wrong Trip")
        logs = frappe.get_all("Trip Start Log", filters={"dispatch_trip": dt.name})
        self.assertEqual(logs, [])

    def test_audit_row_stores_hash_not_raw_token(self):
        tr, rp, dt = self._worker_trip(
            self.driver, self.project, self.building, [self.w1], "Scan Route F"
        )
        self._cleanup_logs(dt.name)
        pass_data = boarding.get_boarding_pass(dt.name, self.w1)
        res = boarding.scan_boarding_pass(pass_data["pass_token"])
        scan = frappe.get_doc("Boarding Scan Log", res["scan_log"])
        self.assertNotEqual(scan.pass_token_hash, pass_data["pass_token"])
        self.assertEqual(len(scan.pass_token_hash), 64)  # sha-256 hexdigest


def tearDownModule():
    # P-148: drop this module's committed Accommodation Buildings so the suite's
    # post-run building count returns to the pre-suite baseline (see factories.py).
    from apex_habitat.tests import factories

    factories.purge_test_buildings()
