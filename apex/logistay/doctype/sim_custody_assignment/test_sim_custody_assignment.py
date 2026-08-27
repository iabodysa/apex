# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from apex.tests.factories import default_company, make_project, make_supplier


def _contract(company=None):
    doc = frappe.get_doc(
        {
            "doctype": "Telecom Contract",
            "company": company or default_company(),
            "supplier": make_supplier("_T-SCA Supplier"),
            "contract_start_date": today(),
            "contract_end_date": add_days(today(), 365),
            "billing_frequency": "Monthly",
            "recurring_amount": 500,
            "currency": "SAR",
        }
    ).insert(ignore_permissions=True)
    doc.submit()
    return doc


def _sim(**overrides):
    contract = _contract()
    fields = {
        "doctype": "SIM Card",
        "company": contract.company,
        "telecom_contract": contract.name,
        "mobile_number": "05" + frappe.generate_hash(length=8)[:8].translate(
            str.maketrans("abcdef", "012345")
        ),
    }
    fields.update(overrides)
    return frappe.get_doc(fields).insert(ignore_permissions=True).name


def _employee(company=None):
    return frappe.get_doc(
        {
            "doctype": "Employee",
            "first_name": "_T-SCA Holder " + frappe.generate_hash(length=6),
            "date_of_birth": "1990-01-01",
            "date_of_joining": "2020-01-01",
            "gender": "Male",
            "company": company or default_company(),
        }
    ).insert(ignore_permissions=True).name


def _event(sim, action="Assign", **overrides):
    fields = {
        "doctype": "SIM Custody Assignment",
        "company": frappe.db.get_value("SIM Card", sim, "company"),
        "sim_card": sim,
        "action": action,
        "assignment_date": today(),
    }
    if action in ("Assign", "Transfer"):
        fields.setdefault("custodian_type", "Employee")
        fields.setdefault("employee", _employee(fields["company"]))
    fields.update(overrides)
    return frappe.get_doc(fields)


def _assigned(sim, **overrides):
    doc = _event(sim, **overrides).insert(ignore_permissions=True)
    doc.submit()
    return doc


class TestSIMCustodyAssignmentCustodianInputs(FrappeTestCase):
    def test_assigning_without_a_custodian_type_is_refused(self):
        with self.assertRaisesRegex(frappe.ValidationError, "Custodian Type is required"):
            _event(_sim(), custodian_type=None, employee=None).insert(ignore_permissions=True)

    def test_an_employee_custodian_without_an_employee_is_refused(self):
        with self.assertRaisesRegex(frappe.ValidationError, "Employee receiving the SIM"):
            _event(_sim(), custodian_type="Employee", employee=None).insert(
                ignore_permissions=True
            )

    def test_a_project_custodian_without_a_project_is_refused(self):
        with self.assertRaisesRegex(frappe.ValidationError, "Project receiving the SIM"):
            _event(_sim(), custodian_type="Project", employee=None, project=None).insert(
                ignore_permissions=True
            )

    def test_an_employee_custodian_drops_any_project_that_was_typed(self):
        doc = _event(
            _sim(), custodian_type="Employee", project=make_project("_T-SCA Project")
        ).insert(ignore_permissions=True)
        self.assertFalse(doc.project)

    def test_a_project_custodian_drops_any_employee_that_was_typed(self):
        doc = _event(
            _sim(),
            custodian_type="Project",
            project=make_project("_T-SCA Project"),
        ).insert(ignore_permissions=True)
        self.assertFalse(doc.employee)

    def test_a_return_carries_no_custodian_at_all(self):
        sim = _sim()
        _assigned(sim)
        doc = _event(sim, action="Return", custodian_type="Employee").insert(
            ignore_permissions=True
        )
        self.assertFalse(doc.custodian_type)
        self.assertFalse(doc.employee)


class TestSIMCustodyAssignmentRetirementReason(FrappeTestCase):
    def test_recording_a_sim_lost_without_a_reason_is_refused(self):
        with self.assertRaisesRegex(frappe.ValidationError, "Reason is required"):
            _event(_sim(), action="Lost").insert(ignore_permissions=True)

    def test_terminating_a_sim_without_a_reason_is_refused(self):
        with self.assertRaisesRegex(frappe.ValidationError, "Reason is required"):
            _event(_sim(), action="Terminated").insert(ignore_permissions=True)

    def test_a_reason_of_blanks_is_no_reason(self):
        with self.assertRaisesRegex(frappe.ValidationError, "Reason is required"):
            _event(_sim(), action="Lost", reason="   ").insert(ignore_permissions=True)

    def test_a_reason_lets_the_retirement_through(self):
        doc = _event(_sim(), action="Lost", reason="_T-SCA stolen").insert(
            ignore_permissions=True
        )
        self.assertEqual(doc.action, "Lost")


