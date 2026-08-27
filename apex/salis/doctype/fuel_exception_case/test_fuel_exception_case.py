# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.model.workflow import WorkflowTransitionError, apply_workflow
from frappe.tests.utils import FrappeTestCase


def _user(first_name):
    email = "_t_fec_" + frappe.generate_hash(length=6) + "@example.com"
    frappe.get_doc(
        {
            "doctype": "User",
            "email": email,
            "first_name": first_name,
            "send_welcome_email": 0,
        }
    ).insert(ignore_permissions=True)
    return email


def _case(**overrides):
    fields = {
        "doctype": "Fuel Exception Case",
        "exception_type": "Over-Consumption",
        "description": "_T-FuelExceptionCase " + frappe.generate_hash(length=6),
    }
    fields.update(overrides)
    return frappe.get_doc(fields)


def _under_investigation(**overrides):
    doc = _case(**overrides).insert(ignore_permissions=True)
    apply_workflow(doc, "Start Investigation")
    return doc


class TestFuelExceptionCaseOpensOpen(FrappeTestCase):
    def test_a_case_created_at_a_later_status_is_refused(self):
        with self.assertRaisesRegex(frappe.ValidationError, "must be created with status Open"):
            _case(status="Under Investigation").insert(ignore_permissions=True)

    def test_a_case_created_open_is_accepted(self):
        doc = _case().insert(ignore_permissions=True)
        self.assertEqual(doc.status, "Open")


class TestFuelExceptionCaseReporter(FrappeTestCase):
    def test_a_case_with_no_reporter_names_the_session_user(self):
        doc = _case(reported_by=None).insert(ignore_permissions=True)
        self.assertEqual(doc.reported_by, frappe.session.user)


class TestFuelExceptionCaseClosure(FrappeTestCase):
    def test_resolving_without_any_evidence_is_refused(self):
        doc = _under_investigation(reported_by=_user("_T-FEC Reporter"))
        with self.assertRaisesRegex(frappe.ValidationError, "Evidence required"):
            apply_workflow(doc, "Resolve")

    def test_the_workflow_offers_no_resolve_to_the_person_who_raised_the_case(self):
        doc = _under_investigation(reported_by=frappe.session.user)
        doc.evidence_notes = "_T-Meter photo attached"
        doc.save(ignore_permissions=True)
        with self.assertRaises(WorkflowTransitionError):
            apply_workflow(doc, "Resolve")

    def test_the_closer_cannot_be_the_person_who_raised_the_case(self):
        doc = _under_investigation(reported_by=frappe.session.user)
        doc.evidence_notes = "_T-Meter photo attached"
        doc.status = "Resolved"
        with self.assertRaisesRegex(frappe.ValidationError, "closer must differ"):
            doc.save(ignore_permissions=True)

    def test_a_resolution_by_a_second_person_stamps_the_closer(self):
        doc = _under_investigation(reported_by=_user("_T-FEC Reporter"))
        doc.evidence_notes = "_T-Meter photo attached"
        doc.save(ignore_permissions=True)
        apply_workflow(doc, "Resolve")
        self.assertEqual(doc.closed_by, frappe.session.user)

    def test_an_investigation_without_evidence_is_untouched_by_the_closure_rule(self):
        doc = _under_investigation(reported_by=_user("_T-FEC Reporter"))
        self.assertEqual(doc.status, "Under Investigation")
        self.assertFalse(doc.closed_by)
