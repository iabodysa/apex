# Copyright (c) 2026, AFMCO and contributors
"""submit_due_rounds enforces building-read scope BEFORE creating any round.

submit_due_rounds takes a single ``building`` and drives one round per cadence
plus a manager email. A caller scoped off that building (no User Permission for
it) must be rejected up-front with a PermissionError — before the savepoint, any
Safety Round insert, or the report email — so a supervisor cannot drive (or leak)
another estate's due-rounds. A supervisor acting on their OWN building is
unaffected and still records the rounds.

These tests pin the new ``frappe.has_permission("Building",
"read", doc=building, throw=True)`` gate: that it fires (the cross-building call
never reaches frappe.db.savepoint and creates no round) and that the in-scope
caller still succeeds end-to-end.
"""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from apex_habitat.habitat.api.safety_checklist import submit_due_rounds


def _h(n=6):
    return frappe.generate_hash(length=n).upper()


class TestSubmitDueRoundsBuildingScope(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Two estates; a Resident Supervisor scoped (User Permission) to ONLY b1.
        cls.b1 = cls._building()
        cls.b2 = cls._building()
        cls.scoped = cls._scoped_supervisor(cls.b1)
        # One active, applies-to-all Daily task so a real round can be recorded.
        cls.task = cls._daily_task()

    @classmethod
    def _building(cls):
        doc = frappe.get_doc(
            {"doctype": "Building", "building_name": "SCP-" + _h()}
        )
        doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        cls.addClassCleanup(
            frappe.delete_doc,
            "Building",
            doc.name,
            force=True,
            ignore_permissions=True,
        )
        return doc.name

    @classmethod
    def _scoped_supervisor(cls, building):
        email = "scope-{0}@example.com".format(_h()).lower()
        frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": "Scope",
                "send_welcome_email": 0,
                "roles": [{"role": "Resident Supervisor"}],
            }
        ).insert(ignore_permissions=True)
        cls.addClassCleanup(
            frappe.delete_doc, "User", email, force=True, ignore_permissions=True
        )
        up = frappe.get_doc(
            {
                "doctype": "User Permission",
                "user": email,
                "allow": "Building",
                "for_value": building,
            }
        )
        up.insert(ignore_permissions=True)
        cls.addClassCleanup(
            frappe.delete_doc,
            "User Permission",
            up.name,
            force=True,
            ignore_permissions=True,
        )
        return email

    @classmethod
    def _daily_task(cls):
        doc = frappe.get_doc(
            {
                "doctype": "Safety Task Catalog",
                "task_code": "SCP-" + _h(),
                "task_title": "Scope Gate Task",
                "department": "Fire Safety",
                "frequency": "Daily",
                "priority": "High",
                "applicable_to_all_buildings": 1,
                "is_active": 1,
            }
        )
        doc.insert(ignore_permissions=True)
        cls.addClassCleanup(
            frappe.delete_doc,
            "Safety Task Catalog",
            doc.name,
            force=True,
            ignore_permissions=True,
        )
        return doc.name

    def _results(self):
        return [{"task": self.task, "cadence": "Daily", "execution_status": "Good"}]

    def setUp(self):
        self.addCleanup(frappe.set_user, "Administrator")

    # RED -> GREEN: a supervisor scoped to b1 cannot submit due-rounds for b2.
    def test_cross_building_submit_denied(self):
        frappe.set_user(self.scoped)
        with self.assertRaises(frappe.PermissionError):
            submit_due_rounds(self.b2, today(), self._results())

    def test_cross_building_denied_before_any_side_effect(self):
        # The gate must reject BEFORE the savepoint/round creation: frappe.db.savepoint
        # is never reached and no Safety Round is created for the off-scope building.
        before = frappe.db.count("Safety Round", {"building": self.b2})
        frappe.set_user(self.scoped)
        with patch(
            "apex_habitat.habitat.api.safety_checklist.frappe.db.savepoint"
        ) as mock_savepoint:
            with self.assertRaises(frappe.PermissionError):
                submit_due_rounds(self.b2, today(), self._results())
        mock_savepoint.assert_not_called()
        frappe.set_user("Administrator")
        after = frappe.db.count("Safety Round", {"building": self.b2})
        self.assertEqual(
            after, before, "no round may be created for an off-scope building"
        )

    def test_cross_building_empty_results_denied_by_scope_not_validation(self):
        # Even with NO result lines the scope gate fires first: a scoped-off caller
        # gets PermissionError, NOT the "No result lines" ValidationError that would
        # mean execution slipped past the building check (and could email the report).
        frappe.set_user(self.scoped)
        with self.assertRaises(frappe.PermissionError):
            submit_due_rounds(self.b2, today(), [])

    # The permitted supervisor still records rounds for their OWN building.
    def test_in_scope_supervisor_still_processes(self):
        frappe.set_user(self.scoped)
        out = submit_due_rounds(self.b1, today(), self._results())
        self.assertTrue(out["ok"])
        self.assertEqual(len(out["rounds"]), 1)
        frappe.set_user("Administrator")
        self.assertEqual(
            frappe.db.get_value(
                "Safety Round", out["rounds"][0]["safety_round"], "docstatus"
            ),
            1,
            "the in-scope supervisor's round must be submitted",
        )
