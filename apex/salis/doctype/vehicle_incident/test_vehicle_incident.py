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

    def _assert_raised_by_the_controller_guard(self, ctx, needle):
        """The exception must come from the controller's own guard.

        ``LinkValidationError`` SUBCLASSES ``ValidationError`` and Frappe's link
        check (``_validate_links``) runs BEFORE ``validate()``, so a bare
        ``assertRaises(ValidationError)`` can pass while the guard under test never
        executes. Pinning the message (and excluding the link error outright) is
        what makes these assertions mean something.
        """
        self.assertNotIsInstance(
            ctx.exception,
            frappe.exceptions.LinkValidationError,
            "a link check satisfied this assertion — the guard under test never ran",
        )
        self.assertIn(needle, str(ctx.exception))

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
        with self.assertRaises(frappe.ValidationError) as cm:
            self._incident("Accident", incident_date=add_days(today(), 1))
        self._assert_raised_by_the_controller_guard(cm, "Incident date cannot be in the future")

    def test_negative_estimated_cost_rejected(self):
        # [#82nrhv]
        with self.assertRaises(frappe.ValidationError) as cm:
            self._incident("Accident", fault="Third party", estimated_cost=-100)
        self._assert_raised_by_the_controller_guard(cm, "Estimated cost cannot be negative")

    def test_zero_or_positive_estimated_cost_allowed(self):
        # [#2qwohn]
        zero = self._incident("Accident", fault="Third party", estimated_cost=0)
        self.assertTrue(zero.name)
        positive = self._incident("Accident", fault="Third party", estimated_cost=2500)
        self.assertTrue(positive.name)

    def _company(self):
        """The site's company, created when the site has none — never a skip."""
        existing = frappe.db.get_value("Company", {}, "name")
        if existing:
            return existing
        tag = frappe.generate_hash(length=12)
        return frappe.get_doc(
            {
                "doctype": "Company",
                "company_name": f"Incident Recovery {tag}",
                # Full hash, never a slice: a narrowed random identifier is what
                # apex/tests/test_fixture_identifier_entropy.py forbids.
                "abbr": f"IR{tag}",
                "default_currency": "SAR",
                "country": "Saudi Arabia",
            }
        ).insert(ignore_permissions=True).name

    def _receivable_account(self, company):
        """A non-group Receivable account, created when the chart of accounts has
        none. HRMS refuses to submit an Employee Advance on any other account
        type, so this is the prerequisite the recovery path actually needs."""
        existing = frappe.db.get_value(
            "Account",
            {"company": company, "account_type": "Receivable", "is_group": 0},
            "name",
        )
        if existing:
            return existing
        parent = frappe.db.get_value(
            "Account", {"company": company, "is_group": 1, "root_type": "Asset"}, "name"
        )
        self.assertTrue(parent, f"company {company} has no Asset group account")
        return frappe.get_doc(
            {
                "doctype": "Account",
                "account_name": f"Incident Advances {frappe.generate_hash(length=12)}",
                "company": company,
                "parent_account": parent,
                "root_type": "Asset",
                "account_type": "Receivable",
                "is_group": 0,
            }
        ).insert(ignore_permissions=True).name

    def _configure_advance_account(self):
        """Point the company at a Receivable Employee Advance Account and put the
        previous value back afterwards, so one test cannot reconfigure another."""
        company = self._company()
        previous = frappe.db.get_value(
            "Company", company, "default_employee_advance_account"
        )
        self.addCleanup(
            frappe.db.set_value,
            "Company",
            company,
            "default_employee_advance_account",
            previous,
        )
        frappe.db.set_value(
            "Company",
            company,
            "default_employee_advance_account",
            self._receivable_account(company),
        )
        return company

    def _employee(self):
        """An Active employee to recover from, reusing the site's own if there is one."""
        company = self._company()
        employee = frappe.db.get_value("Employee", {"status": "Active", "company": company})
        if employee:
            return company, employee
        emp = frappe.get_doc(
            {
                "doctype": "Employee",
                "first_name": f"Recovery {frappe.generate_hash(length=12)}",
                "company": company,
                "status": "Active",
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
        """[#a102cg] KSA Labor Law: the worker's written consent is required
        before a wage may be touched. A draft may be saved unsigned so the
        signature can be collected after the case is opened; the submit that
        APPROVES the recovery may not."""
        inc = self._recovery_incident()
        self.assertTrue(inc.name, "an unsigned recovery must still be saveable as a draft")
        self.assertFalse(inc.worker_signature)
        with self.assertRaises(frappe.ValidationError) as cm:
            inc.submit()
        self._assert_raised_by_the_controller_guard(
            cm, "consent signature is required before a cost recovery can be approved"
        )
        self.assertEqual(
            frappe.db.get_value("Vehicle Incident", inc.name, "docstatus"),
            0,
            "an unsigned recovery must stay a draft",
        )
        self.assertEqual(
            frappe.db.count(
                "Employee Advance",
                {"custom_source_doctype": "Vehicle Incident", "custom_source_document": inc.name},
            ),
            0,
            "no receivable may be raised before consent is recorded",
        )

    def test_a_signed_recovery_passes_the_same_consent_gate(self):
        """Non-vacuity for the gate above: the identical document submits once
        the signature is present, so the rejection is about consent and nothing
        else."""
        self._configure_advance_account()
        inc = self._recovery_incident(worker_signature="data:image/png;base64,SIGNED")
        inc.submit()
        self.assertEqual(inc.docstatus, 1)

    def test_recovery_amount_cannot_exceed_the_estimated_cost(self):
        with self.assertRaises(frappe.ValidationError) as cm:
            self._recovery_incident(estimated_cost=500, recovery_amount=900)
        self._assert_raised_by_the_controller_guard(
            cm, "Amount to Recover cannot exceed the estimated cost"
        )

    def test_agreed_installment_cannot_exceed_the_recovery_amount(self):
        with self.assertRaises(frappe.ValidationError) as cm:
            self._recovery_incident(recovery_amount=1000, installment_amount=1500)
        self._assert_raised_by_the_controller_guard(
            cm, "Agreed Installment cannot exceed the Amount to Recover"
        )

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
        # The Receivable Employee Advance Account is BUILT here rather than
        # skipped over: an earlier version called skipTest when the chart of
        # accounts had none, which reported green while proving nothing.
        self._configure_advance_account()

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
        previous = frappe.db.get_value(
            "Company", company, "default_employee_advance_account"
        )
        self.addCleanup(
            frappe.db.set_value,
            "Company",
            company,
            "default_employee_advance_account",
            previous,
        )
        frappe.db.set_value("Company", company, "default_employee_advance_account", None)
        inc = self._recovery_incident(worker_signature="data:image/png;base64,SIGNED")
        inc.submit()
        inc.reload()
        self.assertEqual(inc.docstatus, 1, "an unconfigured site must still record the incident")
        self.assertFalse(inc.recovery_advance, "no advance may be raised without an advance account")

    def _approved_recovery(self):
        """A submitted, consented recovery incident and the ONE advance it raised."""
        self._configure_advance_account()
        inc = self._recovery_incident(worker_signature="data:image/png;base64,SIGNED")
        inc.submit()
        inc.reload()
        self.assertTrue(inc.recovery_advance, "an approved recovery must raise an Employee Advance")
        self.assertEqual(
            frappe.db.get_value("Employee Advance", inc.recovery_advance, "docstatus"), 1
        )
        return inc

    def test_cancelling_the_incident_reverses_the_receivable(self):
        """[#a102rv] The mirror of submit: cancelling the incident cancels the
        Employee Advance, which reverses the receivable natively (HRMS reverses
        each linked Additional Salary's contribution on its own cancel)."""
        inc = self._approved_recovery()
        advance = inc.recovery_advance

        inc.cancel()

        self.assertEqual(
            frappe.db.get_value("Employee Advance", advance, "docstatus"),
            2,
            "cancelling the incident must reverse the receivable it raised",
        )
        self.assertEqual(frappe.db.get_value("Employee Advance", advance, "status"), "Cancelled")
        self.assertEqual(
            frappe.db.count(
                "Employee Advance",
                {
                    "custom_source_doctype": "Vehicle Incident",
                    "custom_source_document": inc.name,
                    "docstatus": ["<", 2],
                },
            ),
            0,
            "no live receivable may survive the cancellation",
        )
        self.assertIsNone(
            find_recovery_advance("Vehicle Incident", inc.name),
            "the mapping key is the NON-cancelled advance, so a reversed one must "
            "stop claiming its source document",
        )

    def test_cancelling_is_blocked_once_the_advance_carries_a_recovered_amount(self):
        """Once real money has moved — the company has paid, or an installment has
        been recovered — reversing is an accounting decision, so the cancel is
        refused rather than silently unwinding a posted balance."""
        inc = self._approved_recovery()
        advance = inc.recovery_advance
        frappe.db.set_value("Employee Advance", advance, "paid_amount", 500)

        with self.assertRaises(frappe.ValidationError) as cm:
            inc.cancel()
        self._assert_raised_by_the_controller_guard(
            cm, "already carries a paid or recovered amount"
        )
        self.assertEqual(
            frappe.db.get_value("Employee Advance", advance, "docstatus"),
            1,
            "the receivable must stay submitted when the cancel is refused",
        )

    def test_an_amendment_raises_its_own_single_advance(self):
        """A cancelled recovery does not lock the case out: the amendment is a new
        source document and maps once to its own single advance, so there is still
        exactly one LIVE receivable for the case."""
        inc = self._approved_recovery()
        original_advance = inc.recovery_advance
        inc.cancel()

        amended = frappe.copy_doc(inc)
        amended.amended_from = inc.name
        self.assertFalse(
            amended.recovery_advance,
            "the source link is no_copy, so an amendment must start unmapped",
        )
        self.assertFalse(
            amended.worker_signature,
            "the signature is no_copy: consent must be collected again for a new approval",
        )
        amended.worker_signature = "data:image/png;base64,SIGNED"
        amended.insert(ignore_permissions=True)
        amended.submit()
        amended.reload()

        self.assertTrue(amended.recovery_advance)
        self.assertNotEqual(amended.recovery_advance, original_advance)
        self.assertEqual(
            find_recovery_advance("Vehicle Incident", amended.name), amended.recovery_advance
        )
        self.assertEqual(
            frappe.db.count(
                "Employee Advance",
                {
                    "custom_source_doctype": "Vehicle Incident",
                    "custom_source_document": ["in", [inc.name, amended.name]],
                    "docstatus": ["<", 2],
                },
            ),
            1,
            "exactly one LIVE advance across the cancelled original and its amendment",
        )
