# Copyright (c) 2026, AFMCO and contributors
"""Idle Resident Report notifies each role holder ONCE, via the framework ( #4).

``after_insert`` resolved the responsible department's role holders by hand: a
``frappe.get_all("Has Role", ...)`` followed by one ``frappe.db.get_value("User", ...)``
per holder to test ``enabled``. That is ``frappe.utils.user.get_users_with_role``
(``frappe/utils/user.py:419-435``) re-implemented, and worse in three measurable ways —
a user holding the role through two ``Has Role`` rows was assigned twice, the enabled
check cost one round trip per holder, and Administrator was excluded only because the
hand-rolled list remembered to exclude it.

The test drives ``after_insert`` with ``assign_to.add`` captured, so it asserts the
RECIPIENTS and the round trips, not the ToDo plumbing.
"""

import frappe
from frappe.desk.form import assign_to as assign_to_module
from frappe.tests.utils import FrappeTestCase

from apex.habitat.doctype.idle_resident_report import idle_resident_report as IRR
from apex.tests._helpers import _user

ROLE = "HR Manager"


class TestIdleResidentReportRecipients(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.tag = frappe.generate_hash(length=12).upper()

        cls.duplicated = _user("irr_dup@example.com", ROLE)
        cls.plain = _user("irr_plain@example.com", ROLE)
        cls.disabled = _user("irr_disabled@example.com", ROLE)

        # A SECOND Has Role row for the same (user, role): the shape the hand-rolled
        # query counted twice. Written with db_insert, which is the only way such a row
        # exists — Has Role.before_insert (frappe/core/doctype/has_role/has_role.py:25)
        # rejects the duplicate, so a live one is legacy data that predates that guard.
        duplicate = frappe.get_doc(
            {
                "doctype": "Has Role",
                "parent": cls.duplicated,
                "parenttype": "User",
                "parentfield": "roles",
                "role": ROLE,
            }
        )
        duplicate.name = "irr-dup-" + cls.tag
        duplicate.db_insert()
        cls.duplicate_row = duplicate.name

        frappe.db.set_value("User", cls.disabled, "enabled", 0)
        frappe.db.commit()

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        frappe.db.set_value("User", cls.disabled, "enabled", 1)
        frappe.db.delete("Has Role", {"name": cls.duplicate_row})
        frappe.db.commit()
        super().tearDownClass()

    def setUp(self):
        self.captured = []
        self.user_reads = 0
        self._real_add = assign_to_module.add
        self._real_get_value = frappe.db.get_value

        def fake_add(args):
            self.captured.append(args)

        def counting_get_value(doctype, *a, **kw):
            if doctype == "User":
                self.user_reads += 1
            return self._real_get_value(doctype, *a, **kw)

        assign_to_module.add = fake_add
        frappe.db.get_value = counting_get_value

    def tearDown(self):
        assign_to_module.add = self._real_add
        frappe.db.get_value = self._real_get_value

    def _run(self):
        doc = frappe._dict(
            doctype="Idle Resident Report",
            name="IDLE-TEST-" + self.tag,
            responsible_department="HR",
            employee="EMP-" + self.tag,
            employee_name="Test Resident",
            building="Building " + self.tag,
            reason_category="Other",
        )
        IRR.after_insert(doc)
        return self.captured[0]["assign_to"] if self.captured else []

    def test_double_role_holder_is_assigned_once(self):
        assignees = self._run()
        self.assertEqual(assignees.count(self.duplicated), 1)
        self.assertIn(self.plain, assignees)

    def test_administrator_is_never_assigned(self):
        self.assertNotIn("Administrator", self._run())

    def test_disabled_holder_is_excluded(self):
        self.assertNotIn(self.disabled, self._run())

    def test_no_per_user_round_trip(self):
        """The enabled filter belongs in the one join, not in a read per holder."""
        self._run()
        self.assertEqual(self.user_reads, 0)
