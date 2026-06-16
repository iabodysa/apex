import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, now_datetime

from apex_habitat.apex_core.doctype.operations_alert.operations_alert import OperationsAlert

# [#gim548]
# [#66rs26]
test_ignore = ["Salis Vehicle", "Salis Driver"]


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
        # [#1dpub4]
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
        # [#j1ww5c]
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
        # [#68jph9]
        name = self._make_alert("Resolved", age_days=200, resolved_age_days=None)
        OperationsAlert.clear_old_logs(days=90)
        self.assertFalse(frappe.db.exists("Operations Alert", name))
