"""Driver-portal feature-flag gating: when ``Salis Settings.enable_driver_portal``
is OFF the portal must present a disabled state on bootstrap and refuse every write.

The flag is the single kill-switch for the self-service portal. ``get_driver_context``
(the SPA bootstrap) must report ``enabled: False`` rather than raise, and every action
endpoint guards on ``_require_enabled()`` so a disabled portal cannot create attendance,
fuel requests or tickets even for a genuinely linked driver. These tests flip the flag
off, assert that contract for a real resolved driver, and restore the flag afterwards.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex_habitat.salis.api import driver_portal
from apex_habitat.tests.test_driver_portal import _ensure_test_driver


class TestDriverPortalDisabledFlag(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.driver = _ensure_test_driver()
		cls.user = frappe.db.get_value(
			"Employee", frappe.db.get_value("Salis Driver", cls.driver, "employee"), "user_id"
		)

	def _disable_portal(self):
		frappe.set_user("Administrator")
		frappe.db.set_single_value("Salis Settings", "enable_driver_portal", 0)

	def tearDown(self):
		# Restore the kill-switch to ON so the Single is left enabled for any
		# sibling suite that assumes the live default.
		frappe.set_user("Administrator")
		frappe.db.set_single_value("Salis Settings", "enable_driver_portal", 1)

	def test_context_reports_disabled_for_linked_driver(self):
		"""With the flag off the bootstrap returns a disabled, unlinked payload —
		``enabled`` is falsy and no driver profile is exposed — even for a user who
		IS linked to a Salis Driver. The SPA renders the 'portal off' state, never a
		live cockpit."""
		self._disable_portal()
		frappe.set_user(self.user)
		ctx = driver_portal.get_driver_context()
		self.assertFalse(ctx["enabled"], "Disabled flag must yield enabled=False.")
		self.assertFalse(ctx["linked"])
		self.assertIsNone(ctx["driver"])
		frappe.set_user("Administrator")

	def test_check_in_blocked_when_disabled(self):
		"""The check-in WRITE endpoint must refuse when the portal is off, even for a
		resolved driver — no Driver Attendance may be created behind a closed portal."""
		self._disable_portal()
		frappe.set_user(self.user)
		with self.assertRaises(frappe.PermissionError):
			driver_portal.driver_check_in()
		frappe.set_user("Administrator")

	def test_fuel_request_blocked_when_disabled(self):
		"""The fuel-request WRITE endpoint must refuse when the portal is off — a
		disabled portal cannot raise a Fuel Request for a linked driver."""
		self._disable_portal()
		frappe.set_user(self.user)
		with self.assertRaises(frappe.PermissionError):
			driver_portal.submit_fuel_request(litres=25)
		frappe.set_user("Administrator")

	def test_reads_blocked_when_disabled(self):
		"""Read endpoints guard on the same flag, so a disabled portal exposes no
		trip or ticket data either."""
		self._disable_portal()
		frappe.set_user(self.user)
		for call in (driver_portal.my_trips_today, driver_portal.my_support_tickets):
			with self.assertRaises(frappe.PermissionError):
				call()
		frappe.set_user("Administrator")
