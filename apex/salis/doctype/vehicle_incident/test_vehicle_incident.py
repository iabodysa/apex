# Copyright (c) 2026, afmcoltd

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
        doc = self._incident()
        doc.insert()
        self.addCleanup(self._delete_incident, doc.name)
        self.assertEqual(doc.status, "Open")

    def test_a_hand_edited_status_is_refused(self):
        doc = self._incident()
        doc.insert()
        self.addCleanup(self._delete_incident, doc.name)
        doc.status = "Closed"
        with self.assertRaises(WorkflowPermissionError):
            doc.save()

    def test_close_travels_through_apply_workflow(self):
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