class TestSIMCustodyAssignmentPriorStatus(FrappeTestCase):
    def test_a_second_assign_on_an_assigned_sim_is_refused(self):
        sim = _sim()
        _assigned(sim)
        with self.assertRaisesRegex(frappe.ValidationError, "expected"):
            _event(sim).insert(ignore_permissions=True)

    def test_transferring_an_available_sim_is_refused(self):
        with self.assertRaisesRegex(frappe.ValidationError, "expected"):
            _event(_sim(), action="Transfer").insert(ignore_permissions=True)

    def test_returning_an_available_sim_is_refused(self):
        with self.assertRaisesRegex(frappe.ValidationError, "expected"):
            _event(_sim(), action="Return").insert(ignore_permissions=True)

    def test_reactivating_a_sim_that_was_never_suspended_is_refused(self):
        with self.assertRaisesRegex(frappe.ValidationError, "expected"):
            _event(_sim(), action="Reactivate").insert(ignore_permissions=True)

    def test_transferring_an_assigned_sim_is_accepted(self):
        sim = _sim()
        _assigned(sim)
        doc = _assigned(sim, action="Transfer")
        self.assertEqual(doc.action, "Transfer")


class TestSIMCustodyAssignmentBackDating(FrappeTestCase):
    def test_an_event_dated_before_the_last_one_is_refused(self):
        sim = _sim()
        _assigned(sim)
        with self.assertRaisesRegex(frappe.ValidationError, "before SIM"):
            _event(
                sim, action="Return", assignment_date=add_days(today(), -1)
            ).insert(ignore_permissions=True)

    def test_an_event_dated_on_the_same_day_is_accepted(self):
        sim = _sim()
        _assigned(sim)
        doc = _event(sim, action="Return").insert(ignore_permissions=True)
        self.assertEqual(str(doc.assignment_date), today())


class TestSIMCustodyAssignmentCompanyCompatibility(FrappeTestCase):
    def test_an_employee_of_another_company_cannot_hold_the_sim(self):
        other = frappe.get_doc(
            {
                "doctype": "Company",
                "company_name": "_T-SCA Other " + frappe.generate_hash(length=6),
                "default_currency": "SAR",
                "country": "Saudi Arabia",
            }
        ).insert(ignore_permissions=True).name
        with self.assertRaisesRegex(frappe.ValidationError, "belongs to company"):
            _event(_sim(), employee=_employee(other)).insert(ignore_permissions=True)


class TestSIMCustodyAssignmentProjection(FrappeTestCase):
    def test_submitting_an_assignment_moves_the_card_to_assigned(self):
        sim = _sim()
        doc = _assigned(sim)
        card = frappe.db.get_value(
            "SIM Card",
            sim,
            ["status", "current_custodian_employee", "current_assignment"],
            as_dict=True,
        )
        self.assertEqual(card.status, "Assigned")
        self.assertEqual(card.current_custodian_employee, doc.employee)
        self.assertEqual(card.current_assignment, doc.name)

    def test_returning_the_sim_empties_the_custody(self):
        sim = _sim()
        _assigned(sim)
        _assigned(sim, action="Return")
        card = frappe.db.get_value(
            "SIM Card", sim, ["status", "current_custodian_employee"], as_dict=True
        )
        self.assertEqual(card.status, "Available")
        self.assertFalse(card.current_custodian_employee)

    def test_suspending_holds_the_custodian_and_marks_the_card_suspended(self):
        sim = _sim()
        doc = _assigned(sim)
        _assigned(sim, action="Suspend")
        card = frappe.db.get_value(
            "SIM Card", sim, ["status", "current_custodian_employee"], as_dict=True
        )
        self.assertEqual(card.status, "Suspended")
        self.assertEqual(card.current_custodian_employee, doc.employee)

    def test_reactivating_returns_the_card_to_its_held_state(self):
        sim = _sim()
        _assigned(sim)
        _assigned(sim, action="Suspend")
        _assigned(sim, action="Reactivate")
        self.assertEqual(frappe.db.get_value("SIM Card", sim, "status"), "Assigned")

    def test_a_terminal_event_empties_the_custody_and_names_the_end(self):
        sim = _sim()
        _assigned(sim)
        _assigned(sim, action="Lost", reason="_T-SCA stolen")
        card = frappe.db.get_value(
            "SIM Card", sim, ["status", "current_custodian_employee"], as_dict=True
        )
        self.assertEqual(card.status, "Lost")
        self.assertFalse(card.current_custodian_employee)

    def test_the_previous_custodian_is_remembered_on_the_event(self):
        sim = _sim()
        first = _assigned(sim)
        second = _assigned(sim, action="Transfer")
        self.assertEqual(second.previous_custodian_employee, first.employee)

    def test_cancelling_an_event_rebuilds_the_card_without_it(self):
        sim = _sim()
        doc = _assigned(sim)
        doc.cancel()
        self.assertEqual(frappe.db.get_value("SIM Card", sim, "status"), "Available")
