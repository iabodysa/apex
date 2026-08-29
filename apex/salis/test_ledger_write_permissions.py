# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.utils.portal_identity import DRIVER, WORKER, as_capacity
from apex.salis.api.boarding import _log_scan
from apex.salis.fuel_engine import reverse_fuel_ledger
from apex.salis.rental_engine import reverse_rental_accrual
from apex.tests.factories import make_vehicle

GRANTED_USER = "fleet_manager_ledger_write@example.com"
UNGRANTED_USER = "internal_auditor_ledger_write@example.com"

_SOURCE = "TEST-FR-LEDGER-WRITE"
_PLATE = "LEDGER-WRITE-1"


def _user(email, role):
    if not frappe.db.exists("User", email):
        frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": email.split("@")[0],
                "send_welcome_email": 0,
            }
        ).insert(ignore_permissions=True)
    doc = frappe.get_doc("User", email)
    if role not in {r.role for r in doc.roles}:
        doc.add_roles(role)
    return email


class TestALedgerWriteRunsUnderTheCallersOwnPermission(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.granted = _user(GRANTED_USER, "Fleet Manager")
        cls.ungranted = _user(UNGRANTED_USER, "Internal Auditor")
        cls.vehicle = make_vehicle(_PLATE, ownership="Rented")

    def setUp(self):
        frappe.set_user("Administrator")
        self.addCleanup(lambda: frappe.set_user("Administrator"))

    def _purge_ledger(self, doctype, filters):
        frappe.set_user("Administrator")
        for name in frappe.get_all(doctype, filters=filters, pluck="name"):
            frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)

    def _fuel_original(self):
        original = frappe.get_doc(
            {
                "doctype": "Fuel Consumption Ledger",
                "period_month": "2026-01",
                "litres": 10,
                "amount": 100,
                "source_type": "Fuel Request",
                "source_doctype": "Fuel Request",
                "source_name": _SOURCE,
            }
        ).insert(ignore_permissions=True)
        self.addCleanup(
            lambda: self._purge_ledger(
                "Fuel Consumption Ledger", {"source_name": _SOURCE}
            )
        )
        return original

    def _rental_original(self):
        original = frappe.get_doc(
            {
                "doctype": "Rental Accrual Ledger",
                "vehicle": self.vehicle,
                "accrual_date": "2026-01-05",
                "daily_rate": 50,
                "amount": 50,
                "source_doctype": "Rental Vehicle Movement",
                "source_name": _SOURCE,
            }
        ).insert(ignore_permissions=True)
        self.addCleanup(
            lambda: self._purge_ledger("Rental Accrual Ledger", {"vehicle": self.vehicle})
        )
        return original

    def test_fleet_manager_reverses_a_fuel_ledger_row_without_a_permission_bypass(self):
        self._fuel_original()
        frappe.set_user(self.granted)
        self.assertEqual(reverse_fuel_ledger("Fuel Request", _SOURCE), 1)

    def test_a_role_without_create_on_the_fuel_ledger_is_refused_the_reversal(self):
        self._fuel_original()
        frappe.set_user(self.ungranted)
        with self.assertRaises(frappe.PermissionError):
            reverse_fuel_ledger("Fuel Request", _SOURCE)

    def test_fleet_manager_reverses_a_rental_accrual_without_a_permission_bypass(self):
        self._rental_original()
        frappe.set_user(self.granted)
        self.assertEqual(
            reverse_rental_accrual("Rental Vehicle Movement", _SOURCE), 1
        )

    def test_a_role_without_create_on_the_rental_ledger_is_refused_the_reversal(self):
        self._rental_original()
        frappe.set_user(self.ungranted)
        with self.assertRaises(frappe.PermissionError):
            reverse_rental_accrual("Rental Vehicle Movement", _SOURCE)

    def _insert_trip_ledger(self, doctype, values):
        return frappe.get_doc({"doctype": doctype, **values}).insert(ignore_links=True)

    def test_fleet_manager_posts_a_trip_fulfilment_ledger_row(self):
        self.addCleanup(
            lambda: self._purge_ledger(
                "Trip Fulfilment Ledger", {"dispatch_trip": _SOURCE}
            )
        )
        frappe.set_user(self.granted)
        row = self._insert_trip_ledger(
            "Trip Fulfilment Ledger", {"dispatch_trip": _SOURCE, "worker_count": 1}
        )
        self.assertTrue(row.name)

    def test_a_role_without_create_on_the_fulfilment_ledger_is_refused(self):
        frappe.set_user(self.ungranted)
        with self.assertRaises(frappe.PermissionError):
            self._insert_trip_ledger(
                "Trip Fulfilment Ledger", {"dispatch_trip": _SOURCE, "worker_count": 1}
            )

    def test_fleet_manager_posts_a_trip_boarding_ledger_row(self):
        self.addCleanup(
            lambda: self._purge_ledger(
                "Trip Boarding Ledger", {"dispatch_trip": _SOURCE}
            )
        )
        frappe.set_user(self.granted)
        row = self._insert_trip_ledger(
            "Trip Boarding Ledger",
            {"dispatch_trip": _SOURCE, "employee": _SOURCE, "outcome": "Boarded"},
        )
        self.assertTrue(row.name)

    def test_a_role_without_create_on_the_boarding_ledger_is_refused(self):
        frappe.set_user(self.ungranted)
        with self.assertRaises(frappe.PermissionError):
            self._insert_trip_ledger(
                "Trip Boarding Ledger",
                {"dispatch_trip": _SOURCE, "employee": _SOURCE, "outcome": "Boarded"},
            )

    def test_the_driver_capacity_posts_a_trip_boarding_ledger_row(self):
        self.addCleanup(
            lambda: self._purge_ledger(
                "Trip Boarding Ledger", {"dispatch_trip": _SOURCE}
            )
        )
        with as_capacity(DRIVER, None):
            row = self._insert_trip_ledger(
                "Trip Boarding Ledger",
                {"dispatch_trip": _SOURCE, "employee": _SOURCE, "outcome": "Boarded"},
            )
        self.assertTrue(row.name)

    def test_the_worker_capacity_is_refused_the_trip_boarding_ledger_row(self):
        with as_capacity(WORKER, None):
            with self.assertRaises(frappe.PermissionError):
                self._insert_trip_ledger(
                    "Trip Boarding Ledger",
                    {"dispatch_trip": _SOURCE, "employee": _SOURCE, "outcome": "Boarded"},
                )

    def test_the_driver_capacity_writes_the_boarding_scan_log(self):
        self.addCleanup(
            lambda: self._purge_ledger("Boarding Scan Log", {"result": "Invalid Token"})
        )
        name = _log_scan(None, None, None, "Invalid Token", None)
        self.assertEqual(
            frappe.db.get_value("Boarding Scan Log", name, "owner"),
            "driver@apex.internal",
        )

    def test_the_worker_capacity_is_refused_the_boarding_scan_log(self):
        with as_capacity(WORKER, None):
            with self.assertRaises(frappe.PermissionError):
                frappe.get_doc(
                    {"doctype": "Boarding Scan Log", "result": "Invalid Token"}
                ).insert()

