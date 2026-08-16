# Copyright (c) 2026, afmcoltd
"""A User Permission carrying ``applicable_for`` must scope ONE doctype ( #2).

``applicable_for`` restricts a User Permission to a single DocType. Frappe applies it that
way when it builds its own match conditions (``frappe/model/db_query.py``): a row with no
``applicable_for`` counts everywhere, a row naming the queried doctype counts for it, and a
row naming a different doctype counts for nothing.

Apex resolved its tenant scope from the ``User Permission`` table with ``pluck="for_value"``,
which returns the value and drops every other column — so a Building permission granted for
Safety Round alone silently unlocked every other Building-scoped DocType for that user. This
test is the oracle for that fix: the SAME permission must admit the doctype it names and
exclude the one it does not.

The building is ``test_records.json``'s, not a minted one: ``test_dependencies`` stands the
Company / Site / Building chain up once per run, so this file owns a name to hang one User
Permission on without building and tearing that chain down itself. The User Permission
itself is the subject and is still built here.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat import permissions as HP
from apex.tests._helpers import _user

test_dependencies = ["Building"]

BUILDING = "_Test Building"
NAMED = "Safety Round"
OTHER = "Cleaning Log"


class TestApplicableForNarrowsScope(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.user = _user("paf_res_sup@example.com", "Resident Supervisor")
        cls.permission = frappe.get_doc(
            {
                "doctype": "User Permission",
                "user": cls.user,
                "allow": "Building",
                "for_value": BUILDING,
                "applicable_for": NAMED,
            }
        ).insert(ignore_permissions=True)
        cls.addClassCleanup(frappe.cache.hdel, "user_permissions", cls.user)

    def setUp(self):
        frappe.local.cache = {}
        self.addCleanup(frappe.set_user, "Administrator")

    def test_named_doctype_is_admitted(self):
        """Safety Round is the doctype the permission names: the building is in scope."""
        condition = HP.building_scope_query(user=self.user, doctype=NAMED)
        self.assertIn(frappe.db.escape(BUILDING), condition)

    def test_other_doctype_is_excluded(self):
        """Cleaning Log is NOT the doctype the permission names: nothing is in scope."""
        self.assertEqual(HP.building_scope_query(user=self.user, doctype=OTHER), "1=0")

    def test_form_access_to_other_doctype_is_denied(self):
        """The same narrowing governs the form / REST verdict, not just the list."""
        doc = frappe._dict(doctype=OTHER, building=BUILDING)
        # assertIs, not assertFalse: the deny-only hook returns None to DEFER, and None
        # is falsy — an assertFalse here would pass against the unfixed code.
        self.assertIs(HP.building_scoped_has_permission(doc, "read", user=self.user), False)

        in_scope = frappe._dict(doctype=NAMED, building=BUILDING)
        self.assertIsNone(HP.building_scoped_has_permission(in_scope, "read", user=self.user))

    def test_framework_supplies_the_doctype_to_the_hook(self):
        """The narrowing only works because frappe hands the doctype to the hook.

        Driven through ``DatabaseQuery.get_permission_query_conditions`` — the framework's
        own call site — rather than by calling the hook directly, so a signature that
        stopped receiving ``doctype`` fails here.
        """
        from frappe.model.db_query import DatabaseQuery

        self.assertEqual(
            DatabaseQuery(OTHER, user=self.user).get_permission_query_conditions(), "1=0"
        )
        self.assertIn(
            frappe.db.escape(BUILDING),
            DatabaseQuery(NAMED, user=self.user).get_permission_query_conditions(),
        )

    def test_unrestricted_permission_still_covers_every_doctype(self):
        """A permission with no applicable_for keeps applying everywhere."""
        # The permission is shared with the other cases in this class, so what this one
        # widens it hands back.
        self.addCleanup(self._set_applicable_for, NAMED)
        self._set_applicable_for(None)

        for doctype in (NAMED, OTHER):
            self.assertIn(
                frappe.db.escape(BUILDING),
                HP.building_scope_query(user=self.user, doctype=doctype),
            )

    def _set_applicable_for(self, value):
        self.permission.reload()
        self.permission.applicable_for = value
        self.permission.save(ignore_permissions=True)
        frappe.cache.hdel("user_permissions", self.user)
        frappe.local.cache = {}
