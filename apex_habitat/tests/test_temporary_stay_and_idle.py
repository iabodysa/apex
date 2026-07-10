# Copyright (c) 2026, AFMCO and contributors
"""v0.8.5 — Temporary-stay validation on Accommodation Assignment and the Idle
Resident Report status flow (schema groundwork; no automation yet)."""

import frappe
from apex_habitat.tests.factories import ApexHabitatTestCase


def _h(n=4):
    return frappe.generate_hash(length=n).upper()


class TestTemporaryStayAndIdle(ApexHabitatTestCase):
    def setUp(self):
        self.company = frappe.db.get_value("Company", {}) or frappe.get_doc({
            "doctype": "Company", "company_name": "Test Co", "default_currency": "SAR",
            "country": "Saudi Arabia"}).insert(ignore_permissions=True).name
        self.cc = frappe.db.get_value("Cost Center", {"is_group": 0, "company": self.company}) or frappe.db.get_value("Cost Center", {"is_group": 0})
        self.site = frappe.get_doc({"doctype": "Site", "site_name": _h(6)}).insert(ignore_permissions=True)
        self.building = frappe.get_doc({"doctype": "Building", "building_name": "B " + _h(),
                                        "site": self.site.name, "total_capacity": 4, "company": self.company,
                                        "default_cost_center": self.cc}).insert(ignore_permissions=True).name
        self.employee = frappe.get_doc({"doctype": "Employee", "first_name": "E " + _h(), "company": self.company,
                                        "gender": "Male", "date_of_birth": "1990-01-01", "date_of_joining": "2020-01-01"}).insert(ignore_permissions=True).name
        self.project = frappe.get_doc({"doctype": "Project", "project_name": "P " + _h()}).insert(ignore_permissions=True).name

    def _assignment(self, stay_type, expected=None):
        return frappe.get_doc({
            "doctype": "Housing Assignment", "naming_series": "ACC-ASG-.YYYY.-.#####",
            "employee": self.employee, "project": self.project, "building": self.building,
            "cost_center": self.cc, "check_in_date": "2026-05-01",
            "stay_type": stay_type, "expected_checkout_date": expected,
        })

    def test_expected_checkout_notification_targets_building_supervisor(self):
        # The Expected Checkout Approaching alert must resolve to the building's own
        # responsible_facility_supervisor, not only the broad Resident Supervisor /
        # Accommodation Manager roles. The supervisor is mirrored onto the assignment
        # via fetch_from so the notification's receiver_by_document_field can read it.
        from apex_habitat.tests.factories import make_bed, make_room

        supervisor = f"sup{_h()}@test.com".lower()
        frappe.get_doc({"doctype": "User", "email": supervisor, "first_name": "Sup",
                        "send_welcome_email": 0}).insert(ignore_permissions=True)
        frappe.db.set_value("Building", self.building,
                            "responsible_facility_supervisor", supervisor)

        room = make_room(self.building, readiness_status="Ready")
        bed = make_bed(room.name)
        asg = self._assignment("Permanent")
        asg.room = room.name
        asg.bed = bed.name
        asg.insert(ignore_permissions=True)

        # fetch_from must have mirrored the building supervisor onto the assignment row.
        self.assertEqual(asg.responsible_facility_supervisor, supervisor)

        notification = frappe.get_doc("Notification", "Habitat - Expected Checkout Approaching")
        context = {"doc": asg, "alert": notification, "comments": None}
        recipients, _cc, _bcc = notification.get_list_of_recipients(asg, context)
        self.assertIn(supervisor, recipients,
                      "the building's responsible_facility_supervisor must be a recipient")

    def test_temporary_requires_expected_checkout_date(self):
        with self.assertRaises(frappe.ValidationError):
            self._assignment("Temporary").insert(ignore_permissions=True)

    def test_temporary_expected_date_after_checkin(self):
        with self.assertRaises(frappe.ValidationError):
            self._assignment("Temporary", "2026-04-20").insert(ignore_permissions=True)

    # [#3yvblc]
    def _idle(self, **kw):
        doc = frappe.get_doc({
            "doctype": "Idle Resident Report", "naming_series": "IDLE-.YYYY.-.####",
            "employee": self.employee, "building": self.building,
            "reason_category": "New Hire", "responsible_department": "Operations",
            "status": "Open", **kw})
        return doc

    def test_idle_resolve_requires_notes(self):
        doc = self._idle().insert(ignore_permissions=True)
        doc.status = "Resolved"
        with self.assertRaises(frappe.ValidationError):
            doc.save(ignore_permissions=True)

    def test_idle_rejects_duplicate_open_report(self):
        self._idle().insert(ignore_permissions=True)
        with self.assertRaises(frappe.ValidationError):
            self._idle().insert(ignore_permissions=True)

    def test_idle_after_insert_routes_todo_to_department_role(self):
        # [#fp3msv]
        email = f"mgr{_h()}@test.com".lower()
        user = frappe.get_doc({"doctype": "User", "email": email, "first_name": "Mgr",
                               "send_welcome_email": 0,
                               "roles": [{"role": "Accommodation Manager"}]}).insert(ignore_permissions=True)
        rep = self._idle(responsible_department="Operations").insert(ignore_permissions=True)
        todos = frappe.get_all("ToDo", filters={
            "reference_type": "Idle Resident Report", "reference_name": rep.name,
            "allocated_to": user.name, "status": "Open"})
        self.assertEqual(len(todos), 1, "an Operations role holder must get a routed ToDo")

    def test_idle_aging_accrues_days_idle(self):
        from apex_habitat.habitat.tasks import idle_resident_aging
        from frappe.utils import add_days, today
        rep = self._idle(reported_on=add_days(today(), -7)).insert(ignore_permissions=True)
        idle_resident_aging()
        rep.reload()
        self.assertEqual(rep.days_idle, 7)
        self.assertEqual(rep.estimated_accommodation_cost_bleed_sar, 0)  # [#71g7ip]
