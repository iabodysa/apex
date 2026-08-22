# Copyright (c) 2026, AFMCO and contributors
"""Idle Resident Report notifies each role holder ONCE, and only if they may
already read the report (#4).

``after_insert`` used to resolve the responsible department's role holders by hand: a
``frappe.get_all("Has Role", ...)`` followed by one ``frappe.db.get_value("User", ...)``
per holder to test ``enabled``, then handed the raw list straight to ``assign_to.add`` with
no permission check. That was ``frappe.utils.user.get_users_with_role``
(``frappe/utils/user.py:419-435``) re-implemented and worse in three measurable ways — a
user holding the role through two ``Has Role`` rows was assigned twice, the enabled check
cost one round trip per holder, Administrator was excluded only because the hand-rolled
list remembered to — and it was one thing worse than any of those: a role holder who could
not read the document was handed one anyway via a DocShare (or blocked outright with
Document Sharing off), which is how a role-scoped assignment became a permission leak.

``after_insert`` now routes through :func:`apex.apex_core.utils.role_assignment.assign_role`,
which applies ``frappe.has_permission`` before assigning. The dedup/round-trip cases below
are proven against the "Operations" department (Accommodation Manager, who DOES hold read
on this DocType) so the assignment actually happens; a fourth test proves the "HR"
department (HR Manager, who holds NO read DocPerm here) queues to nobody rather than
silently widening — the queue empties instead of leaking, until an owner grants the role
read.
"""

import frappe
from frappe.desk.form import assign_to as assign_to_module
from frappe.tests.utils import FrappeTestCase

from apex.habitat.doctype.idle_resident_report import idle_resident_report as IRR
from apex.tests import factories
from apex.tests._helpers import _user

ROLE = "Accommodation Manager"

class TestIdleResidentReportRecipients(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.tag = frappe.generate_hash(length=12).upper()
        cls.company = factories.make_company().name
        cls.building = factories.make_building(company=cls.company).name
        cls.employee = factories.make_employee(company=cls.company).name

        cls.duplicated = _user("irr_dup@example.com", ROLE)
        cls.plain = _user("irr_plain@example.com", ROLE)
        cls.disabled = _user("irr_disabled@example.com", ROLE)
        for user in (cls.duplicated, cls.plain, cls.disabled):
            frappe.db.delete("Has Role", {"parent": user, "role": "HR Manager"})

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
        frappe.set_user("Administrator")
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

    def _report(self, department, **overrides):
        payload = {
            "doctype": "Idle Resident Report",
            "naming_series": "IDLE-.YYYY.-.####",
            "employee": self.employee,
            "building": self.building,
            "reason_category": "Other",
            "responsible_department": department,
            "status": "Open",
        }
        payload.update(overrides)
        doc = frappe.get_doc(payload).insert(ignore_permissions=True)
        self.addCleanup(frappe.delete_doc, "Idle Resident Report", doc.name, force=True)
        return doc

    def _run(self, department="Operations"):
        """Creates one report, fires after_insert, then deletes the report immediately
        (rather than deferring to addCleanup) — the duplicate-open-report guard in
        _validate_status_transition would otherwise refuse a second call in the same
        test for the same employee."""
        doc = self._report(department)
        IRR.after_insert(doc)
        assignees = self.captured[-1]["assign_to"] if self.captured else []
        frappe.delete_doc("Idle Resident Report", doc.name, force=True, ignore_permissions=True)
        return assignees

    def test_double_role_holder_is_assigned_once(self):
        assignees = self._run()
        self.assertEqual(assignees.count(self.duplicated), 1)
        self.assertIn(self.plain, assignees)

    def test_administrator_is_never_assigned(self):
        self.assertNotIn("Administrator", self._run())

    def test_disabled_holder_is_excluded(self):
        self.assertNotIn(self.disabled, self._run())

    def test_the_enabled_filter_does_not_scale_with_holder_count(self):
        """The enabled filter belongs in the one join, not in a read per holder --
        proven by holding the read count flat as the candidate count grows, not by
        demanding zero: assign_role's own has_permission check now costs one fixed
        read of its own per call, which get_users_with_role's join never did."""
        self._run()
        after_three_candidates = self.user_reads
        _user("irr_extra@example.com", ROLE)
        self.addCleanup(frappe.db.delete, "Has Role", {"parent": "irr_extra@example.com"})
        self.user_reads = 0
        self._run()
        self.assertEqual(
            self.user_reads,
            after_three_candidates,
            "a fourth candidate must not add another User read",
        )

    def test_a_role_with_no_read_grant_is_queued_to_nobody(self):
        """HR Manager holds no DocPerm on this DocType (idle_resident_report.json).
        after_insert must not widen a role holder's access to reach them -- an empty
        queue is the honest outcome until that grant is made, not a DocShare."""
        assignees = self._run(department="HR")
        self.assertEqual(assignees, [])
        self.assertEqual(self.captured, [])
