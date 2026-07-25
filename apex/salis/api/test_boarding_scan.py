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

from contextlib import contextmanager
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.doctype.masar_worker_token.masar_worker_token import (
    issue_driver_link,
)
from apex.salis.api import boarding
from apex.tests.factories import (
    WorkerTripMixin as _WorkerTripMixin,
    make_masar_building as _building,
    make_worker_employee as _employee,
    make_project as _project,
)


class _Request:
    def __init__(self, cookies):
        self.cookies = cookies
        self.remote_addr = "127.0.0.1"


@contextmanager
def _request_cookies(cookies):
    sentinel = object()
    previous_request = getattr(frappe.local, "request", sentinel)
    previous_ip = getattr(frappe.local, "request_ip", sentinel)
    previous_form = getattr(frappe.local, "form_dict", sentinel)
    frappe.local.request = _Request(cookies)
    frappe.local.request_ip = "127.0.0.1"
    frappe.local.form_dict = frappe._dict(
        {"cmd": "boarding-scan-" + frappe.generate_hash(length=12)}
    )
    try:
        yield
    finally:
        for fieldname, previous in (
            ("request", previous_request),
            ("request_ip", previous_ip),
            ("form_dict", previous_form),
        ):
            if previous is sentinel:
                if hasattr(frappe.local, fieldname):
                    delattr(frappe.local, fieldname)
            else:
                setattr(frappe.local, fieldname, previous)


