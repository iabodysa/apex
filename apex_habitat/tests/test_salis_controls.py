"""Tests for the Salis control fixes (segregation of duties, portal gating,
attendance uniqueness). These cover behaviour that must hold regardless of any
later workflow refactor."""

import unittest

import frappe
from frappe.model.workflow import apply_workflow, get_transitions

from apex_habitat.salis.api import driver_portal
from apex_habitat.tests.test_driver_portal import _ensure_test_driver


class TestDriverPortalGating(unittest.TestCase):
    """Read and write endpoints must honour Salis Settings.enable_driver_portal."""

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cls.driver = _ensure_test_driver()
        cls.user = frappe.db.get_value(
            "Employee", frappe.db.get_value("Salis Driver", cls.driver, "employee"), "user_id"
        )

    def tearDown(self):
        frappe.set_user("Administrator")
        frappe.db.set_single_value("Salis Settings", "enable_driver_portal", 1)
        frappe.db.commit()

    def test_reads_and_writes_blocked_when_portal_disabled(self):
        frappe.db.set_single_value("Salis Settings", "enable_driver_portal", 0)
        frappe.db.commit()
        frappe.set_user(self.user)
        for call in (
            driver_portal.my_trips_today,
            driver_portal.my_support_tickets,
            driver_portal.driver_check_in,
            driver_portal.driver_check_out,
        ):
            with self.assertRaises(frappe.PermissionError):
                call()


class TestDriverAttendanceDuplicate(unittest.TestCase):
    """One attendance row per driver per day."""

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cls.driver = _ensure_test_driver()

    def test_second_attendance_same_day_is_rejected(self):
        today = frappe.utils.today()
        frappe.db.delete("Driver Attendance", {"driver": self.driver, "attendance_date": today})
        frappe.db.commit()
        first = frappe.get_doc(
            {"doctype": "Driver Attendance", "driver": self.driver,
             "attendance_date": today, "status": "Present"}
        ).insert(ignore_permissions=True)
        with self.assertRaises(frappe.ValidationError):
            frappe.get_doc(
                {"doctype": "Driver Attendance", "driver": self.driver,
                 "attendance_date": today, "status": "Present"}
            ).insert(ignore_permissions=True)
        first.delete(ignore_permissions=True)
        frappe.db.commit()


class TestPaymentRequestSoD(unittest.TestCase):
    """A Finance approver may not approve a payment they themselves raised.

    Transitions are owned by the native Salis Payment Request Workflow, so the
    request is driven Draft -> Pending Finance -> Approved by Finance through
    ``apply_workflow``. The maker != checker rule is held both by the workflow
    condition and by the controller's finance gate (defence in depth); this test
    exercises the canonical workflow path."""

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cls.fin1 = cls._finance_user("fin1_sod@example.com")
        cls.fin2 = cls._finance_user("fin2_sod@example.com")
        frappe.db.commit()

    @staticmethod
    def _finance_user(email):
        if not frappe.db.exists("User", email):
            u = frappe.get_doc({"doctype": "User", "email": email,
                                "first_name": email.split("@")[0], "send_welcome_email": 0})
            u.insert(ignore_permissions=True)
        else:
            u = frappe.get_doc("User", email)
        # Finance Manager (to approve) plus an operational maker role (to raise /
        # submit-to-finance), so the only thing standing between a requester and
        # self-approval is the SoD condition, not a role gap.
        for role in ("Finance Manager", "Fleet Project Manager"):
            if role not in frappe.get_roles(email):
                u.add_roles(role)
        return email

    def _pending_request_by(self, user):
        """A Pending Finance request whose requested_by is ``user``, reached via
        the workflow (insert at Draft, then Submit to Finance)."""
        frappe.set_user("Administrator")
        doc = frappe.get_doc(
            {"doctype": "Salis Payment Request", "expense_type": "Fuel",
             "amount": 100, "requested_by": user, "status": "Draft"}
        ).insert(ignore_permissions=True)
        frappe.set_user(user)
        apply_workflow(doc, "Submit to Finance")
        frappe.set_user("Administrator")
        doc.reload()
        return doc

    def test_requester_cannot_self_approve(self):
        doc = self._pending_request_by(self.fin1)
        self.assertEqual(doc.requested_by, self.fin1)
        frappe.set_user(self.fin1)
        # The SoD condition removes the approve transition for the requester.
        self.assertNotIn("Approve (Finance)", {t.action for t in get_transitions(doc)})
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(doc, "Approve (Finance)")
        frappe.set_user("Administrator")
        frappe.delete_doc("Salis Payment Request", doc.name, ignore_permissions=True, force=True)
        frappe.db.commit()

    def test_other_finance_user_can_approve(self):
        doc = self._pending_request_by(self.fin1)
        frappe.set_user(self.fin2)
        apply_workflow(doc, "Approve (Finance)")
        doc.reload()
        self.assertEqual(doc.status, "Approved by Finance")
        self.assertEqual(doc.docstatus, 1)
        self.assertEqual(doc.finance_approved_by, self.fin2)
        # Approve (Finance) submits the document; cancel before deleting.
        frappe.set_user("Administrator")
        doc.reload()
        doc.cancel()
        frappe.delete_doc("Salis Payment Request", doc.name, ignore_permissions=True, force=True)
        frappe.db.commit()


