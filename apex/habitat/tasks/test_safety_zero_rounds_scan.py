# Copyright (c) 2026, AFMCO and contributors

import frappe
from frappe.utils import today

from apex.habitat.tasks import daily_safety_task_compliance_scan
from apex.tests.factories import ApexHabitatTestCase


def _hash(n=12):
    return frappe.generate_hash(length=n).upper()


class TestSafetyZeroRoundsScan(ApexHabitatTestCase):
    """daily_safety_task_compliance_scan flags active buildings with no recent round."""

    def setUp(self):
        self.site = frappe.get_doc({
            "doctype": "Site", "site_name": _hash(),
        }).insert(ignore_permissions=True)

    def _building(self, status="Active", supervisor=None):
        # [#bv5acj]
        abbr = "Z" + _hash()
        return frappe.get_doc({
            "doctype": "Building",
            "building_name": f"Bldg {abbr}", "abbreviation": abbr,
            "site": self.site.name, "total_capacity": 10, "status": status,
            "responsible_supervisor": supervisor,
        }).insert(ignore_permissions=True)

    def _supervisor(self):
        email = f"zrs-{_hash()}@example.com".lower()
        return frappe.get_doc({
            "doctype": "User", "email": email, "first_name": "ZRS Supervisor",
            "send_welcome_email": 0,
        }).insert(ignore_permissions=True).name

    def _submitted_round(self, building):
        """A SUBMITTED Safety Round on ``building``, carrying one rated task.

        The scan only cares that a submitted round exists, but a round cannot be
        submitted without a Safety Task Execution: an unrated round would derive
        "Pass" from an empty status set. The rating is fixture detail here — it
        just has to be real. Scoped to no building (``applicable_to_all_buildings``
        off, no scope rows) so the catalog row stays inert for the scan."""
        task = frappe.get_doc({
            "doctype": "Safety Task Catalog", "task_code": f"ZR-{_hash()}",
            "task_title": "Zero Rounds Fixture Task", "department": "Fire Safety",
            "frequency": "Daily", "priority": "High",
            "applicable_to_all_buildings": 0, "is_active": 1,
        }).insert(ignore_permissions=True).name
        rnd = frappe.get_doc({
            "doctype": "Safety Round", "naming_series": "SRN-.YYYY.-.#####",
            "building": building, "round_date": today(), "cadence": "Daily",
        }).insert(ignore_permissions=True)
        frappe.get_doc({
            "doctype": "Safety Task Execution",
            "building": building, "task": task, "execution_date": today(),
            "execution_status": "Good", "safety_round": rnd.name,
        }).insert(ignore_permissions=True).submit()
        rnd.submit()
        return rnd

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
        self._submitted_round(b.name)
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
        self._submitted_round(b.name)
        daily_safety_task_compliance_scan()
        self.assertFalse(
            self._supervisor_notified(sup, b.name),
            "BUG: supervisor wrongly alerted though a recent round exists",
        )

    # A-069: dedup + auto-clear of the zero-rounds bell notifications.
    def _unread_bell_count(self, user, building):
        """Unread Building-linked Alert bell notifications this user holds for a building."""
        return frappe.db.count("Notification Log", {
            "for_user": user,
            "type": "Alert",
            "document_type": "Building",
            "document_name": building,
            "read": 0,
        })

    def test_second_scan_does_not_duplicate_supervisor_bell(self):
        """Re-running the daily scan while the building still has no round must NOT stack
        a second unread bell notification — the first unread one dedups the re-run."""
        sup = self._supervisor()
        b = self._building(supervisor=sup)
        daily_safety_task_compliance_scan()
        daily_safety_task_compliance_scan()
        self.assertEqual(
            self._unread_bell_count(sup, b.name),
            1,
            "BUG: a second scan stacked a duplicate unread bell notification",
        )

    def test_submitting_round_clears_supervisor_bell(self):
        """Submitting a Safety Round resolves the zero-rounds condition, so the building's
        unread bell notifications are auto-cleared (marked read) on submit."""
        sup = self._supervisor()
        b = self._building(supervisor=sup)
        daily_safety_task_compliance_scan()
        self.assertEqual(self._unread_bell_count(sup, b.name), 1)
        self._submitted_round(b.name)
        self.assertEqual(
            self._unread_bell_count(sup, b.name),
            0,
            "BUG: submitting a round did not clear the building's unread bell notifications",
        )

    # [#5yf1my]
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
