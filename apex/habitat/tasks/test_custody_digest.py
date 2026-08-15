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

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from apex.habitat import tasks
from apex.tests._helpers import _user


class TestWeeklyCustodyDigest(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        frappe.db.set_single_value("Habitat Settings", "enable_email_notifications", 1)
        self.sup = _user(f"cd_sup_{frappe.generate_hash(length=12)}@example.com", "Accommodation Manager")
        self.building = self._building(self.sup)

    def _building(self, supervisor):
        return (
            frappe.get_doc(
                {
                    "doctype": "Building",
                    "building_name": f"CD-BLD-{frappe.generate_hash(length=12)}",
                    "responsible_supervisor": supervisor,
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
        self._issue(self.building, "Issued", add_days(today(), 7))
        self._issue(self.building, "Partially Returned", add_days(today(), -3))

        sent = self._run_capturing_mail()
        mine = [m for m in sent if m["recipients"] == [self.sup]]
        self.assertEqual(len(mine), 1, "supervisor must receive exactly one digest")
        self.assertIn(self.building, mine[0]["message"])

    def _every_user_enabled(self):
        """``frappe.db.get_value``, except that every User reads as enabled.

        Scoped to the single query it has to neutralise and delegating everything
        else VERBATIM: this sits on the whole framework's document loader for the
        length of the run, which calls it with keyword arguments, so the wrapper
        must not re-bind the positional signature it forwards.
        """
        original = frappe.db.get_value

        def get_value(*args, **kwargs):
            doctype = kwargs.get("doctype", args[0] if args else None)
            fieldname = kwargs.get("fieldname", args[2] if len(args) > 2 else "name")
            if doctype == "User" and fieldname == "enabled":
                return 1
            return original(*args, **kwargs)

        return get_value

    def test_building_without_supervisor_is_skipped(self):
        """The ``responsible_supervisor is set`` filter on the Building query.

        The digest carries a SECOND, later guard — it skips a supervisor whose User
        row is not enabled — and an unsupervised building arrives there as a FALSY
        supervisor, which reads as not-enabled. So it would be dropped by the
        backstop even with the Building filter gone, and asserting the outcome alone
        proves nothing about the filter this test is named for. The backstop is
        therefore neutralised for the length of the run (every User reads as
        enabled), leaving the named filter as the only thing that can keep the
        orphan out.
        """
        orphan = frappe.get_doc(
            {
                "doctype": "Building",
                "building_name": f"CD-ORPH-{frappe.generate_hash(length=12)}",
            }
        ).insert(ignore_permissions=True).name
        self._issue(orphan, "Issued", add_days(today(), 7))

        with patch.object(frappe.db, "get_value", self._every_user_enabled()):
            sent = self._run_capturing_mail()
        self.assertEqual([m for m in sent if orphan in m.get("message", "")], [])
        # A run that mailed nobody would satisfy the line above for the wrong reason.
        self.assertTrue(
            [m for m in sent if m["recipients"] == [self.sup]],
            "the supervised building's digest must still go out",
        )

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
        from apex import hooks

        self.assertIn(
            "apex.habitat.tasks.custody.weekly_custody_digest",
            hooks.scheduler_events["weekly"],
        )