class TestBoardingScan(_WorkerTripMixin, FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.project = _project("Boarding Scan Project")
        cls.building = _building("Boarding Scan Building")
        tag = frappe.generate_hash(length=12).upper()
        cls.driver = (
            frappe.get_doc(
                {
                    "doctype": "Salis Driver",
                    "full_name": f"Boarding Driver {tag}",
                    "status": "Active",
                }
            )
            .insert(ignore_permissions=True)
            .name
        )
        cls.other_driver = (
            frappe.get_doc(
                {
                    "doctype": "Salis Driver",
                    "full_name": f"Boarding Other Driver {tag}",
                    "status": "Active",
                }
            )
            .insert(ignore_permissions=True)
            .name
        )
        cls._token_meta = frappe.get_meta("Masar Worker Token")
        cls._original_token_autoname = cls._token_meta.autoname
        cls.addClassCleanup(
            setattr,
            cls._token_meta,
            "autoname",
            cls._original_token_autoname,
        )
        cls._token_meta.autoname = "hash"
        cls.driver_token = issue_driver_link(cls.driver)["token"]
        cls.other_driver_token = issue_driver_link(cls.other_driver)["token"]
        cls.w1 = _employee("Boarding Worker One")
        cls.w2 = _employee("Boarding Worker Two")
        # [#b7jhii]
        cls.off_manifest = _employee("Boarding Off Manifest")

    @classmethod
    def tearDownClass(cls):
        # [#4w47gh]
        frappe.set_user("Administrator")
        for driver in (cls.driver, cls.other_driver):
            token_name = frappe.db.get_value(
                "Masar Worker Token",
                {"holder_type": "Driver", "driver": driver},
                "name",
            )
            if token_name:
                frappe.delete_doc(
                    "Masar Worker Token",
                    token_name,
                    ignore_permissions=True,
                    force=True,
                )
            if frappe.db.exists("Salis Driver", driver):
                frappe.delete_doc(
                    "Salis Driver",
                    driver,
                    ignore_permissions=True,
                    force=True,
                )
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

    def _paired_trips(self, suffix):
        _tr, _rp, own_trip = self._worker_trip(
            self.driver,
            self.project,
            self.building,
            [self.w1],
            f"Credential Own {suffix}",
        )
        _other_tr, _other_rp, other_trip = self._worker_trip(
            self.other_driver,
            self.project,
            self.building,
            [self.w2],
            f"Credential Other {suffix}",
        )
        return own_trip, other_trip

    def _assert_guest_rejected_before_trip_read(self, dispatch_trip):
        frappe.set_user("Guest")
        real_get_value = boarding.frappe.db.get_value
        with _request_cookies({}), patch.object(
            boarding.frappe.db,
            "get_value",
            wraps=real_get_value,
        ) as reads:
            with self.assertRaises(frappe.PermissionError):
                boarding._resolve_trip(dispatch_trip)
        trip_reads = [
            call
            for call in reads.call_args_list
            if call.args and call.args[0] == "Dispatch Trip"
        ]
        self.assertEqual(trip_reads, [])

    def test_missing_guest_credential_is_denied_before_existing_trip_lookup(self):
        own_trip, _other_trip = self._paired_trips(self._testMethodName)
        self._assert_guest_rejected_before_trip_read(own_trip.name)

    def test_missing_guest_credential_is_denied_before_nonexistent_trip_lookup(self):
        self._assert_guest_rejected_before_trip_read(
            "MISSING-" + frappe.generate_hash(length=12)
        )

    def test_staff_without_driver_credential_can_resolve_any_trip(self):
        _own_trip, other_trip = self._paired_trips(self._testMethodName)
        frappe.set_user("Administrator")
        with _request_cookies({}):
            resolved = boarding._resolve_trip(other_trip.name)
        self.assertEqual(resolved.name, other_trip.name)

    def test_staff_session_with_driver_cookie_can_resolve_token_driver_trip(self):
        own_trip, _other_trip = self._paired_trips(self._testMethodName)
        frappe.set_user("Administrator")
        with _request_cookies({"masar_dt": self.driver_token}):
            resolved = boarding._resolve_trip(own_trip.name)
        self.assertEqual(resolved.driver, self.driver)

    def test_staff_session_with_driver_cookie_is_confined_to_token_driver_trip(self):
        _own_trip, other_trip = self._paired_trips(self._testMethodName)
        frappe.set_user("Administrator")
        with _request_cookies({"masar_dt": self.driver_token}):
            with self.assertRaises(frappe.PermissionError):
                boarding._resolve_trip(other_trip.name)

    def test_valid_driver_credential_denies_foreign_and_missing_trips_uniformly(self):
        _own_trip, other_trip = self._paired_trips(self._testMethodName)
        missing_trip = "MISSING-" + frappe.generate_hash(length=12)
        denials = []
        frappe.set_user("Guest")
        with _request_cookies({"masar_dt": self.driver_token}):
            for trip_name in (other_trip.name, missing_trip):
                with self.subTest(trip_name=trip_name):
                    with self.assertRaises(frappe.PermissionError) as denial:
                        boarding._resolve_trip(trip_name)
                    denials.append(str(denial.exception))
        self.assertEqual(denials[0], denials[1])

    def test_invalid_cookie_under_staff_session_is_denied(self):
        _own_trip, other_trip = self._paired_trips(self._testMethodName)
        frappe.set_user("Administrator")
        with _request_cookies({"masar_dt": "invalid"}):
            with self.assertRaises(frappe.PermissionError):
                boarding._resolve_trip(other_trip.name)

    def test_blank_presented_cookie_under_staff_session_is_denied(self):
        _own_trip, other_trip = self._paired_trips(self._testMethodName)
        frappe.set_user("Administrator")
        with _request_cookies({"masar_dt": ""}):
            with self.assertRaises(frappe.PermissionError):
                boarding._resolve_trip(other_trip.name)

    def test_invalid_cookie_is_denied_before_missing_trip_lookup(self):
        frappe.set_user("Administrator")
        with _request_cookies({"masar_dt": "invalid"}):
            with self.assertRaises(frappe.PermissionError):
                boarding._resolve_trip("MISSING-" + frappe.generate_hash(length=12))

    def test_blank_cookie_is_denied_before_missing_trip_lookup(self):
        frappe.set_user("Administrator")
        with _request_cookies({"masar_dt": ""}):
            with self.assertRaises(frappe.PermissionError):
                boarding._resolve_trip("MISSING-" + frappe.generate_hash(length=12))

    def test_cookie_context_restores_previously_absent_request_state(self):
        sentinel = object()
        previous_request = getattr(frappe.local, "request", sentinel)
        previous_ip = getattr(frappe.local, "request_ip", sentinel)
        for fieldname in ("request", "request_ip"):
            if hasattr(frappe.local, fieldname):
                delattr(frappe.local, fieldname)
        try:
            with _request_cookies({"masar_dt": self.driver_token}):
                self.assertTrue(hasattr(frappe.local, "request"))
                self.assertTrue(hasattr(frappe.local, "request_ip"))
            self.assertFalse(hasattr(frappe.local, "request"))
            self.assertFalse(hasattr(frappe.local, "request_ip"))
        finally:
            for fieldname, previous in (
                ("request", previous_request),
                ("request_ip", previous_ip),
            ):
                if previous is not sentinel:
                    setattr(frappe.local, fieldname, previous)

    def test_invalid_cookie_cannot_write_forged_pass_audit(self):
        before = frappe.db.count("Boarding Scan Log")
        with _request_cookies({"masar_dt": "invalid"}):
            with self.assertRaises(frappe.PermissionError):
                boarding.scan_boarding_pass("forged-pass")
        self.assertEqual(frappe.db.count("Boarding Scan Log"), before)

    def test_blank_cookie_cannot_write_forged_pass_audit(self):
        before = frappe.db.count("Boarding Scan Log")
        with _request_cookies({"masar_dt": ""}):
            with self.assertRaises(frappe.PermissionError):
                boarding.scan_boarding_pass("forged-pass")
        self.assertEqual(frappe.db.count("Boarding Scan Log"), before)

    def test_missing_cookie_guest_cannot_write_forged_pass_audit(self):
        before = frappe.db.count("Boarding Scan Log")
        frappe.set_user("Guest")
        with _request_cookies({}):
            with self.assertRaises(frappe.PermissionError):
                boarding.scan_boarding_pass("forged-pass")
        self.assertEqual(frappe.db.count("Boarding Scan Log"), before)

    def test_valid_cookie_preserves_invalid_pass_audit(self):
        with _request_cookies({"masar_dt": self.driver_token}):
            result = boarding.scan_boarding_pass("forged-pass")
        self.addCleanup(
            frappe.delete_doc,
            "Boarding Scan Log",
            result["scan_log"],
            ignore_permissions=True,
            force=True,
        )
        self.assertEqual(result["result"], "Invalid Token")

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

        # [#65569c]
        log = frappe.get_doc("Trip Start Log", res["trip_start_log"])
        self.assertEqual(log.boarded_count, 1)
        self.assertEqual(len(log.boarding_events), 1)
        row = log.boarding_events[0]
        self.assertEqual(row.worker, self.w1)
        self.assertEqual(row.method, "QR")
        self.assertEqual(row.accommodation_building, self.building)

        # [#q4ltp5]
        scan = frappe.get_doc("Boarding Scan Log", res["scan_log"])
        self.assertEqual(scan.result, "Valid")
        self.assertEqual(scan.employee, self.w1)
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

        # [#1p0lyv]
        rows = frappe.get_all(
            "Boarding Scan Log",
            filters={"dispatch_trip": dt.name, "employee": self.w1},
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
        # [#5oy7f9]
        forged = pass_data["pass_token"][:-4] + "0000"

        res = boarding.scan_boarding_pass(forged)
        self.assertEqual(res["result"], "Invalid Token")

        # [#hvvfpf]
        logs = frappe.get_all("Trip Start Log", filters={"dispatch_trip": dt.name})
        self.assertEqual(logs, [])
        # [#s0exfb]
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
        self.assertEqual(len(scan.pass_token_hash), 64)  # [#kllefw]


def tearDownModule():
    # [#2esm3x]
    from apex.tests import factories

    factories.purge_test_buildings()
