# Copyright (c) 2026, AFMCO and contributors
import frappe
from frappe.email.doctype.notification.notification import get_context
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, now_datetime

from apex_habitat.apex_core.doctype.operations_alert.operations_alert import OperationsAlert
from apex_habitat.salis.permissions import _project_supervisor
from apex_habitat.salis.tasks import _raise_alert, _resolve_project_supervisor
from apex_habitat.tests._helpers import _user

# [#3hbe1z]
test_ignore = ["Salis Vehicle", "Salis Driver"]
NOTIFICATION = "Apex Core - Operations Alert Critical"


class TestOperationsAlertRetention(FrappeTestCase):
    """clear_old_logs must age out ONLY Resolved alerts — Open/Acknowledged
    alerts are still actionable and must survive forever (regression for the
    2026-06-04 audit P0: the old delete purged by `modified` regardless of
    status)."""

    def _make_alert(self, status, age_days, resolved_age_days=None):
        doc = frappe.get_doc({
            "doctype": "Operations Alert",
            "alert_type": "Idle Vehicle",
            "severity": "Warning",
            "status": status,
            "message": "QA retention fixture",
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        # [#shgfhw]
        frappe.db.set_value(
            "Operations Alert", doc.name, "modified",
            add_days(now_datetime(), -age_days), update_modified=False,
        )
        if resolved_age_days is not None:
            frappe.db.set_value(
                "Operations Alert", doc.name, "resolved_on",
                add_days(now_datetime(), -resolved_age_days), update_modified=False,
            )
        return doc.name

    def test_aged_resolved_is_cleared(self):
        name = self._make_alert("Resolved", age_days=200, resolved_age_days=200)
        OperationsAlert.clear_old_logs(days=90)
        self.assertFalse(frappe.db.exists("Operations Alert", name))

    def test_open_alert_is_never_cleared(self):
        # [#hg88v4]
        name = self._make_alert("Open", age_days=400)
        OperationsAlert.clear_old_logs(days=90)
        self.assertTrue(frappe.db.exists("Operations Alert", name))

    def test_acknowledged_alert_is_never_cleared(self):
        name = self._make_alert("Acknowledged", age_days=400)
        OperationsAlert.clear_old_logs(days=90)
        self.assertTrue(frappe.db.exists("Operations Alert", name))

    def test_recent_resolved_is_kept(self):
        name = self._make_alert("Resolved", age_days=5, resolved_age_days=5)
        OperationsAlert.clear_old_logs(days=90)
        self.assertTrue(frappe.db.exists("Operations Alert", name))

    def test_resolved_without_resolved_on_falls_back_to_modified(self):
        # [#31npav]
        name = self._make_alert("Resolved", age_days=200, resolved_age_days=None)
        OperationsAlert.clear_old_logs(days=90)
        self.assertFalse(frappe.db.exists("Operations Alert", name))


class TestOperationsAlertCriticalNotification(FrappeTestCase):
    """A Critical Operations Alert must notify the vehicle's project supervisor —
    the User holding a User Permission for the vehicle's Project — via System
    Notification, NOT every Fleet role and NOT an oversight role. Provisions its
    own Project / scoped supervisor / oversight user / vehicle in setUp and uses
    frappe.generate_hash() for the unique plate so it survives a fresh CI site."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        suffix = frappe.generate_hash(length=8)
        cls.project = frappe.get_doc(
            {"doctype": "Project", "project_name": f"OA Crit {suffix}"}
        ).insert(ignore_permissions=True).name
        cls.sup = _user(f"oa_crit_sup_{suffix}@example.com", "Fleet Supervisor")
        cls.oversight = _user(f"oa_crit_mgr_{suffix}@example.com", "Fleet Manager")
        # Both hold a Project User Permission; only the scoped one is "the supervisor".
        for user in (cls.sup, cls.oversight):
            frappe.get_doc(
                {"doctype": "User Permission", "allow": "Project",
                 "for_value": cls.project, "user": user}
            ).insert(ignore_permissions=True)
        cls.vehicle = frappe.get_doc(
            {"doctype": "Salis Vehicle", "plate_number": f"OA-{suffix}",
             "status": "Active", "project": cls.project}
        ).insert(ignore_permissions=True).name
        # A second vehicle with no project, to prove the resolver returns None.
        cls.vehicle_no_project = frappe.get_doc(
            {"doctype": "Salis Vehicle", "plate_number": f"NP-{suffix}", "status": "Active"}
        ).insert(ignore_permissions=True).name

    def _critical_doc(self, **overrides):
        data = {
            "doctype": "Operations Alert", "alert_type": "License Expiry",
            "severity": "Critical", "status": "Open", "message": "QA critical",
            "vehicle": self.vehicle, "project_supervisor": self.sup,
        }
        data.update(overrides)
        return frappe.get_doc(data)

    def test_project_supervisor_excludes_oversight(self):
        # The scoped supervisor is returned; the oversight (unscoped) role is not.
        self.assertEqual(_project_supervisor(self.project), self.sup)
        self.assertIsNone(_project_supervisor(None))

    def test_resolve_via_vehicle_chain(self):
        self.assertEqual(_resolve_project_supervisor(self.vehicle), self.sup)
        self.assertIsNone(_resolve_project_supervisor(self.vehicle_no_project))
        self.assertIsNone(_resolve_project_supervisor(None))

    def test_critical_alert_stamps_supervisor(self):
        name = _raise_alert(
            "License Expiry", "Critical", "QA stamp",
            vehicle=self.vehicle, driver=None,
        )
        self.assertIsNotNone(name)
        self.assertEqual(
            frappe.db.get_value("Operations Alert", name, "project_supervisor"),
            self.sup,
        )

    def test_notification_record_is_enabled_and_targeted(self):
        notif = frappe.get_doc("Notification", NOTIFICATION)
        self.assertTrue(notif.enabled)
        self.assertEqual(notif.document_type, "Operations Alert")
        self.assertTrue(notif.send_system_notification)
        self.assertEqual(
            [r.receiver_by_document_field for r in notif.recipients],
            ["project_supervisor"],
        )

    def test_condition_gates_on_critical_with_supervisor(self):
        notif = frappe.get_doc("Notification", NOTIFICATION)
        critical = self._critical_doc()
        self.assertTrue(
            frappe.safe_eval(notif.condition, None, get_context(critical))
        )
        # Warning severity must NOT fire.
        warning = self._critical_doc(severity="Warning")
        self.assertFalse(
            frappe.safe_eval(notif.condition, None, get_context(warning))
        )
        # Critical but no resolvable supervisor must NOT fire.
        orphan = self._critical_doc(project_supervisor=None)
        self.assertFalse(
            frappe.safe_eval(notif.condition, None, get_context(orphan))
        )

    def test_system_notification_reaches_supervisor(self):
        notif = frappe.get_doc("Notification", NOTIFICATION)
        critical = self._critical_doc()
        critical.insert(ignore_permissions=True)
        before = frappe.db.count(
            "Notification Log", {"for_user": self.sup, "document_name": critical.name}
        )
        # System-notification half of the alert (send_system_notification=1).
        notif.create_system_notification(critical, get_context(critical))
        after = frappe.db.count(
            "Notification Log", {"for_user": self.sup, "document_name": critical.name}
        )
        self.assertEqual(after, before + 1)
