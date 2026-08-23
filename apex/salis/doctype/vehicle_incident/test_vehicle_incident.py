# Copyright (c) 2026, afmcoltd
"""Tests for Vehicle Incident's own draft guards and cost-recovery arithmetic.

Patterned on frappe/tests/test_document.py. Most cases build an unsaved
Document via frappe.new_doc and call one guard method directly. The
status-transition case is the exception: it travels through the Vehicle
Incident Workflow (apex/fixtures/workflow.json), so those cases insert a
minimal incident against the fixture vehicle, submit it, and drive the Close
action through ``frappe.model.workflow.apply_workflow`` — the same
production path ``close_incident`` calls — asserting the framework's own
``validate_workflow`` (frappe/model/document.py:687-695) refuses a
hand-edited jump instead of a bespoke check.

WHY ``test_ignore`` NAMES ``Loan``. ``get_dependencies`` (frappe/test_runner.py:359-381)
builds a test record for every Link on the DocType under test, whether or not a case
touches it. ``recovery_loan`` Links to ``Loan``, which the ``lending`` app owns, and
apex declares only frappe, erpnext and hrms — so on a site without lending the walk
aborts the WHOLE suite with ``DocType Loan not found`` before one case runs, which
reads as UNKNOWN rather than as a failure. ``test_ignore`` (test_runner.py:374-377) is
the framework's own hatch for this and is scoped to this module alone. It is honest
here because nothing below reads ``recovery_loan``; the cases that do live in
``test_vehicle_incident_loan_recovery.py`` and skip themselves when lending is absent.
"""

from __future__ import annotations

import frappe
from frappe.model.workflow import WorkflowPermissionError
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from apex.salis.doctype.vehicle_incident.vehicle_incident import close_incident
from apex.tests._helpers import lending_installed

test_dependencies = ["Salis Vehicle"]
test_ignore = ["Loan"]


class TestVehicleIncident(FrappeTestCase):
    def _incident(self, **fields):
        doc = frappe.new_doc("Vehicle Incident")
        doc.update(
            {
                "incident_type": "Accident",
                "vehicle": "_T ABC 1001",
                "incident_date": today(),
                "description": "Test collision.",
            }
        )
        doc.update(fields)
        return doc

    def _delete_incident(self, name):
        doc = frappe.get_doc("Vehicle Incident", name)
        if doc.docstatus == 1:
            doc.cancel()
        frappe.delete_doc("Vehicle Incident", name, force=True)


    def test_a_new_incident_defaults_to_open_with_no_python_default(self):
        """The DocType JSON's ``default: Open`` on the status field does this
        alone now that ``_guard_status``'s ``is_new()`` branch is gone."""
        doc = self._incident()
        doc.insert()
        self.addCleanup(self._delete_incident, doc.name)
        self.assertEqual(doc.status, "Open")

    def test_a_hand_edited_status_is_refused(self):
        """Break the removed guard's job on purpose: a plain save() that jumps
        the field to a state with no modelled transition from Open must still
        fail — now via the Workflow, not a ``has_value_changed`` throw."""
        doc = self._incident()
        doc.insert()
        self.addCleanup(self._delete_incident, doc.name)
        doc.status = "Closed"
        with self.assertRaises(WorkflowPermissionError):
            doc.save()

    def test_close_travels_through_apply_workflow(self):
        """Proves the production path: ``close_incident`` calls
        ``close_incident_internal``, which drives the Close transition through
        ``frappe.model.workflow.apply_workflow`` rather than setting the field
        directly."""
        doc = self._incident()
        doc.insert()
        self.addCleanup(self._delete_incident, doc.name)
        doc.submit()
        self.assertEqual(
            frappe.db.get_value("Vehicle Incident", doc.name, "status"), "Under Review"
        )

        close_incident(doc.name, "Repaired and returned to service.")
        self.assertEqual(
            frappe.db.get_value("Vehicle Incident", doc.name, "status"), "Closed"
        )


    def test_incident_date_in_the_future_is_refused(self):
        doc = self._incident(incident_date=add_days(today(), 1))
        self.assertRaises(frappe.ValidationError, doc.validate)

    def test_incident_date_today_is_accepted(self):
        doc = self._incident(incident_date=today())
        doc.validate()

    def test_negative_estimated_cost_is_refused(self):
        doc = self._incident(estimated_cost=-1)
        self.assertRaises(frappe.ValidationError, doc.validate)

    def test_zero_estimated_cost_is_accepted(self):
        doc = self._incident(estimated_cost=0)
        doc.validate()


    def test_third_party_fields_are_cleared_once_the_flag_is_off(self):
        doc = self._incident(
            third_party_involved=0,
            third_party_plate="ABC 123",
            third_party_driver="Someone",
        )
        doc._sync_third_party()
        self.assertIsNone(doc.third_party_plate)
        self.assertIsNone(doc.third_party_driver)

    def test_third_party_fields_survive_while_the_flag_is_on(self):
        doc = self._incident(third_party_involved=1, third_party_plate="ABC 123")
        doc._sync_third_party()
        self.assertEqual(doc.third_party_plate, "ABC 123")


    def test_recovery_amount_must_be_positive(self):
        doc = self._incident(recover_from_driver=1, recovery_amount=0)
        self.assertRaises(frappe.ValidationError, doc._guard_cost_recovery)

    def test_recovery_amount_cannot_exceed_the_estimated_cost(self):
        doc = self._incident(
            recover_from_driver=1, estimated_cost=500, recovery_amount=600
        )
        self.assertRaises(frappe.ValidationError, doc._guard_cost_recovery)

    def test_recovery_amount_within_the_estimated_cost_is_accepted(self):
        doc = self._incident(
            recover_from_driver=1,
            estimated_cost=500,
            recovery_amount=400,
            worker_signature="sig",
        )
        with lending_installed():
            doc._guard_cost_recovery()

    def test_installment_amount_cannot_exceed_the_recovery_amount(self):
        doc = self._incident(
            recover_from_driver=1,
            estimated_cost=500,
            recovery_amount=400,
            installment_amount=450,
            worker_signature="sig",
        )
        self.assertRaises(frappe.ValidationError, doc._guard_cost_recovery)

    def test_submitting_a_recovery_without_a_worker_signature_is_refused(self):
        doc = self._incident(recover_from_driver=1, recovery_amount=400)
        doc.docstatus = 1
        self.assertRaises(frappe.ValidationError, doc._guard_cost_recovery)

    def test_a_worker_signature_stamps_todays_date_once(self):
        doc = self._incident(
            recover_from_driver=1,
            recovery_amount=400,
            worker_signature="sig",
            signed_on=None,
        )
        with lending_installed():
            doc._guard_cost_recovery()
        self.assertEqual(doc.signed_on, today())
