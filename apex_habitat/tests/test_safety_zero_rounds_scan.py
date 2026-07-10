# Copyright (c) 2026, AFMCO and contributors

import frappe
from frappe.utils import today

from apex_habitat.habitat.tasks import daily_safety_task_compliance_scan
from apex_habitat.tests.factories import ApexHabitatTestCase


def _hash(n=6):
    return frappe.generate_hash(length=n).upper()


class TestSafetyZeroRoundsScan(ApexHabitatTestCase):
    """daily_safety_task_compliance_scan flags active buildings with no recent round."""

    def setUp(self):
        self.site = frappe.get_doc({
            "doctype": "Accommodation Site", "site_name": _hash(),
        }).insert(ignore_permissions=True)

    def _building(self, status="Active", supervisor=None):
        # building_name is the autoname/PRIMARY key (unique) — use a full hash so
        # repeated runs on a persistent test DB never collide (was _hash(3), too narrow).
        abbr = "Z" + _hash()
        return frappe.get_doc({
            "doctype": "Accommodation Building",
            "building_name": f"Bldg {abbr}", "abbreviation": abbr,
            "site": self.site.name, "total_capacity": 10, "status": status,
            "responsible_facility_supervisor": supervisor,
        }).insert(ignore_permissions=True)

    def _supervisor(self):
        email = f"zrs-{_hash()}@example.com".lower()
        return frappe.get_doc({
            "doctype": "User", "email": email, "first_name": "ZRS Supervisor",
            "send_welcome_email": 0,
        }).insert(ignore_permissions=True).name

    def _zero_rounds_alert_exists(self, building):
        return bool(frappe.db.exists("Operations Alert", {
            "alert_type": "Supervisor Delay",
            "message": ["like", f"%zero-rounds::{building}%"],
        }))

    def _supervisor_notified(self, user, building):
        return bool(frappe.db.exists("Notification Log", {
            "for_user": user,
            "email_content": ["like", f"%zero-rounds::{building}%"],
        }))

    def test_active_building_with_no_round_is_flagged(self):
        b = self._building()
        daily_safety_task_compliance_scan()
        self.assertTrue(
            self._zero_rounds_alert_exists(b.name),
            "BUG: active building with no safety round was not flagged",
        )

    def test_recent_round_suppresses_flag(self):
        b = self._building()
        frappe.get_doc({
            "doctype": "Safety Round", "naming_series": "SRN-.YYYY.-.#####",
            "building": b.name, "round_date": today(), "cadence": "Daily",
        }).insert(ignore_permissions=True).submit()
        daily_safety_task_compliance_scan()
        self.assertFalse(
            self._zero_rounds_alert_exists(b.name),
            "BUG: building with a recent submitted round was wrongly flagged",
        )

    def test_inactive_building_is_ignored(self):
        b = self._building(status="Inactive")
        daily_safety_task_compliance_scan()
        self.assertFalse(
            self._zero_rounds_alert_exists(b.name),
            "BUG: inactive building should not be flagged for missing rounds",
        )

    def test_responsible_supervisor_is_notified_when_no_round(self):
        sup = self._supervisor()
        b = self._building(supervisor=sup)
        daily_safety_task_compliance_scan()
        self.assertTrue(
            self._supervisor_notified(sup, b.name),
            "BUG: the building's responsible supervisor was not alerted of the missing round",
        )

    def test_responsible_supervisor_not_notified_when_round_exists(self):
        sup = self._supervisor()
        b = self._building(supervisor=sup)
        frappe.get_doc({
            "doctype": "Safety Round", "naming_series": "SRN-.YYYY.-.#####",
            "building": b.name, "round_date": today(), "cadence": "Daily",
        }).insert(ignore_permissions=True).submit()
        daily_safety_task_compliance_scan()
        self.assertFalse(
            self._supervisor_notified(sup, b.name),
            "BUG: supervisor wrongly alerted though a recent round exists",
        )

    # ---- R11: off-by-one — a task due TODAY (zero grace) is overdue TODAY -----
    def _task_instance(self, building, due_date):
        """A draft Scheduled Task Instance in the Open state, due on ``due_date``."""
        return frappe.get_doc({
            "doctype": "Scheduled Task Instance",
            "naming_series": "STI-.YYYY.-.####",
            "due_date": due_date, "status": "Open", "building": building,
        }).insert(ignore_permissions=True, ignore_mandatory=True, ignore_links=True).name

    def test_instance_due_today_is_overdue_with_zero_grace(self):
        """With safety_overdue_grace_days = 0, an instance due exactly today must flip
        to Overdue on its due day — the `<=` boundary fix (was `<`, off-by-one)."""
        frappe.db.set_single_value("Habitat Settings", "safety_overdue_grace_days", 0)
        b = self._building()
        inst = self._task_instance(b.name, today())
        daily_safety_task_compliance_scan()
        self.assertEqual(
            frappe.db.get_value("Scheduled Task Instance", inst, "status"),
            "Overdue",
            "BUG: a task due today was NOT flagged overdue with zero grace (off-by-one)",
        )
