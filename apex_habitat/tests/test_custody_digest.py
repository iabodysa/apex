# Copyright (c) 2026, AFMCO and contributors
"""Weekly custody digest (``habitat.tasks.weekly_custody_digest``).

Proves the job emails each building's responsible supervisor a roll-up of only
their own building(s), short-circuits when the master email kill-switch is OFF,
and is wired into the weekly scheduler. Data is provisioned in setUp so the suite
passes on a clean CI site; ``frappe.sendmail`` is captured so the test asserts on
recipients/content without an outbox. Custody Issues are inserted with
``ignore_validate`` to skip the item-required controller rule while keeping the
framework link/field checks — the digest reads the rows, it does not re-run the
issue lifecycle.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from apex_habitat.habitat import tasks
from apex_habitat.tests._helpers import _user


class TestWeeklyCustodyDigest(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        # The digest is gated behind the master email kill-switch (default OFF);
        # turn it ON so the content tests below exercise the send path.
        frappe.db.set_single_value("Habitat Settings", "enable_email_notifications", 1)
        self.sup = _user(f"cd_sup_{frappe.generate_hash(length=6)}@example.com", "Accommodation Manager")
        self.building = self._building(self.sup)

    def _building(self, supervisor):
        return (
            frappe.get_doc(
                {
                    "doctype": "Accommodation Building",
                    "building_name": f"CD-BLD-{frappe.generate_hash(length=6)}",
                    "responsible_facility_supervisor": supervisor,
                }
            )
            .insert(ignore_permissions=True)
            .name
        )

    def _issue(self, building, status, expected_return_date):
        doc = frappe.get_doc(
            {
                "doctype": "Custody Issue",
                "issue_date": today(),
                "building": building,
                "status": status,
                "expected_return_date": expected_return_date,
            }
        )
        doc.flags.ignore_validate = True
        doc.insert(ignore_permissions=True)
        return doc.name

    def _run_capturing_mail(self):
        sent = []
        original = frappe.sendmail
        frappe.sendmail = lambda **kw: sent.append(kw)
        try:
            tasks.weekly_custody_digest()
        finally:
            frappe.sendmail = original
        return sent

    def test_supervisor_receives_digest_for_their_building(self):
        # One open (future return) and one overdue (past return) issue.
        self._issue(self.building, "Issued", add_days(today(), 7))
        self._issue(self.building, "Partially Returned", add_days(today(), -3))

        sent = self._run_capturing_mail()
        mine = [m for m in sent if m["recipients"] == [self.sup]]
        self.assertEqual(len(mine), 1, "supervisor must receive exactly one digest")
        # The supervisor's own building is named in the digest body.
        self.assertIn(self.building, mine[0]["message"])

    def test_building_without_supervisor_is_skipped(self):
        # A building with no responsible supervisor has no recipient: a digest run
        # over only that building must send nothing.
        orphan = frappe.get_doc(
            {
                "doctype": "Accommodation Building",
                "building_name": f"CD-ORPH-{frappe.generate_hash(length=6)}",
            }
        ).insert(ignore_permissions=True).name
        self._issue(orphan, "Issued", add_days(today(), 7))

        sent = self._run_capturing_mail()
        # No mail can be addressed to a building that has no supervisor.
        self.assertEqual([m for m in sent if orphan in m.get("message", "")], [])

    def test_no_sendmail_when_email_disabled(self):
        self._issue(self.building, "Issued", add_days(today(), 7))
        frappe.db.set_single_value("Habitat Settings", "enable_email_notifications", 0)

        calls = []
        original = frappe.sendmail
        frappe.sendmail = lambda **kw: calls.append(kw)
        try:
            tasks.weekly_custody_digest()
        finally:
            frappe.sendmail = original

        self.assertEqual(calls, [], "digest attempted a send while email was disabled")

    def test_job_is_registered_in_weekly_scheduler(self):
        from apex_habitat import hooks

        self.assertIn(
            "apex_habitat.habitat.tasks.custody.weekly_custody_digest",
            hooks.scheduler_events["weekly"],
        )
