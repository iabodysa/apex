# Copyright (c) 2026, AFMCO and contributors
"""The vehicle compliance alert has to reach the driver sitting in the vehicle.

``Salis - Vehicle Compliance Expiring Soon`` addresses
``receiver_by_document_field: current_driver_user``. That field is a ``fetch_from``
mirror of ``current_driver.driver_user``, and the framework resolves ``fetch_from``
only on the ORM save path (``BaseDocument._validate_links``). The pairing is written
by ``frappe.db.set_value`` on purpose — ``SalisVehicle`` refuses a hand-written
``current_driver`` — and ``set_value`` runs no controller and no fetch, so left alone
the mirror stays empty until something unrelated saves the vehicle.

These cases assert the mirror is correct the instant the pairing changes, with no
intervening save: filled on submit, cleared on cancel, and never left pointing at the
driver who has just handed the vehicle over.

The vehicle and the two riders are built here rather than borrowed. The shipped Salis
fixtures carry no ``driver_user``, and an assignment is refused when the vehicle or the
rider already holds an overlapping one — so a shared record makes this case depend on
what every other case left behind. The employee behind the rider IS borrowed: it is
ERPNext's own, whose ``user_id`` is the portal account the mirror has to land on.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

WORKER = "_Test Employee"
PORTAL_USER = "test@example.com"

class TestVehicleAssignmentDriverMirror(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        employee = frappe.db.get_value("Employee", {"first_name": WORKER})
        self.vehicle = self._new("Salis Vehicle", plate_number=self._tag("_VM"), status="Active")
        self.driver = self._new("Salis Driver", full_name=self._tag("_VM Rider"), employee=employee)
        self.other_driver = self._new("Salis Driver", full_name=self._tag("_VM Rider No Login"))

    def _tag(self, prefix):
        return f"{prefix} {frappe.generate_hash(length=12).upper()}"

    def _new(self, doctype, **values):
        doc = frappe.get_doc({"doctype": doctype, **values}).insert(
            ignore_permissions=True, ignore_mandatory=True
        )
        self.addCleanup(frappe.delete_doc, doctype, doc.name, force=True, ignore_permissions=True)
        return doc.name

    def _mirror(self):
        """Read the two halves straight from the row, never through a reloaded document."""
        return frappe.db.get_value(
            "Salis Vehicle", self.vehicle, ["current_driver", "current_driver_user"]
        )

    def _assign(self, driver):
        assignment = frappe.get_doc(
            {
                "doctype": "Vehicle Assignment",
                "vehicle": self.vehicle,
                "driver": driver,
                "start_date": today(),
                "status": "Active",
            }
        ).insert(ignore_permissions=True)
        assignment.submit()
        self.addCleanup(self._drop_assignment, assignment.name)
        return assignment

    @staticmethod
    def _drop_assignment(name):
        """Hand the record back. FrappeTestCase rolls back per CLASS, not per case
        (frappe/tests/utils.py:46), and a submitted document refuses deletion, so an
        assignment left behind here blocks the next case's vehicle as an overlap."""
        doc = frappe.get_doc("Vehicle Assignment", name)
        if doc.docstatus == 1:
            doc.cancel()
        frappe.delete_doc("Vehicle Assignment", name, force=True, ignore_permissions=True)

    def test_the_rider_fixture_carries_a_login(self):
        """Positive control: without this the mirror assertions below could not fail."""
        self.assertEqual(
            frappe.db.get_value("Salis Driver", self.driver, "driver_user"), PORTAL_USER
        )

    def test_submitting_an_assignment_fills_the_driver_user_mirror(self):
        """The alert's only driver-facing recipient must exist the moment the pair does."""
        self._assign(self.driver)

        current_driver, current_driver_user = self._mirror()
        self.assertEqual(current_driver, self.driver)
        self.assertIsNotNone(
            current_driver_user,
            "the compliance alert addresses current_driver_user and it is empty",
        )
        self.assertEqual(current_driver_user, PORTAL_USER)

    def test_cancelling_an_assignment_clears_the_driver_user_mirror(self):
        """A cleared pairing that keeps its user mirror mails a driver who handed the vehicle back."""
        assignment = self._assign(self.driver)
        assignment.cancel()

        current_driver, current_driver_user = self._mirror()
        self.assertIsNone(current_driver)
        self.assertIsNone(current_driver_user, "the mirror outlived the pairing it mirrors")

    def test_a_driver_with_no_login_leaves_the_mirror_empty_rather_than_stale(self):
        """The second rider has no user; the mirror must follow, not keep the first one."""
        first = self._assign(self.driver)
        first.cancel()
        self._assign(self.other_driver)

        current_driver, current_driver_user = self._mirror()
        self.assertEqual(current_driver, self.other_driver)
        self.assertIsNone(
            current_driver_user,
            "the alert would have mailed the previous driver about this vehicle",
        )

test_dependencies = ['Employee']

class TestAnAssignmentKeepsAnOpenStop(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.vehicle = self._new(
            "Salis Vehicle",
            plate_number="_VS " + frappe.generate_hash(length=12).upper(),
            status="Active",
        )
        self.driver = self._new(
            "Salis Driver", full_name="_VS Rider " + frappe.generate_hash(length=12).upper()
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
