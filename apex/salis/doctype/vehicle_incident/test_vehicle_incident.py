# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Vehicle Incident controller.

Proves the theft side effects and their reversal, that an accident records the
event without touching vehicle state, that a future-dated incident is rejected,
and (A-102) that driver cost recovery is consent-gated and maps to exactly one
native HRMS Employee Advance.
"""

from __future__ import annotations

import json

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from apex.apex_core.utils.employee_recovery import find_recovery_advance, raise_recovery_advance


class TestVehicleIncident(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        # [#gn6wfx]
        tag = self._testMethodName
        self.driver = frappe.get_doc(
            {"doctype": "Salis Driver", "full_name": f"Incident Driver {tag}", "status": "Active"}
        ).insert(ignore_permissions=True).name
        self.vehicle = frappe.get_doc(
            {
                "doctype": "Salis Vehicle",
                "plate_number": f"INC {tag}",
                "status": "Active",
                "current_driver": self.driver,
            }
        ).insert(ignore_permissions=True).name

    def _incident(self, incident_type, **overrides):
        data = {
            "doctype": "Vehicle Incident",
            "incident_type": incident_type,
            "vehicle": self.vehicle,
            "incident_date": today(),
            "description": "Test incident",
        }
        data.update(overrides)
        return frappe.get_doc(data).insert(ignore_permissions=True)

    def _card_count(self, card_name):
        # [#4kynzx]
        card = frappe.get_doc("Number Card", card_name)
        return frappe.db.count(card.document_type, json.loads(card.filters_json or "[]"))

    def test_theft_stops_vehicle_and_clears_driver(self):
        inc = self._incident("Theft")
        inc.submit()
        v = frappe.get_doc("Salis Vehicle", self.vehicle)
        self.assertEqual(v.status, "Stopped")
        self.assertFalse(v.current_driver, "theft must clear the current driver")
        self.assertFalse(
            frappe.db.get_value("Salis Driver", self.driver, "current_vehicle"),
            "theft must clear the driver's current vehicle",
        )
        # [#6y3htq]
        inc.reload()
        self.assertEqual(inc.previous_status, "Active")
        self.assertEqual(inc.previous_driver, self.driver)

    def test_theft_increments_open_incident_and_theft_cards(self):
        # [#ofos3i]
        before_incidents = self._card_count("Open Vehicle Incidents")
        before_theft = self._card_count("Open Theft Reports")

        inc = self._incident("Theft")
        inc.submit()
        self.assertEqual(inc.status, "Open", "a submitted theft stays Open for the dashboard")
        self.assertEqual(
            self._card_count("Open Vehicle Incidents"),
            before_incidents + 1,
            "the Open Vehicle Incidents card must count the new theft",
        )
        self.assertEqual(
            self._card_count("Open Theft Reports"),
            before_theft + 1,
            "the Open Theft Reports card must count the new theft",
        )

        # [#s9978y]
        acc = self._incident("Accident", fault="Third party")
        acc.submit()
        self.assertEqual(
            self._card_count("Open Vehicle Incidents"),
            before_incidents + 2,
            "the general card must also count the accident",
        )
        self.assertEqual(
            self._card_count("Open Theft Reports"),
            before_theft + 1,
            "an accident must not change the theft card",
        )

    def test_cancel_theft_restores_vehicle_and_driver(self):
        inc = self._incident("Theft")
        inc.submit()
        inc.cancel()
        v = frappe.get_doc("Salis Vehicle", self.vehicle)
        self.assertEqual(v.status, "Active", "cancel must restore the prior status")
        self.assertEqual(v.current_driver, self.driver, "cancel must restore the driver")

    def test_accident_does_not_change_vehicle(self):
        inc = self._incident("Accident", fault="Third party")
        inc.submit()
        v = frappe.get_doc("Salis Vehicle", self.vehicle)
        self.assertEqual(v.status, "Active", "an accident records the event only")
        self.assertEqual(v.current_driver, self.driver)

    def test_future_dated_incident_rejected(self):
        with self.assertRaises(frappe.ValidationError):
            self._incident("Accident", incident_date=add_days(today(), 1))

    def test_negative_estimated_cost_rejected(self):
        # [#82nrhv]
        with self.assertRaises(frappe.ValidationError):
            self._incident("Accident", fault="Third party", estimated_cost=-100)

    def test_zero_or_positive_estimated_cost_allowed(self):
        # [#2qwohn]
        zero = self._incident("Accident", fault="Third party", estimated_cost=0)
        self.assertTrue(zero.name)
        positive = self._incident("Accident", fault="Third party", estimated_cost=2500)
        self.assertTrue(positive.name)

    def _employee(self):
        """An Active employee to recover from, reusing the site's own if there is one."""
        company = frappe.db.get_value("Company", {}, "name")
        employee = frappe.db.get_value("Employee", {"status": "Active", "company": company})
        if employee:
            return company, employee
        emp = frappe.get_doc(
            {
                "doctype": "Employee",
                "first_name": f"Recovery {frappe.generate_hash(length=12)}",
                "company": company,
                "gender": "Male",
                "date_of_birth": "1990-01-01",
                "date_of_joining": "2020-01-01",
            }
        ).insert(ignore_permissions=True)
        return company, emp.name

    def _recovery_incident(self, **overrides):
        company, employee = self._employee()
        self.company, self.employee = company, employee
        data = {
            "fault": "Driver",
            "estimated_cost": 3000,
            "recover_from_driver": 1,
            "recovery_employee": employee,
            "recovery_amount": 1200,
        }
        data.update(overrides)
        return self._incident("Accident", **data)

    def test_recovery_needs_a_consent_signature_before_approval(self):
        # [#a102cg] A draft may be saved unsigned; the submit that approves it may not.
        inc = self._recovery_incident()
        self.assertTrue(inc.name, "an unsigned recovery must still be saveable as a draft")
        with self.assertRaises(frappe.ValidationError):
            inc.submit()

    def test_recovery_amount_cannot_exceed_the_estimated_cost(self):
        with self.assertRaises(frappe.ValidationError):
            self._recovery_incident(estimated_cost=500, recovery_amount=900)

    def test_agreed_installment_cannot_exceed_the_recovery_amount(self):
        with self.assertRaises(frappe.ValidationError):
            self._recovery_incident(recovery_amount=1000, installment_amount=1500)

    def test_consent_date_is_stamped_with_the_signature(self):
        inc = self._recovery_incident(worker_signature="data:image/png;base64,SIGNED")
        self.assertEqual(inc.signed_on, today(), "the consent date must be stamped on signing")

    def test_public_intake_cannot_self_declare_a_recovery(self):
        # [#a102rf] A Guest report is an event, never a wage-deduction decision.
        _company, employee = self._employee()
        frappe.set_user("Guest")
        try:
            inc = frappe.get_doc(
                {
                    "doctype": "Vehicle Incident",
                    "incident_type": "Accident",
                    "vehicle": self.vehicle,
                    "incident_date": today(),
                    "description": "Public report",
                    "recover_from_driver": 1,
                    "recovery_employee": employee,
                    "recovery_amount": 5000,
                }
            ).insert(ignore_permissions=True)
        finally:
            frappe.set_user("Administrator")
        self.assertFalse(inc.recover_from_driver, "a Guest must not be able to flag a recovery")
        self.assertFalse(inc.recovery_employee)
        self.assertFalse(inc.recovery_amount)

    def test_signed_recovery_maps_once_to_one_employee_advance(self):
        company, _employee = self._employee()
        receivable = frappe.db.get_value(
            "Account", {"company": company, "account_type": "Receivable", "is_group": 0}, "name"
        )
        if not receivable:
            self.skipTest("site has no Receivable account to use as the Employee Advance account")
        frappe.db.set_value("Company", company, "default_employee_advance_account", receivable)

        inc = self._recovery_incident(worker_signature="data:image/png;base64,SIGNED")
        inc.submit()
        inc.reload()
        self.assertTrue(inc.recovery_advance, "an approved recovery must raise an Employee Advance")

        advance = frappe.get_doc("Employee Advance", inc.recovery_advance)
        self.assertEqual(advance.docstatus, 1)
        self.assertEqual(advance.advance_amount, 1200)
        self.assertTrue(
            advance.repay_unclaimed_amount_from_salary,
            "the advance must be marked as recovered from salary",
        )

        # [#a102id] Maps ONCE: the source link is the idempotency key, on both sides.
        self.assertEqual(find_recovery_advance("Vehicle Incident", inc.name), advance.name)
        self.assertEqual(
            raise_recovery_advance(
                source_doctype="Vehicle Incident",
                source_name=inc.name,
                employee=inc.recovery_employee,
                amount=1200,
                purpose="second attempt",
            ),
            advance.name,
            "a repeat raise must return the existing advance, never a second one",
        )
        self.assertEqual(
            frappe.db.count(
                "Employee Advance",
                {"custom_source_doctype": "Vehicle Incident", "custom_source_document": inc.name,
                 "docstatus": ["<", 2]},
            ),
            1,
        )

    def test_recovery_is_a_noop_when_no_advance_account_is_configured(self):
        company, _employee = self._employee()
        frappe.db.set_value("Company", company, "default_employee_advance_account", None)
        inc = self._recovery_incident(worker_signature="data:image/png;base64,SIGNED")
        inc.submit()
        inc.reload()
        self.assertEqual(inc.docstatus, 1, "an unconfigured site must still record the incident")
        self.assertFalse(inc.recovery_advance, "no advance may be raised without an advance account")
