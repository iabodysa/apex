# Copyright (c) 2026, AFMCO and contributors
"""Daily open-alerts digest (``salis.tasks.daily_open_alerts_digest``).

Proves the job groups Open/Acknowledged Operations Alerts by their owning
``responsible_supervisor`` and emails each supervisor only their own bucket, skips
alerts with no owning supervisor, and is wired into the daily scheduler. Data is
provisioned in setUp so the suite passes on a clean CI site; ``frappe.sendmail``
is captured so the test asserts on recipients/counts without an outbox.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis import tasks
from apex.tests._helpers import _user


class TestOpenAlertsDigest(FrappeTestCase):
    MARKER = "digest test"

    def setUp(self):
        frappe.set_user("Administrator")
        # [#ovj1ei]
        frappe.db.set_single_value("Habitat Settings", "enable_email_notifications", 1)
        # [#i7af0o]
        frappe.db.delete("Operations Alert", {"message": ("like", f"{self.MARKER}%")})
        self.sup_a = _user(f"oad_a_{frappe.generate_hash(length=12)}@example.com", "Fleet Supervisor")
        self.sup_b = _user(f"oad_b_{frappe.generate_hash(length=12)}@example.com", "Fleet Supervisor")

    def _alert(self, severity, supervisor, status="Open"):
        return frappe.get_doc(
            {
                "doctype": "Operations Alert",
                "alert_type": "Idle Vehicle",
                "severity": severity,
                "status": status,
                "message": f"{self.MARKER} " + frappe.generate_hash(length=12),
                "responsible_supervisor": supervisor,
            }
        ).insert(ignore_permissions=True).name

    def _run_capturing_mail(self):
        sent = []
        original = frappe.sendmail
        frappe.sendmail = lambda **kw: sent.append(kw)
        try:
            tasks.daily_open_alerts_digest()
        finally:
            frappe.sendmail = original
        return sent

    def test_each_supervisor_gets_only_their_bucket(self):
        self._alert("Critical", self.sup_a)
        self._alert("Warning", self.sup_a)
        self._alert("Info", self.sup_b)

        sent = self._run_capturing_mail()
        by_recipient = {mail["recipients"][0]: mail for mail in sent}

        self.assertIn(self.sup_a, by_recipient)
        self.assertIn(self.sup_b, by_recipient)
        # [#nvu0zd]
        self.assertIn("2", by_recipient[self.sup_a]["subject"])
        self.assertIn("1", by_recipient[self.sup_b]["subject"])

    def test_acknowledged_alerts_are_included_resolved_excluded(self):
        self._alert("Warning", self.sup_a, status="Acknowledged")
        self._alert("Warning", self.sup_a, status="Resolved")

        sent = self._run_capturing_mail()
        by_recipient = {mail["recipients"][0]: mail for mail in sent}

        self.assertIn(self.sup_a, by_recipient)
        # [#9ww8uw]
        self.assertIn("1", by_recipient[self.sup_a]["subject"])

    def test_alerts_without_supervisor_are_skipped(self):
        # [#2yla2l]
        self._alert("Critical", None)
        sent = self._run_capturing_mail()
        self.assertEqual(sent, [])

    def test_no_sendmail_when_email_disabled(self):
        # [#9784t5]
        self._alert("Critical", self.sup_a)
        frappe.db.set_single_value("Habitat Settings", "enable_email_notifications", 0)

        calls = []
        original = frappe.sendmail
        frappe.sendmail = lambda **kw: calls.append(kw)
        try:
            tasks.daily_open_alerts_digest()
        finally:
            frappe.sendmail = original

        self.assertEqual(calls, [], "digest attempted a send while email was disabled")

    def test_job_is_registered_in_daily_scheduler(self):
        from apex import hooks

        self.assertIn(
            "apex.salis.tasks.alerts.daily_open_alerts_digest",
            hooks.scheduler_events["daily"],
        )