class TestRequestedByStamping(unittest.TestCase):
    """``requested_by`` is stamped to the session user server-side and is a
    read-only field on the SoD-bearing DocTypes, so the maker != checker gate
    cannot be spoofed through the form path."""

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cls.user = cls._mgr("rb_user@example.com")
        frappe.db.commit()

    def tearDown(self):
        frappe.set_user("Administrator")

    @staticmethod
    def _mgr(email):
        if not frappe.db.exists("User", email):
            u = frappe.get_doc({"doctype": "User", "email": email,
                                "first_name": email.split("@")[0], "send_welcome_email": 0})
            u.insert(ignore_permissions=True)
        else:
            u = frappe.get_doc("User", email)
        for role in ("Fleet Manager", "Fleet Project Manager"):
            if role not in frappe.get_roles(email):
                u.add_roles(role)
        return email

    def _vehicle(self, plate):
        v = frappe.db.get_value("Salis Vehicle", {"plate_number": plate}, "name")
        if not v:
            v = frappe.get_doc({"doctype": "Salis Vehicle", "plate_number": plate,
                                "status": "Active"}).insert(ignore_permissions=True).name
        return v

    def _project(self, name):
        p = frappe.db.get_value("Project", {"project_name": name}, "name")
        if not p:
            p = frappe.get_doc({"doctype": "Project", "project_name": name}).insert(
                ignore_permissions=True).name
        return p

    def test_field_is_read_only_in_schema(self):
        for dt in ("Fuel Claim", "Rental Settlement", "Approval Request",
                   "Salis Payment Request"):
            meta = frappe.get_meta(dt)
            field = meta.get_field("requested_by")
            self.assertIsNotNone(field, f"{dt} must declare requested_by")
            self.assertTrue(field.read_only, f"{dt}.requested_by must be read_only")

    def test_fuel_claim_stamps_session_user(self):
        frappe.set_user(self.user)
        doc = frappe.get_doc({
            "doctype": "Fuel Claim", "project": self._project("RB Claim P"),
            "vehicle": self._vehicle("RB CLAIM 1"), "period_month": "2026-05",
            "claimed_litres": 50, "status": "Draft",
        }).insert(ignore_permissions=True)
        self.assertEqual(doc.requested_by, self.user)
        frappe.set_user("Administrator")
        frappe.delete_doc("Fuel Claim", doc.name, ignore_permissions=True, force=True)
        frappe.db.commit()

    def test_rental_settlement_stamps_session_user(self):
        frappe.set_user(self.user)
        office = frappe.db.get_value("Rental Office", {}, "name")
        if not office:
            office = frappe.get_doc({"doctype": "Rental Office",
                                     "office_name": "RB Office"}).insert(
                ignore_permissions=True).name
        doc = frappe.get_doc({
            "doctype": "Rental Settlement", "rental_office": office,
            "period_month": "2026-05", "status": "Draft", "claimed_total": 0,
        }).insert(ignore_permissions=True)
        self.assertEqual(doc.requested_by, self.user)
        frappe.set_user("Administrator")
        frappe.delete_doc("Rental Settlement", doc.name, ignore_permissions=True, force=True)
        frappe.db.commit()

    def test_approval_request_stamps_session_user(self):
        frappe.set_user(self.user)
        doc = frappe.get_doc({
            "doctype": "Approval Request", "request_type": "Other",
            "approver": "Administrator", "decision": "Pending",
        }).insert(ignore_permissions=True)
        self.assertEqual(doc.requested_by, self.user)
        frappe.set_user("Administrator")
        frappe.delete_doc("Approval Request", doc.name, ignore_permissions=True, force=True)
        frappe.db.commit()
