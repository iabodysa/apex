# Copyright (c) 2026, AFMCO and contributors
"""The /fleet employee fuel request draws against the vehicle's monthly Fuel Quota.

The second door onto the same hole the driver portal had: ``submit_fuel_request``
built a Fuel Request with no ``fuel_quota``, so the controller's allowance gate
(``_guard_quota_allowance``) returned at its first line for every request raised from
the employee page — /fleet drew past an allocation the desk, the approval console and
the portal are all held to.

These tests hold the closed path end to end — the quota is resolved for the request's
OWN month and stamped on the request, an oversized draw is refused with the
controller's own ValidationError before anything is written, and a refusal never moves
``consumed_litres``. They also pin the two ways the gate must NOT over-reach: a draw
that exactly spends the remainder is allowed, and a vehicle with no quota that month
still submits, because the allocation is what creates the ceiling, not the endpoint.

The fixture driver is PRIVATE to this module and deliberately not the shared portal
driver: ``bound_vehicle`` reads ``current_vehicle`` FIRST, and the shared driver
carries one — so the driver portal's trick of binding a second vehicle through an
Active Vehicle Assignment resolves to the wrong vehicle on this endpoint. Each test
points its own driver's ``current_vehicle`` at its own plate instead.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.api import fleet_employee
from apex.tests.factories import make_driver_without_vehicle, make_vehicle


class TestFleetEmployeeFuelQuotaGate(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.driver, cls.user = make_driver_without_vehicle("fleet_emp_fuel_quota@example.com")

	def setUp(self):
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")

	def _bound_vehicle(self, plate):
		"""A vehicle bound to this module's own driver as their ``current_vehicle``.

		``current_vehicle`` rather than a Vehicle Assignment because that is the first
		branch ``salis.utils.bound_vehicle`` reads — the rule this endpoint resolves
		the caller's vehicle through. The write is a row, so the per-test rollback
		returns the driver to vehicle-less."""
		vehicle = make_vehicle(plate)
		frappe.db.set_value("Salis Driver", self.driver, "current_vehicle", vehicle)
		return vehicle

	def _quota(self, vehicle, monthly_litres, consumed_litres=0, status="Active", period=None):
		"""A Fuel Quota for ``vehicle``, in the CURRENT period unless ``period`` says
		otherwise — the current month is the one a /fleet request is dated into, so it
		is the row the endpoint has to resolve."""
		return frappe.get_doc(
			{"doctype": "Fuel Quota", "vehicle": vehicle,
			 "period_month": period or frappe.utils.today()[:7],
			 "monthly_litres": monthly_litres, "consumed_litres": consumed_litres,
			 "status": status}
		).insert(ignore_permissions=True)

	def _submit(self, litres):
		"""Submit as the employee. The endpoint is session-scoped and takes no driver,
		so the identity IS the fixture user."""
		frappe.set_user(self.user)
		try:
			return fleet_employee.submit_fuel_request(litres=litres)
		finally:
			frappe.set_user("Administrator")

	def test_request_carries_the_quota_for_its_own_month(self):
		"""The created Fuel Request names the vehicle's quota for the month it is
		dated into — the link the whole allowance gate hangs off."""
		vehicle = self._bound_vehicle("FQ FLEET A")
		quota = self._quota(vehicle, monthly_litres=100)

		result = self._submit(litres=10)

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
		vehicle = self._bound_vehicle("FQ FLEET B")
		quota = self._quota(vehicle, monthly_litres=100, consumed_litres=90)

		with self.assertRaises(frappe.ValidationError) as caught:
			self._submit(litres=25)

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
			"A refused /fleet request must leave no draft behind.",
		)

	def test_exhausted_quota_refuses_the_employee_page_too(self):
		"""The gate's other refusal reaches /fleet as well: a spent allocation turns
		away even a 1 L draw."""
		vehicle = self._bound_vehicle("FQ FLEET C")
		quota = self._quota(vehicle, monthly_litres=50, consumed_litres=50, status="Exhausted")

		with self.assertRaises(frappe.ValidationError) as caught:
			self._submit(litres=1)

		self.assertIn(quota.name, str(caught.exception))
		self.assertEqual(frappe.db.get_value("Fuel Quota", quota.name, "consumed_litres"), 50)
		self.assertFalse(frappe.db.exists("Fuel Request", {"vehicle": vehicle}))

	def test_a_draw_that_exactly_spends_the_remainder_is_allowed(self):
		"""The ceiling is an overrun test, not a margin: 10 L against 10 L remaining
		passes, and consumption is still posted later (at Done), not at request time."""
		vehicle = self._bound_vehicle("FQ FLEET D")
		quota = self._quota(vehicle, monthly_litres=100, consumed_litres=90)

		result = self._submit(litres=10)

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
		vehicle = self._bound_vehicle("FQ FLEET E")

		result = self._submit(litres=40)

		self.assertEqual(
			frappe.db.get_value("Fuel Request", result["name"], "vehicle"), vehicle
		)
		self.assertFalse(
			frappe.db.get_value("Fuel Request", result["name"], "fuel_quota"),
			"With no quota for the month the request must carry none.",
		)

	def test_last_months_quota_neither_binds_nor_refuses(self):
		"""A spent allocation from the PREVIOUS period is not this month's ceiling —
		the resolver is scoped to the request's own month, so the request is neither
		bound to the stale row nor refused by it."""
		vehicle = self._bound_vehicle("FQ FLEET F")
		last_month = frappe.utils.add_months(frappe.utils.today(), -1)[:7]
		self._quota(
			vehicle, monthly_litres=5, consumed_litres=5, status="Exhausted", period=last_month
		)

		result = self._submit(litres=40)

		self.assertFalse(
			frappe.db.get_value("Fuel Request", result["name"], "fuel_quota"),
			"Only a quota for the request's own month may be bound.",
		)
