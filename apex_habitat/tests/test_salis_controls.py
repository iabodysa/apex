"""Tests for the Salis control fixes (segregation of duties, portal gating,
attendance uniqueness). These cover behaviour that must hold regardless of any
later workflow refactor."""

import unittest

import frappe

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
    """A Finance approver may not approve a payment they themselves raised."""

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
        if "Finance Manager" not in frappe.get_roles(email):
            u.add_roles("Finance Manager")
        return email

    def _new_request_as(self, user):
        frappe.set_user(user)
        doc = frappe.get_doc(
            {"doctype": "Salis Payment Request", "expense_type": "Fuel",
             "amount": 100, "status": "Pending Finance"}
        ).insert(ignore_permissions=True)
        return doc

    def test_requester_cannot_self_approve(self):
        doc = self._new_request_as(self.fin1)
        self.assertEqual(doc.requested_by, self.fin1)
        doc.status = "Approved by Finance"
        with self.assertRaises(frappe.ValidationError):
            doc.save(ignore_permissions=True)
        frappe.set_user("Administrator")
        frappe.delete_doc("Salis Payment Request", doc.name, ignore_permissions=True, force=True)
        frappe.db.commit()

    def test_other_finance_user_can_approve(self):
        doc = self._new_request_as(self.fin1)
        frappe.set_user(self.fin2)
        doc.status = "Approved by Finance"
        doc.save(ignore_permissions=True)
        self.assertEqual(doc.finance_approved_by, self.fin2)
        frappe.set_user("Administrator")
        frappe.delete_doc("Salis Payment Request", doc.name, ignore_permissions=True, force=True)
        frappe.db.commit()
