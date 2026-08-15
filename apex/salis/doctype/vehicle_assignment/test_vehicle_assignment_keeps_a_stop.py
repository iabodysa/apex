# Copyright (c) 2026, AFMCO and contributors
"""Assigning a driver does not put a stopped vehicle back on the road.

``VehicleAssignment.on_submit`` writes ``Salis Vehicle.status = "Active"`` alongside the
driver pairing. That write is a ``frappe.db.set_value``, so it runs no controller — and
the guard that refuses an operator's own status edit while a Vehicle Suspension or an
open Vehicle Incident owns the vehicle
(``SalisVehicle._refuse_a_status_edit_while_a_stop_owns_the_vehicle``) never saw it.

So the one thing an operator is forbidden to do by hand — return an accident-stopped or
stolen vehicle to Active while the stop is still open — could be done by assigning a
driver to it, and every board that offers Active vehicles for dispatch believed it.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today


class TestAnAssignmentKeepsAnOpenStop(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.vehicle = self._new(
            "Salis Vehicle",
            plate_number="_VS " + frappe.generate_hash(length=8).upper(),
            status="Active",
        )
        self.driver = self._new(
            "Salis Driver", full_name="_VS Rider " + frappe.generate_hash(length=8).upper()
        )

    def _new(self, doctype, **values):
        doc = frappe.get_doc({"doctype": doctype, **values}).insert(
            ignore_permissions=True, ignore_mandatory=True
        )
        self.addCleanup(self._drop, doctype, doc.name)
        return doc.name

    @staticmethod
    def _drop(doctype, name):
        if not frappe.db.exists(doctype, name):
            return
        doc = frappe.get_doc(doctype, name)
        if doc.docstatus == 1:
            doc.cancel()
        frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)

    def _stop(self):
        """A submitted Vehicle Suspension with no return date — the vehicle is off the road."""
        doc = frappe.get_doc(
            {
                "doctype": "Vehicle Suspension",
                "vehicle": self.vehicle,
                "stop_reason": "Maintenance",
                "stop_date": today(),
            }
        ).insert(ignore_permissions=True, ignore_mandatory=True)
        doc.submit()
        self.addCleanup(self._drop, "Vehicle Suspension", doc.name)
        return doc.name

    def _assign(self):
        doc = frappe.get_doc(
            {
                "doctype": "Vehicle Assignment",
                "vehicle": self.vehicle,
                "driver": self.driver,
                "start_date": today(),
                "status": "Active",
            }
        ).insert(ignore_permissions=True)
        doc.submit()
        self.addCleanup(self._drop, "Vehicle Assignment", doc.name)
        return doc.name

    def _status(self):
        return frappe.db.get_value("Salis Vehicle", self.vehicle, "status")

    def test_the_stop_is_what_takes_the_vehicle_off_the_road(self):
        """Positive control: without a stop landing, the case below proves nothing."""
        self._stop()
        self.assertEqual(self._status(), "Stopped")

    def test_an_assignment_does_not_reactivate_a_stopped_vehicle(self):
        """The defect: the pairing's own status write walked past an open stop."""
        self._stop()

        self._assign()

        self.assertEqual(
            self._status(),
            "Stopped",
            "assigning a driver returned a stopped vehicle to the dispatch board",
        )

    def test_the_driver_is_still_paired_to_the_stopped_vehicle(self):
        """The half that must survive: the assignment is a real custody record, and the
        vehicle staying off the road does not make it a no-op."""
        self._stop()

        self._assign()

        self.assertEqual(
            frappe.db.get_value("Salis Vehicle", self.vehicle, "current_driver"), self.driver
        )

    def test_an_assignment_still_activates_a_vehicle_nothing_is_holding(self):
        """The behaviour the status write exists for, kept."""
        frappe.db.set_value("Salis Vehicle", self.vehicle, "status", "Released")

        self._assign()

        self.assertEqual(self._status(), "Active")
