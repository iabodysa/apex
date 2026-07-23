# Copyright (c) 2026, AFMCO and contributors
"""Driver Push Subscription — a driver device's Web Push registration.

One row per (driver, browser endpoint). Created on the driver's opt-in via the
driver-portal API (the whitelisted endpoint is the authorization boundary; the
Driver role holds no DocPerm here by design, like Fuel Request). The endpoint and
auth secret are device secrets — stored in the DB, never logged."""

import frappe
from frappe.model.document import Document


class DriverPushSubscription(Document):
	def before_save(self):
		# [#ancvsc]
		if not self.user and self.driver:
			employee = frappe.db.get_value("Salis Driver", self.driver, "employee")
			if employee:
				self.user = frappe.db.get_value("Employee", employee, "user_id")
