# Copyright (c) 2026, AFMCO and contributors
"""The portal fuel request draws against the vehicle's monthly Fuel Quota.

``submit_fuel_request`` used to build a Fuel Request with no ``fuel_quota`` at all, so
the controller's allowance gate (``_guard_quota_allowance``) returned at its first line
for every portal-submitted Standard request: the SPA rendered a quota bar the request
then ignored, and a driver could draw past an allocation the desk and the approval
console are both held to.

These tests hold the closed path end to end — the quota is resolved for the request's
OWN month and stamped on the request, an oversized draw is refused with the
controller's own ValidationError before anything is written, and a refusal never moves
``consumed_litres``. They also pin the two ways the gate must NOT over-reach: a draw
that exactly spends the remainder is allowed, and a vehicle with no quota this month
still submits, because the allocation is what creates the ceiling, not the endpoint.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.api import driver_portal
from apex.tests.factories import (
    make_test_driver as _ensure_test_driver,
    make_vehicle,
)


class TestPortalFuelQuotaGate(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        frappe.db.set_single_value("Salis Settings", "enable_driver_portal", 1)
        cls.driver = _ensure_test_driver()
        cls.user = frappe.db.get_value(
            "Employee", frappe.db.get_value("Salis Driver", cls.driver, "employee"), "user_id"
        )

    def setUp(self):
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")

    def _bound_vehicle(self, plate):
        """A vehicle bound to the portal driver through an Active Vehicle Assignment.

		Deliberately NOT the driver's ``current_vehicle``: the canonical portal driver
		is shared with the other driver_portal suites, so a quota is attached to a
		second, private vehicle and their quota-less default is left untouched."""
        vehicle = make_vehicle(plate)
        frappe.get_doc(
            {"doctype": "Vehicle Assignment", "driver": self.driver, "vehicle": vehicle,
             "status": "Active", "start_date": frappe.utils.today()}
        ).insert(ignore_permissions=True)
        return vehicle

    def _quota(self, vehicle, monthly_litres, consumed_litres=0, status="Active", period=None):
        """A Fuel Quota for ``vehicle``, in the CURRENT period unless ``period`` says
		otherwise — the current month is the one a portal request is dated into, so it
		is the row the endpoint has to resolve."""
        return frappe.get_doc(
            {"doctype": "Fuel Quota", "vehicle": vehicle,
             "period_month": period or frappe.utils.today()[:7],
             "monthly_litres": monthly_litres, "consumed_litres": consumed_litres,
             "status": status}
        ).insert(ignore_permissions=True)

    def _submit(self, vehicle, litres):
        frappe.set_user(self.user)
        try:
            return driver_portal.submit_fuel_request(litres=litres, vehicle=vehicle)
        finally:
            frappe.set_user("Administrator")

    def test_request_carries_the_quota_for_its_own_month(self):
        """The created Fuel Request names the vehicle's quota for the month it is
		dated into — the link the whole allowance gate hangs off."""
        vehicle = self._bound_vehicle("FQ PORTAL A")
        quota = self._quota(vehicle, monthly_litres=100)

        result = self._submit(vehicle, litres=10)

        row = frappe.db.get_value(
            "Fuel Request",
            result["name"],
            ["fuel_quota", "request_date", "request_type"],
            as_dict=True,
        )
        self.assertEqual(row.fuel_quota, quota.name)
        self.assertEqual(row.request_type, "Standard")
        self.assertEqual(
            str(row.request_date)[:7],
            quota.period_month,
            "The quota resolved must be the one for the request's own month.",
        )

    def test_draw_over_the_remaining_allowance_is_refused(self):
        """25 L against 10 L of remaining allocation is refused with the controller's
		own ValidationError, nothing is written, and consumption does not move."""
        vehicle = self._bound_vehicle("FQ PORTAL B")
        quota = self._quota(vehicle, monthly_litres=100, consumed_litres=90)

        with self.assertRaises(frappe.ValidationError) as caught:
            self._submit(vehicle, litres=25)

        message = str(caught.exception)
        # The oversized-draw branch, not the exhausted-quota one: only it interpolates
        # the requested amount and the 10 L still left. Matching the interpolated
        # numbers keeps the assertion true in either language.
        self.assertIn(quota.name, message)
        self.assertIn("25.0", message)
        self.assertIn("10.0", message)
        self.assertEqual(
            frappe.db.get_value("Fuel Quota", quota.name, "consumed_litres"),
            90,
            "A refused draw must leave consumed_litres untouched.",
        )
        self.assertFalse(
            frappe.db.exists("Fuel Request", {"vehicle": vehicle}),
            "A refused portal request must leave no draft behind.",
        )

    def test_exhausted_quota_refuses_the_portal_too(self):
        """The gate's other refusal reaches the portal as well: a spent allocation
		turns away even a 1 L draw."""
        vehicle = self._bound_vehicle("FQ PORTAL C")
        quota = self._quota(
            vehicle, monthly_litres=50, consumed_litres=50, status="Exhausted"
        )

        with self.assertRaises(frappe.ValidationError) as caught:
            self._submit(vehicle, litres=1)

        self.assertIn(quota.name, str(caught.exception))
        self.assertEqual(frappe.db.get_value("Fuel Quota", quota.name, "consumed_litres"), 50)
        self.assertFalse(frappe.db.exists("Fuel Request", {"vehicle": vehicle}))

    def test_a_draw_that_exactly_spends_the_remainder_is_allowed(self):
        """The ceiling is an overrun test, not a margin: 10 L against 10 L remaining
		passes, and consumption is still posted later (at Done), not at request time."""
        vehicle = self._bound_vehicle("FQ PORTAL D")
        quota = self._quota(vehicle, monthly_litres=100, consumed_litres=90)

        result = self._submit(vehicle, litres=10)

        self.assertEqual(
            frappe.db.get_value("Fuel Request", result["name"], "fuel_quota"), quota.name
        )
        self.assertEqual(
            frappe.db.get_value("Fuel Quota", quota.name, "consumed_litres"),
            90,
            "Raising a request must not consume the quota; Done does that.",
        )

    def test_vehicle_without_a_quota_this_month_still_submits(self):
        """No allocation means no ceiling. The gate must not turn into a requirement
		that every vehicle carry a quota before its driver can ask for fuel."""
        vehicle = self._bound_vehicle("FQ PORTAL E")

        result = self._submit(vehicle, litres=40)

        self.assertFalse(
            frappe.db.get_value("Fuel Request", result["name"], "fuel_quota"),
            "With no quota for the month the request must carry none.",
        )

    def test_last_months_quota_neither_binds_nor_refuses(self):
        """A spent allocation from the PREVIOUS period is not this month's ceiling —
		the resolver is scoped to the request's own month, so the request is neither
		bound to the stale row nor refused by it."""
        vehicle = self._bound_vehicle("FQ PORTAL F")
        last_month = frappe.utils.add_months(frappe.utils.today(), -1)[:7]
        self._quota(
            vehicle, monthly_litres=5, consumed_litres=5,
            status="Exhausted", period=last_month,
        )

        result = self._submit(vehicle, litres=40)

        self.assertFalse(
            frappe.db.get_value("Fuel Request", result["name"], "fuel_quota"),
            "Only a quota for the request's own month may be bound.",
        )
