# Copyright (c) 2026, AFMCO and contributors
"""Standard Notification records for the two lifecycle events surfaced to the
coordinator (resident request resolved) and the dispatch desk / driver (trip
scheduled).

Locks in two ``is_standard`` Notification records and proves they are synced
on a fresh site and resolve the intended recipients when their status condition
holds. Recipient resolution is exercised through the real
``Notification.get_list_of_recipients`` (the same call the framework makes when
the alert fires), mirroring the existing notification test pattern.

All data is provisioned in setUp so the suite passes on a clean CI site with no
ambient rows.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex_habitat.tests._helpers import _user

RR_NOTIFICATION = "Habitat - Resident Request Resolved"
TRIP_NOTIFICATION = "Salis - Trip Scheduled"


def _recipients(notification_name, doc):
	notification = frappe.get_doc("Notification", notification_name)
	context = {"doc": doc, "alert": notification, "comments": None}
	recipients, _cc, _bcc = notification.get_list_of_recipients(doc, context)
	return recipients


class TestRequestTripNotifications(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.coordinator = _user("rrtn_coord@example.com", "Resident Request Coordinator")
		cls.assigned = _user("rrtn_assigned@example.com", "Resident Supervisor")
		cls.fleet_sup = _user("rrtn_fleet@example.com", "Fleet Supervisor")
		cls.requested_by = _user("rrtn_req@example.com", "Fleet Project Manager")

	def setUp(self):
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_records_are_synced_and_shaped(self):
		"""Both standard Notifications load on a fresh site with the expected
		trigger wiring (so migrate exports + imports them)."""
		rr = frappe.get_doc("Notification", RR_NOTIFICATION)
		self.assertEqual(rr.is_standard, 1)
		self.assertEqual(rr.document_type, "Resident Request")
		self.assertEqual(rr.event, "Value Change")
		self.assertEqual(rr.value_changed, "status")
		self.assertEqual(rr.condition, "doc.status == 'Resolved'")
		self.assertEqual(rr.send_system_notification, 1)

		trip = frappe.get_doc("Notification", TRIP_NOTIFICATION)
		self.assertEqual(trip.is_standard, 1)
		self.assertEqual(trip.document_type, "Transport Request")
		self.assertEqual(trip.event, "Value Change")
		self.assertEqual(trip.value_changed, "status")
		self.assertEqual(trip.condition, "doc.status == 'Scheduled'")
		self.assertEqual(trip.send_system_notification, 1)

	def test_resident_request_resolved_notifies_coordinator(self):
		req = frappe.get_doc({
			"doctype": "Resident Request",
			"naming_series": "REQ-.YYYY.-.####",
			"request_category": "Maintenance",
			"description": "AC not cooling.",
			"assigned_to": self.assigned,
			"status": "New",
		}).insert(ignore_permissions=True)
		self.addCleanup(
			lambda: frappe.delete_doc(
				"Resident Request", req.name,
				ignore_permissions=True, force=True,
			)
		)

		# The alert fires on the transition into Resolved; evaluate against it.
		req.status = "Resolved"
		recipients = _recipients(RR_NOTIFICATION, req)
		self.assertIn(self.coordinator, recipients)
		self.assertIn(self.assigned, recipients)

	def test_resident_request_firing_condition_gates_on_resolved(self):
		"""The alert only fires on the transition into Resolved — the firing
		gate is the Notification ``condition``, evaluated by the framework
		before recipients are resolved."""
		notification = frappe.get_doc("Notification", RR_NOTIFICATION)
		req = frappe.get_doc({
			"doctype": "Resident Request",
			"naming_series": "REQ-.YYYY.-.####",
			"request_category": "Maintenance",
			"description": "Leaking tap.",
			"status": "Triaged",
		}).insert(ignore_permissions=True)
		self.addCleanup(
			lambda: frappe.delete_doc(
				"Resident Request", req.name,
				ignore_permissions=True, force=True,
			)
		)
		self.assertFalse(frappe.safe_eval(notification.condition, None, {"doc": req}))
		req.status = "Resolved"
		self.assertTrue(frappe.safe_eval(notification.condition, None, {"doc": req}))

	def test_trip_scheduled_notifies_dispatch(self):
		tr = frappe.get_doc({
			"doctype": "Transport Request",
			"service_line": "Administrative Trip",
			"request_type": "Administrative Trip / Document Signing",
			"destination": "Ministry Office",
			"from_location": "HQ",
			"to_location": "Ministry Office",
			"requested_by": self.requested_by,
			"source_channel": "Desk",
			"status": "New",
		}).insert(ignore_permissions=True)
		self.addCleanup(
			lambda: frappe.delete_doc(
				"Transport Request", tr.name, ignore_permissions=True, force=True,
			)
		)

		tr.status = "Scheduled"
		recipients = _recipients(TRIP_NOTIFICATION, tr)
		self.assertIn(self.fleet_sup, recipients)
		self.assertIn(self.requested_by, recipients)
