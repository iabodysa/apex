# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Vehicle Incident controller.

Proves the theft side effects and their reversal, that an accident records the
event without touching vehicle state, that a future-dated incident is rejected,
and that driver cost recovery is consent-gated and maps to exactly one
native HRMS Employee Advance.

The vehicle and its rider are the shipped fixtures rather than a fresh pair per case —
a fresh pair for each of the twenty-one cases here would mint forty-two records just to
hang an incident off. Each case hands the pair back: every incident it submitted is
cancelled and the two links are cleared.
"""

from __future__ import annotations

import json
from pathlib import Path

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

import apex
from apex.apex_core.utils.employee_recovery import find_recovery_advance, raise_recovery_advance
from unittest import TestCase
from unittest.mock import MagicMock, patch
from apex.salis.api import fleet_os
from apex.salis.doctype.vehicle_incident import vehicle_incident

_INCIDENT_JSON = Path(apex.__file__).resolve().parent / "salis" / "doctype" / "vehicle_incident" / "vehicle_incident.json"

PLATE = "_T ABC 1001"
DRIVER_NAME = "_Test Driver"

OPERATING_ROLES = {"Fleet Supervisor", "Fleet Project Manager", "Fleet Manager", "System Manager"}
AUDIT_ROLES = {"Internal Auditor", "Government Relations Officer"}
OPERATING_ROLE = "Fleet Manager"
AUDIT_ROLE = "Internal Auditor"

_CONSENT = "data:image/png;base64,iVBORw0KGgo="

class TestVehicleIncident(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.driver = frappe.db.get_value("Salis Driver", {"full_name": DRIVER_NAME}, "name")
        self.vehicle = frappe.db.get_value("Salis Vehicle", {"plate_number": PLATE}, "name")
        self.addCleanup(self._restore)
        frappe.db.set_value("Salis Vehicle", self.vehicle, "current_driver", self.driver)

    def _restore(self):
        """Take every incident this case filed off the borrowed vehicle and clear the two
        links it wrote. A recovery advance that already carries a paid amount refuses the
        cancel by design, so the amount is cleared first — teardown must undo the fixture,
        not re-litigate the guard the case just proved."""
        for name in frappe.get_all(
            "Vehicle Incident", filters={"vehicle": self.vehicle, "docstatus": 1}, pluck="name"
        ):
            doc = frappe.get_doc("Vehicle Incident", name)
            if doc.recovery_advance:
                frappe.db.set_value("Employee Advance", doc.recovery_advance, "paid_amount", 0)
            doc.cancel()
        frappe.db.set_value(
            "Salis Vehicle", self.vehicle, {"status": "Active", "current_driver": None}
        )
        frappe.db.set_value("Salis Driver", self.driver, "current_vehicle", None)

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
        inc.reload()
        self.assertEqual(inc.previous_status, "Active")
        self.assertEqual(inc.previous_driver, self.driver)

    def test_theft_increments_open_incident_and_theft_cards(self):
        before_incidents = self._card_count("Open Vehicle Incidents")
        before_theft = self._card_count("Open Theft Reports")

        inc = self._incident("Theft")
        inc.submit()
        self.assertEqual(
            inc.status, "Under Review", "a submitted theft opens as a case under review"
        )
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
        with self.assertRaises(frappe.ValidationError) as cm:
            self._incident("Accident", fault="Third party", estimated_cost=-100)
        self._assert_raised_by_the_controller_guard(cm, "Estimated cost cannot be negative")

    def test_zero_or_positive_estimated_cost_allowed(self):
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
        """KSA Labor Law: the worker's written consent is required
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
        """The mirror of submit: cancelling the incident cancels the
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
        refused rather than silently unwinding a posted balance.

        The refusal fires in before_cancel, which Frappe runs from
        run_before_save_methods() BEFORE db_update() stamps docstatus 2
        (frappe/model/document.py:414 vs :428, and :431 dispatches on_cancel after
        the write). Raised from on_cancel instead, the 2 is already in the open
        transaction and every read for the rest of the request sees the incident as
        cancelled — only the request-level rollback undoes it.

        Graded on the ROW plus a reload, never on the attribute: Document._cancel()
        assigns self.docstatus = 2 (:1085) before save() is ever called, so
        inc.docstatus reads 2 after ANY blocked cancel and proves nothing about
        which hook refused.
        """
        inc = self._approved_recovery()
        advance = inc.recovery_advance
        frappe.db.set_value("Employee Advance", advance, "paid_amount", 500)

        with self.assertRaises(frappe.ValidationError) as cm:
            inc.cancel()
        self._assert_raised_by_the_controller_guard(
            cm, "already carries a paid or recovered amount"
        )
        self.assertEqual(
            frappe.db.get_value("Vehicle Incident", inc.name, "docstatus"),
            1,
            "a refused cancel must leave the incident submitted, not cancelled-in-the-row",
        )
        inc.reload()
        self.assertEqual(
            inc.docstatus,
            1,
            "reloading the incident in the same request must still read it as submitted",
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

        amended = frappe.copy_doc(inc, ignore_no_copy=False)
        amended.amended_from = inc.name
        amended.docstatus = 0
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

    def _user_with_role(self, role):
        return frappe.get_doc({
            "doctype": "User",
            "email": f"vi_{frappe.generate_hash(length=12)}@example.com",
            "first_name": role.split()[0],
            "roles": [{"role": role}],
        }).insert(ignore_permissions=True).name

    def test_the_consent_signature_is_level_one_for_the_operating_roles_only(self):
        """The shipped JSON, checked rather than trusted.

        A permlevel-1 row is NOT a duplicate of the same role's permlevel-0 row:
        `is_perm_applicable` keeps only permlevel-0 rows (frappe/permissions.py:284), so
        the two answer different questions, and rows are counted on the (role, permlevel)
        PAIR. Every one of them carries WRITE as well as read -- the create-path test
        below is what that half is for.
        """
        shipped = json.loads(_INCIDENT_JSON.read_text(encoding="utf-8"))
        rows = shipped["permissions"]

        signature = [f for f in shipped["fields"] if f["fieldname"] == "worker_signature"][0]
        self.assertEqual(
            signature.get("permlevel"), 1,
            "the consent signature is back at level 0, readable by every role that can "
            "open the incident",
        )

        high = {p["role"] for p in rows if int(p.get("permlevel") or 0) == 1}
        self.assertEqual(
            high, OPERATING_ROLES,
            "the permlevel-1 role set changed. Adding a role hands it every worker's "
            "captured consent mark; removing one silently blanks the consent that role "
            "is the one to capture.",
        )
        for role in sorted(high):
            row = [p for p in rows if p["role"] == role and int(p.get("permlevel") or 0) == 1]
            self.assertEqual(len(row), 1, f"{role}: expected exactly one permlevel-1 row")
            self.assertEqual(row[0].get("read"), 1, f"{role}: permlevel-1 read missing")
            self.assertEqual(
                row[0].get("write"), 1,
                f"{role}: permlevel-1 write missing -- the consent would be blanked on "
                "every incident this role opens",
            )

        for role in sorted(AUDIT_ROLES):
            self.assertNotIn(
                role, high,
                f"{role} holds a permlevel-1 row -- that hands back the exact biometric "
                "mark this change exists to keep from it",
            )
            zero = [p for p in rows if p["role"] == role and int(p.get("permlevel") or 0) == 0]
            self.assertEqual(len(zero), 1, f"{role}: its level-0 row was moved or duplicated")
            self.assertEqual(
                zero[0].get("read"), 1,
                f"{role} lost its read on the incident -- this change narrows one field, "
                "not the audit grant",
            )

    def test_an_audit_role_reads_the_consent_concealed_and_a_fleet_role_does_not(self):
        """THE PAIR. Both verdicts in one method so they cannot drift, and compared as
        VERDICTS ALONE at the end. Comparing (role, value) tuples can never be equal --
        the role names are different literals -- so such a pair passes even with the
        permlevel removed entirely.

        Asserted through `frappe.client.get`, because that is where the read strip lives
        (frappe/client.py:110). An in-process `frappe.get_doc` does NOT strip, so
        asserting on the raw document would prove nothing about what the auditor receives.
        """
        self.addCleanup(frappe.set_user, "Administrator")
        inc = self._recovery_incident(worker_signature=_CONSENT)
        self.assertEqual(inc.worker_signature, _CONSENT, "precondition: the fixture is signed")
        auditor = self._user_with_role(AUDIT_ROLE)
        fleet = self._user_with_role(OPERATING_ROLE)

        frappe.set_user(fleet)
        self.assertIn(
            1, frappe.get_doc("Vehicle Incident", inc.name).get_permlevel_access("read"),
            f"{OPERATING_ROLE} lost its permlevel-1 read row",
        )
        frappe.set_user(auditor)
        self.assertNotIn(
            1, frappe.get_doc("Vehicle Incident", inc.name).get_permlevel_access("read"),
            f"{AUDIT_ROLE} reaches permlevel 1 -- its fleet-wide read is back on the "
            "worker's captured consent",
        )

        frappe.set_user(auditor)
        audited = frappe.client.get("Vehicle Incident", inc.name)
        frappe.set_user(fleet)
        at_desk = frappe.client.get("Vehicle Incident", inc.name)

        self.assertFalse(
            audited.get("worker_signature"),
            f"{AUDIT_ROLE} can still read the worker's captured consent mark",
        )
        self.assertEqual(
            audited.get("recovery_amount"), inc.recovery_amount,
            "the level-0 recovery facts must survive the strip -- the auditor is still "
            "auditing the deduction",
        )
        self.assertEqual(
            at_desk.get("worker_signature"), _CONSENT,
            f"{OPERATING_ROLE} lost the consent it has to be able to produce on demand",
        )

        audit_verdict = "visible" if audited.get("worker_signature") else "concealed"
        fleet_verdict = "visible" if at_desk.get("worker_signature") else "concealed"
        self.assertNotEqual(
            audit_verdict, fleet_verdict,
            f"both roles produced the same verdict ({audit_verdict}) -- the pair collapsed: "
            "either the permlevel stopped being enforced for anyone, or it is now enforced "
            f"against {OPERATING_ROLE} too",
        )

    def test_the_create_path_keeps_the_consent_signature_for_a_fleet_role(self):
        """Why every level-1 row here carries WRITE and not merely read.

        On a NEW document `reset_values_if_no_permlevel_access` takes its reference from
        `frappe.new_doc` rather than from the stored row
        (frappe/model/base_document.py:1277-1279), so a field the caller holds no level-1
        write row for is set to the field DEFAULT -- empty. Not refused, not raised:
        silently emptied, while the controller stamps `signed_on` beside it, filing an
        incident that claims consent and holds none. A read-only level-1 row on a field a
        create path writes is data loss before it is privacy.

        `validate_higher_perm_levels` is the exact call `insert` makes
        (frappe/model/document.py:306), so the outcome is about the permlevel and not
        about the link permissions a full insert would also need.
        """
        self.addCleanup(frappe.set_user, "Administrator")
        fleet = self._user_with_role(OPERATING_ROLE)
        auditor = self._user_with_role(AUDIT_ROLE)

        def surviving_consent(as_user):
            frappe.set_user(as_user)
            fresh = frappe.get_doc({
                "doctype": "Vehicle Incident",
                "incident_type": "Accident",
                "vehicle": self.vehicle,
                "incident_date": today(),
                "description": "Consent captured at the scene",
                "recover_from_driver": 1,
                "recovery_amount": 1200,
                "worker_signature": _CONSENT,
            })
            fresh.set("__islocal", True)
            self.assertTrue(fresh.is_new(), "precondition: the create path needs a NEW doc")
            fresh.validate_higher_perm_levels()
            return fresh.worker_signature

        kept = surviving_consent(fleet)
        blanked = surviving_consent(auditor)

        self.assertEqual(
            kept, _CONSENT,
            f"{OPERATING_ROLE} lost the consent on the CREATE path -- the fleet would file "
            "recoveries stamped as signed with nothing behind them",
        )
        self.assertFalse(
            blanked,
            "a role with no permlevel-1 write row kept a consent mark it cannot reach on "
            "create",
        )
        kept_verdict = "kept" if kept else "blanked"
        blanked_verdict = "kept" if blanked else "blanked"
        self.assertNotEqual(
            kept_verdict, blanked_verdict,
            f"both roles produced the same verdict ({kept_verdict}) -- this pair no longer "
            "distinguishes a role that holds the level-1 write row from one that does not",
        )

test_dependencies = ['Salis Vehicle', 'Salis Driver']

def _raising_frappe() -> MagicMock:
    fake = MagicMock()
    fake.PermissionError = frappe.PermissionError

    def throw(message, exc=None, **_kwargs):
        raise (exc or frappe.ValidationError)(message)

    fake.throw.side_effect = throw
    return fake
def _call(endpoint, *args, **kwargs):
    return getattr(endpoint, "__wrapped__", endpoint)(*args, **kwargs)
class TestVehicleIncidentLifecycle(TestCase):
    def test_new_incident_is_open_and_direct_status_edit_is_refused(self):
        fake = _raising_frappe()
        new_doc = MagicMock(status="Closed")
        new_doc.is_new.return_value = True

        existing = MagicMock(status="Closed")
        existing.is_new.return_value = False
        existing.has_value_changed.return_value = True

        with (
            patch.object(vehicle_incident, "frappe", fake),
            patch.object(vehicle_incident, "_", side_effect=lambda message: message),
        ):
            vehicle_incident.VehicleIncident._guard_status(new_doc)
            with self.assertRaises(frappe.PermissionError):
                vehicle_incident.VehicleIncident._guard_status(existing)

        self.assertEqual(new_doc.status, "Open")

    def test_submit_and_cancel_use_canonical_statuses(self):
        submitted = MagicMock(incident_type="Accident")
        cancelled = MagicMock(incident_type="Accident")

        vehicle_incident.VehicleIncident.on_submit(submitted)
        vehicle_incident.VehicleIncident.on_cancel(cancelled)

        submitted.db_set.assert_called_once_with("status", "Under Review")
        cancelled.db_set.assert_called_once_with("status", "Closed")

    def test_close_requires_write_permission_and_resolution(self):
        doc = MagicMock(docstatus=1, status="Under Review")
        doc.name = "VI-1"
        doc.vehicle = "VEH-1"
        doc.check_permission.side_effect = frappe.PermissionError("denied")
        fake = _raising_frappe()
        fake.get_doc.return_value = doc

        with (
            patch.object(vehicle_incident, "frappe", fake),
            patch.object(vehicle_incident, "_", side_effect=lambda message: message),
        ):
            with self.assertRaises(frappe.ValidationError):
                _call(vehicle_incident.close_incident, "VI-1", "  ")
            with self.assertRaises(frappe.PermissionError):
                _call(vehicle_incident.close_incident, "VI-1", "Repair completed")

        doc.db_set.assert_not_called()

    def test_close_transitions_under_review_and_writes_timeline(self):
        doc = MagicMock(docstatus=1, status="Under Review")
        doc.name = "VI-1"
        doc.vehicle = "VEH-1"
        fake = _raising_frappe()
        fake.get_doc.return_value = doc

        with (
            patch.object(vehicle_incident, "frappe", fake),
            patch.object(vehicle_incident, "_", side_effect=lambda message: message),
            patch.object(vehicle_incident, "add_timeline_note") as add_note,
        ):
            result = _call(vehicle_incident.close_incident, "VI-1", "Repair completed")

        fake.get_doc.assert_called_once_with(
            "Vehicle Incident", "VI-1", for_update=True
        )
        doc.db_set.assert_called_once_with("status", "Closed")
        self.assertIn("Repair completed", doc.add_comment.call_args.args[1])
        add_note.assert_called_once()
        self.assertEqual(result, {"name": "VI-1", "status": "Closed"})

    def test_fleet_recovery_reuses_incident_close_transition(self):
        incident = frappe._dict(
            name="VI-1",
            previous_driver=None,
            previous_status="Active",
        )
        fake = MagicMock()
        fake.db.get_value.side_effect = [incident]

        with (
            patch.object(fleet_os, "frappe", fake),
            patch.object(fleet_os, "_", side_effect=lambda message: message),
            patch.object(fleet_os, "_resolve_plate", return_value="VEH-1"),
            patch.object(fleet_os, "lock_vehicle"),
            patch.object(fleet_os, "_close_open_suspension"),
            patch.object(fleet_os, "_publish_fleet_update"),
            patch.object(
                fleet_os, "close_incident_internal", create=True
            ) as close_incident,
        ):
            result = _call(fleet_os.recover, "1234")

        close_incident.assert_called_once_with(
            "VI-1",
            "Vehicle recovered through Fleet OS.",
            check_permission=False,
        )
        self.assertEqual(result, {"ok": True, "incident": "VI-1"})
class TestVehicleIncidentMetadata(TestCase):
    def test_status_is_read_only_and_cancelled_is_not_a_parallel_state(self):
        metadata = json.loads(
            Path(__file__)
            .with_name("vehicle_incident.json")
            .read_text(encoding="utf-8")
        )
        status = next(
            field for field in metadata["fields"] if field["fieldname"] == "status"
        )
        self.assertEqual(
            status["options"].splitlines(), ["Open", "Under Review", "Closed"]
        )
        self.assertTrue(status["read_only"])
        self.assertNotIn("Cancelled", {state["title"] for state in metadata["states"]})
