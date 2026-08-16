# Copyright (c) 2026, AFMCO and contributors

"""M-20: coverage for four submittable controllers that carry real validate
guards and on_submit / on_cancel side-effects but previously had no test:

  * Vehicle Handover
  * Vehicle Damage Write-Off
  * Movement Cost Transfer
  * Vehicle Suspension

Each test asserts at least one validate/before_submit guard rejection and one
valid path (insert and, where the side-effect is observable, submit)."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from apex.tests._helpers import submit_via_workflow


def _h(n=12):
    return frappe.generate_hash(length=n).upper()


class _SalisMastersMixin:
    """Idempotent minimal-master builders shared across the four cases."""

    @staticmethod
    def _vehicle(plate=None):
        plate = plate or ("PLT-" + _h())
        return frappe.get_doc({
            "doctype": "Salis Vehicle",
            "plate_number": plate,
            "status": "Active",
            "odometer": 1000,
        }).insert(ignore_permissions=True).name

    @staticmethod
    def _driver(name=None):
        name = name or ("DRV " + _h())
        return frappe.get_doc({
            "doctype": "Salis Driver",
            "full_name": name,
            "status": "Active",
        }).insert(ignore_permissions=True).name

    @staticmethod
    def _project(name=None):
        name = name or ("PRJ " + _h())
        p = frappe.db.get_value("Project", {"project_name": name}, "name")
        if not p:
            p = frappe.get_doc({"doctype": "Project", "project_name": name}).insert(
                ignore_permissions=True
            ).name
        return p


class TestVehicleHandover(_SalisMastersMixin, FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def test_validate_rejects_same_from_and_to_driver(self):
        v = self._vehicle()
        d = self._driver()
        with self.assertRaises(frappe.ValidationError):
            frappe.get_doc({
                "doctype": "Vehicle Handover",
                "vehicle": v,
                "from_driver": d,
                "to_driver": d,
                "handover_date": today(),
            }).insert(ignore_permissions=True)

    def test_before_submit_requires_signed_evidence(self):
        v = self._vehicle()
        ho = frappe.get_doc({
            "doctype": "Vehicle Handover",
            "vehicle": v,
            "from_driver": self._driver(),
            "to_driver": self._driver(),
            "handover_date": today(),
            "odometer_reading": 1500,
        }).insert(ignore_permissions=True)
        with self.assertRaises(frappe.ValidationError):
            ho.submit()

    def test_valid_submit_updates_vehicle_mirror(self):
        v = self._vehicle()
        to_driver = self._driver()
        ho = frappe.get_doc({
            "doctype": "Vehicle Handover",
            "vehicle": v,
            "from_driver": self._driver(),
            "to_driver": to_driver,
            "handover_date": today(),
            "odometer_reading": 1500,
            "signed_evidence": "/files/handover.pdf",
        }).insert(ignore_permissions=True)
        ho.submit()
        self.assertEqual(ho.docstatus, 1)
        self.assertEqual(
            frappe.db.get_value("Salis Vehicle", v, "current_driver"), to_driver
        )
        self.assertEqual(
            frappe.db.get_value("Salis Vehicle", v, "odometer"), 1500
        )


class TestVehicleDamageWriteOff(_SalisMastersMixin, FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def test_validate_rejects_beyond_open_without_evidence(self):
        """The CONTROLLER evidence gate must be what rejects this, not the
        framework's mandatory check.

        ``evidence`` is also ``reqd`` on the DocType and ``MandatoryError``
        subclasses ``ValidationError``, so a bare ``assertRaises(ValidationError)``
        here stayed green even with the controller guard deleted. Frappe runs the
        controller ``validate()`` before ``_validate_mandatory()`` (Document.insert:
        run_before_save_methods -> _validate), so with the guard in place the guard
        is what fires; without it the mandatory check fires instead. Rejecting
        ``MandatoryError`` explicitly — and pinning the guard's own message — makes
        removing the guard fail this test. Every other field the DocType requires in
        this state (``damage_description`` is mandatory once status leaves Open) is
        populated so nothing but the evidence gate is left to trip.
        """
        v = self._vehicle()
        with self.assertRaises(frappe.ValidationError) as caught:
            frappe.get_doc({
                "doctype": "Vehicle Damage Write-Off",
                "vehicle": v,
                "status": "Under Review",
                "estimated_cost": 500,
                "damage_description": "Rear bumper cracked during handover.",
            }).insert(ignore_permissions=True)
        self.assertNotIsInstance(
            caught.exception,
            frappe.MandatoryError,
            "The DocType mandatory check rejected this, not the controller's "
            "evidence-beyond-Open guard — the guard is no longer being exercised.",
        )
        self.assertIn(
            "beyond Open",
            str(caught.exception),
            "The rejection did not come from the controller's evidence gate.",
        )

    def test_valid_open_case_inserts_and_submits(self):
        v = self._vehicle()
        wo = frappe.get_doc({
            "doctype": "Vehicle Damage Write-Off",
            "vehicle": v,
            "status": "Open",
            "estimated_cost": 500,
            "evidence": "/files/damage.jpg",
        }).insert(ignore_permissions=True)
        self.assertTrue(wo.name)
        submit_via_workflow(wo)
        self.assertEqual(wo.docstatus, 1)


class TestMovementCostTransfer(_SalisMastersMixin, FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def test_validate_rejects_same_from_and_to_project(self):
        p = self._project()
        with self.assertRaises(frappe.ValidationError):
            frappe.get_doc({
                "doctype": "Movement Cost Transfer",
                "transfer_type": "Fuel",
                "amount": 100,
                "status": "Draft",
                "from_project": p,
                "to_project": p,
            }).insert(ignore_permissions=True)

    def test_valid_distinct_projects_insert(self):
        mct = frappe.get_doc({
            "doctype": "Movement Cost Transfer",
            "transfer_type": "Fuel",
            "amount": 100,
            "status": "Draft",
            "from_project": self._project(),
            "to_project": self._project(),
        }).insert(ignore_permissions=True)
        self.assertTrue(mct.name)


class TestVehicleStop(_SalisMastersMixin, FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def test_before_submit_requires_evidence_for_incident_stop(self):
        v = self._vehicle()
        stop = frappe.get_doc({
            "doctype": "Vehicle Suspension",
            "vehicle": v,
            "stop_reason": "Accident",
            "stop_date": today(),
        }).insert(ignore_permissions=True)
        with self.assertRaises(frappe.ValidationError):
            stop.submit()

    def test_valid_maintenance_stop_sets_vehicle_stopped(self):
        v = self._vehicle()
        stop = frappe.get_doc({
            "doctype": "Vehicle Suspension",
            "vehicle": v,
            "stop_reason": "Maintenance",
            "stop_date": today(),
        }).insert(ignore_permissions=True)
        stop.submit()
        self.assertEqual(stop.docstatus, 1)
        self.assertEqual(
            frappe.db.get_value("Salis Vehicle", v, "status"), "Stopped"
        )
