# Copyright (c) 2026, AFMCO and contributors
"""The /fleet employee vehicle read, and the binding rule its fuel write shares.

``fleet_employee.get_my_vehicle`` and ``fleet_employee.submit_fuel_request`` both
resolve the caller's vehicle through ``salis.utils.bound_vehicle`` — ``current_vehicle``
first, then a SUBMITTED Active Vehicle Assignment. One rule, two doors, so these cases
hold both halves of it: the read answers in the page's own key vocabulary and gives a
user who is not a driver a clean empty state instead of a 403, and the write refuses a
vehicle the caller does not hold.

Both endpoints live on ``fleet_employee``, not ``driver_portal`` —
``apex/www/test_portal_shell_contract.py:26-29`` asserts ``get_my_vehicle`` stays out
of ``driver_portal/profile.py``. /fleet is not behind
``Salis Settings.enable_driver_portal``, which is why no case here toggles it.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.api import fleet_employee
from apex.salis.utils import bound_vehicle
from apex.tests.factories import make_driver_without_vehicle, make_vehicle


class TestFleetEmployeeVehicleBinding(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.driver, cls.user = make_driver_without_vehicle("fleet_emp_vehicle@example.com")

    def setUp(self):
        frappe.set_user("Administrator")
        # FrappeTestCase rolls back once per CLASS, so a binding written by one case
        # would still be on the shared fixture driver when the next one runs. The
        # per-method primitive is a savepoint.
        frappe.db.savepoint("fleet_employee_vehicle")
        self.addCleanup(frappe.db.rollback, save_point="fleet_employee_vehicle")
        self.addCleanup(frappe.set_user, "Administrator")

    def _bind_current_vehicle(self, plate, **kwargs):
        """A vehicle held as the fixture driver's ``current_vehicle``.

        The write is a row on the shared driver, so the per-class rollback returns
        the fixture to vehicle-less for whatever runs next."""
        vehicle = make_vehicle(plate, **kwargs)
        frappe.db.set_value("Salis Driver", self.driver, "current_vehicle", vehicle)
        return vehicle

    def _as_driver(self, call, *args, **kwargs):
        frappe.set_user(self.user)
        try:
            return call(*args, **kwargs)
        finally:
            frappe.set_user("Administrator")

    def test_the_read_answers_in_the_page_key_vocabulary(self):
        """The card's keys are the endpoint's contract: a rename here blanks a field
        on the page, so the whole shape is asserted rather than one probe key."""
        vehicle = self._bind_current_vehicle("FLEET VEH READ", odometer=1234)

        payload = self._as_driver(fleet_employee.get_my_vehicle)["vehicle"]

        self.assertIsNotNone(payload)
        self.assertEqual(payload["name"], vehicle)
        self.assertEqual(payload["plate"], "FLEET VEH READ")
        self.assertEqual(payload["odometerKm"], 1234)
        self.assertEqual(payload["status"], "assigned")
        self.assertEqual(
            set(payload),
            {"name", "plate", "model", "office", "status", "odometerKm", "registrationExpiry"},
        )

    def test_a_driver_with_no_vehicle_reads_as_empty_not_as_an_error(self):
        self.assertIsNone(self._as_driver(fleet_employee.get_my_vehicle)["vehicle"])

    def test_a_user_who_is_not_a_driver_reads_as_empty_too(self):
        """An ordinary office employee opens /fleet. The page renders its empty state;
        the endpoint must not answer with a permission error."""
        outsider = "fleet_emp_outsider@example.com"
        if not frappe.db.exists("User", outsider):
            frappe.get_doc(
                {
                    "doctype": "User",
                    "email": outsider,
                    "first_name": "Fleet Outsider",
                    "send_welcome_email": 0,
                }
            ).insert(ignore_permissions=True)
        frappe.set_user(outsider)
        try:
            self.assertIsNone(fleet_employee.get_my_vehicle()["vehicle"])
        finally:
            frappe.set_user("Administrator")

    def test_the_assignment_fallback_holds_when_the_mirror_is_gone(self):
        """``Vehicle Assignment.on_submit`` stamps ``current_vehicle``, so the second
        branch of ``bound_vehicle`` is only reachable once that mirror has been cleared
        — which is exactly what a reassignment does to the outgoing driver. Clearing it
        here is the precondition, not the behaviour under test."""
        vehicle = make_vehicle("FLEET VEH ASSIGNED")
        assignment = frappe.get_doc(
            {
                "doctype": "Vehicle Assignment",
                "driver": self.driver,
                "vehicle": vehicle,
                "status": "Active",
                "start_date": frappe.utils.today(),
            }
        )
        assignment.insert(ignore_permissions=True)
        assignment.submit()
        frappe.db.set_value("Salis Driver", self.driver, "current_vehicle", None)

        self.assertEqual(
            self._as_driver(fleet_employee.get_my_vehicle)["vehicle"]["name"], vehicle
        )

    def test_fuel_without_a_bound_vehicle_is_refused(self):
        with self.assertRaises(frappe.ValidationError):
            self._as_driver(fleet_employee.submit_fuel_request, litres=10)

    def test_fuel_for_a_vehicle_the_caller_does_not_hold_is_refused(self):
        """A driver naming an arbitrary vehicle id cannot charge fuel to it — the id is
        honoured only after it matches the bound vehicle.

        The caller DOES hold a vehicle here, so the refusal is about the id that was
        named and not about an unbound driver — that is the other case above."""
        mine = self._bind_current_vehicle("FLEET VEH MINE")
        foreign = make_vehicle("FLEET VEH FOREIGN")
        self.assertEqual(bound_vehicle(self.driver), mine)

        with self.assertRaises(frappe.PermissionError):
            self._as_driver(fleet_employee.submit_fuel_request, litres=20, vehicle=foreign)

        self.assertFalse(frappe.db.exists("Fuel Request", {"vehicle": foreign}))
