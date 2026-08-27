# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.model.workflow import WorkflowTransitionError, apply_workflow
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.doctype.salis_settings.salis_settings import get_salis_float


def _vehicle():
    return frappe.get_doc(
        {
            "doctype": "Salis Vehicle",
            "plate_number": "_T-VWO " + frappe.generate_hash(length=6),
            "status": "Active",
        }
    ).insert(ignore_permissions=True).name


def _user_with_role(first_name, role):
    email = "_t_vwo_" + frappe.generate_hash(length=6) + "@example.com"
    doc = frappe.get_doc(
        {
            "doctype": "User",
            "email": email,
            "first_name": first_name,
            "send_welcome_email": 0,
        }
    )
    doc.insert(ignore_permissions=True)
    doc.add_roles(role)
    return email


def _threshold():
    return get_salis_float("writeoff_ops_threshold", 2000.0)


def _case(**overrides):
    fields = {
        "doctype": "Vehicle Damage Write-Off",
        "vehicle": _vehicle(),
        "evidence": "/files/_t_vwo_evidence.pdf",
        "estimated_cost": 100,
        "status": "Open",
    }
    fields.update(overrides)
    return frappe.get_doc(fields)


def _under_review(**overrides):
    doc = _case(**overrides).insert(ignore_permissions=True)
    apply_workflow(doc, "Submit for Review")
    return doc


class TestVehicleDamageWriteOffEvidence(FrappeTestCase):
    def test_moving_past_open_without_evidence_is_refused(self):
        doc = _case(evidence=None)
        doc.status = "Under Review"
        with self.assertRaisesRegex(frappe.ValidationError, "Evidence is required"):
            doc.insert(ignore_permissions=True)

    def test_a_case_with_evidence_moves_past_open(self):
        doc = _under_review()
        self.assertEqual(doc.status, "Under Review")


class TestVehicleDamageWriteOffEstimatedCost(FrappeTestCase):
    def test_a_negative_estimated_cost_is_refused(self):
        with self.assertRaisesRegex(frappe.ValidationError, "cannot be negative"):
            _case(estimated_cost=-1).insert(ignore_permissions=True)

    def test_a_zero_estimated_cost_is_accepted(self):
        doc = _case(estimated_cost=0).insert(ignore_permissions=True)
        self.assertEqual(doc.estimated_cost, 0)


class TestVehicleDamageWriteOffOperationsThreshold(FrappeTestCase):
    def test_a_cost_below_the_threshold_needs_no_operations_tier(self):
        doc = _case(estimated_cost=_threshold() - 1).insert(ignore_permissions=True)
        self.assertEqual(doc.needs_operations, 0)

    def test_a_cost_at_the_threshold_needs_the_operations_tier(self):
        doc = _case(estimated_cost=_threshold()).insert(ignore_permissions=True)
        self.assertEqual(doc.needs_operations, 1)

    def test_the_flag_follows_the_cost_rather_than_what_was_typed(self):
        doc = _case(estimated_cost=_threshold() - 1, needs_operations=1).insert(
            ignore_permissions=True
        )
        self.assertEqual(doc.needs_operations, 0)


class TestVehicleDamageWriteOffAuthority(FrappeTestCase):
    def test_the_raiser_cannot_authorize_their_own_case(self):
        doc = _under_review()
        with self.assertRaises(WorkflowTransitionError):
            apply_workflow(doc, "Authorize (Operations)")

    def test_the_operations_tier_authorizes_and_is_stamped(self):
        doc = _under_review(estimated_cost=_threshold())
        approver = _user_with_role("_T-VWO Fleet Manager", "Fleet Manager")
        frappe.set_user(approver)
        self.addCleanup(frappe.set_user, "Administrator")
        apply_workflow(doc, "Authorize (Operations)")
        self.assertEqual(doc.status, "Approved")
        self.assertEqual(doc.approved_by, approver)
        self.assertTrue(doc.approved_on)

    def test_a_regional_authority_cannot_authorize_above_the_threshold(self):
        doc = _under_review(estimated_cost=_threshold())
        frappe.set_user(_user_with_role("_T-VWO Regional", "Fleet Supervisor"))
        self.addCleanup(frappe.set_user, "Administrator")
        with self.assertRaises(WorkflowTransitionError):
            apply_workflow(doc, "Authorize (Regional)")

    def test_approving_above_the_threshold_without_operations_authority_is_refused(self):
        doc = _under_review(estimated_cost=_threshold())
        frappe.set_user(_user_with_role("_T-VWO Regional", "Fleet Supervisor"))
        self.addCleanup(frappe.set_user, "Administrator")
        doc.status = "Approved"
        with self.assertRaisesRegex(frappe.ValidationError, "Operations-tier authority"):
            doc.save(ignore_permissions=True)

    def test_a_case_short_of_approval_names_no_approver(self):
        doc = _under_review()
        self.assertFalse(doc.approved_by)
        self.assertFalse(doc.approved_on)


class TestVehicleDamageWriteOffSourceIncident(FrappeTestCase):
    def _incident(self, vehicle):
        return frappe.get_doc(
            {
                "doctype": "Vehicle Incident",
                "vehicle": vehicle,
                "incident_date": frappe.utils.today(),
                "incident_type": "Accident",
                "description": "_T-VWO incident",
                "status": "Open",
            }
        ).insert(ignore_permissions=True).name

    def test_submitting_writes_the_case_onto_the_incident(self):
        vehicle = _vehicle()
        incident = self._incident(vehicle)
        doc = _case(vehicle=vehicle, source_incident=incident).insert(
            ignore_permissions=True
        )
        doc.submit()
        self.assertEqual(
            frappe.db.get_value("Vehicle Incident", incident, "write_off_case"), doc.name
        )

    def test_cancelling_clears_the_case_from_the_incident(self):
        vehicle = _vehicle()
        incident = self._incident(vehicle)
        doc = _case(vehicle=vehicle, source_incident=incident).insert(
            ignore_permissions=True
        )
        doc.submit()
        doc.cancel()
        self.assertFalse(
            frappe.db.get_value("Vehicle Incident", incident, "write_off_case")
        )
