# Copyright (c) 2026, afmcoltd
"""A Company User Permission with ``hide_descendants=1`` grants ONLY that node.

Of apex's three scoped axes (Building, Project, Company) only Company is a tree doctype:
``frappe.get_meta("Company").is_nested_set()`` is True (it carries ``lft``/``rgt`` and
``nsm_parent_field = "parent_company"``), while Building and Project carry neither field.
``hide_descendants`` therefore only matters on the Company axis, which
``apex.logistay.permissions`` (SIM Operations) scopes.

``permission_scope.allowed_for()`` and ``permission_scope.for_doctype()`` never read a row's
``hide_descendants`` themselves. They do not need to: frappe's own ``get_user_permissions``
unconditionally adds the permitted node, then — only when the doctype is a nested set AND
``hide_descendants`` is falsy — adds one row per descendant. By the time either apex function
sees the row list the flag has already decided which rows exist; both were already correct,
because they read the framework's resolver rather than the raw ``User Permission`` table —
the same discipline ``test_permission_scope_applicable_for.py`` documents for the sibling
``applicable_for`` field, whose loss to a raw-table ``pluck`` was a real, shipped bug. This
suite is the regression lock against reintroducing that pattern here.

The tree is ERPNext's own: ``_Test Company 4`` is a group whose only child is
``_Test Company 5``, both from ``erpnext/setup/doctype/company/test_records.json``. The
previous form of this file minted a two-level Company tree in ``setUpClass`` and deleted it
in ``tearDownClass`` — two Companies built to assert a flag on one User Permission. Company
fixtures ARE idempotent, unlike Project's: Company autonames from ``company_name``, so a
rebuild finds the name already taken and is skipped rather than colliding.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.utils import permission_scope
from apex.logistay import permissions as LP
from apex.tests._helpers import _user

test_dependencies = ["Company"]

PARENT = "_Test Company 4"
CHILD = "_Test Company 5"
SCOPED_DOCTYPE = "Telecom Contract"
CACHE_KEY = "apex_allowed_companies"


class TestHideDescendantsNarrowsCompanyScope(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.user = _user("phd_sim_user@example.com", "SIM Operations User")
        cls.permission = frappe.get_doc(
            {
                "doctype": "User Permission",
                "user": cls.user,
                "allow": "Company",
                "for_value": PARENT,
                "hide_descendants": 0,
            }
        ).insert(ignore_permissions=True)
        cls.addClassCleanup(frappe.cache.hdel, "user_permissions", cls.user)

    def setUp(self):
        # The permission is shared by every case here, so the flag each one flips is handed
        # back before the next reads it.
        self.addCleanup(self._set_hide_descendants, 0)
        self.addCleanup(frappe.set_user, "Administrator")
        self._set_hide_descendants(0)

    def _set_hide_descendants(self, value):
        self.permission.reload()
        self.permission.hide_descendants = value
        self.permission.save(ignore_permissions=True)
        frappe.cache.hdel("user_permissions", self.user)
        frappe.local.cache = {}

    def test_company_is_the_only_scoped_tree_doctype(self):
        """Grounds the whole file: Company is a tree; Building and Project are not."""
        self.assertTrue(frappe.get_meta("Company").is_nested_set())
        self.assertFalse(frappe.get_meta("Building").is_nested_set())
        self.assertFalse(frappe.get_meta("Project").is_nested_set())

    def test_hide_descendants_off_grants_the_whole_subtree(self):
        """The framework default: the named node AND its descendants are allowed."""
        rows = frappe.permissions.get_user_permissions(self.user)["Company"]
        self.assertEqual(sorted(r.doc for r in rows), sorted([PARENT, CHILD]))
        self.assertEqual(
            sorted(permission_scope.allowed_for(self.user, "Company", CACHE_KEY)),
            sorted([PARENT, CHILD]),
        )

    def test_hide_descendants_on_grants_only_the_named_node(self):
        """hide_descendants=1: the child never enters the resolved set at all."""
        self._set_hide_descendants(1)
        rows = frappe.permissions.get_user_permissions(self.user)["Company"]
        self.assertEqual([r.doc for r in rows], [PARENT])
        self.assertEqual(
            permission_scope.allowed_for(self.user, "Company", CACHE_KEY), [PARENT]
        )

    def test_for_doctype_preserves_the_narrowing_in_both_directions(self):
        """applicable_for narrowing composes with hide_descendants with no special-casing."""
        values_off = permission_scope.allowed_for(self.user, "Company", CACHE_KEY)
        self.assertEqual(
            sorted(
                permission_scope.for_doctype(self.user, "Company", SCOPED_DOCTYPE, values_off)
            ),
            sorted([PARENT, CHILD]),
        )

        self._set_hide_descendants(1)
        values_on = permission_scope.allowed_for(self.user, "Company", CACHE_KEY)
        self.assertEqual(
            permission_scope.for_doctype(self.user, "Company", SCOPED_DOCTYPE, values_on),
            [PARENT],
        )

    def test_logistay_query_fragment_excludes_the_hidden_descendant(self):
        """The real SIM Operations consumer: the list/report WHERE fragment."""
        condition_off = LP.company_scope_query(user=self.user, doctype=SCOPED_DOCTYPE)
        self.assertIn(frappe.db.escape(PARENT), condition_off)
        self.assertIn(frappe.db.escape(CHILD), condition_off)

        self._set_hide_descendants(1)
        condition_on = LP.company_scope_query(user=self.user, doctype=SCOPED_DOCTYPE)
        self.assertIn(frappe.db.escape(PARENT), condition_on)
        self.assertNotIn(frappe.db.escape(CHILD), condition_on)

    def test_logistay_has_permission_denies_the_hidden_descendant(self):
        """The real SIM Operations consumer: the form/REST has_permission verdict."""
        doc = frappe._dict(doctype=SCOPED_DOCTYPE, company=CHILD)
        self.assertIsNone(LP.company_scoped_has_permission(doc, "read", user=self.user))

        self._set_hide_descendants(1)
        self.assertIs(LP.company_scoped_has_permission(doc, "read", user=self.user), False)
