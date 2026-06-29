# Copyright (c) 2026, AFMCO and contributors
"""Project row-scoping tests for the has_permission hook: a scoped user may only
act on documents in their granted projects (and not on project-less documents),
while an oversight role sees everything."""


import frappe
from frappe.tests.utils import FrappeTestCase

from apex_habitat.salis.permissions import scoped_has_permission
from apex_habitat.tests._helpers import _user


class TestProjectScoping(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.pa = cls._project("Scope A")
        cls.pb = cls._project("Scope B")
        cls.sup = _user("scope_sup@example.com", "Fleet Supervisor")   # [#pv84q9]
        cls.mgr = _user("scope_mgr@example.com", "Fleet Manager")      # [#f1j142]
        if not frappe.db.exists("User Permission",
                                {"allow": "Project", "for_value": cls.pa, "user": cls.sup}):
            frappe.get_doc({"doctype": "User Permission", "allow": "Project",
                            "for_value": cls.pa, "user": cls.sup}).insert(ignore_permissions=True)

    @classmethod
    def tearDownClass(cls):
        # setUpClass commits a Project + User Permission OUTSIDE FrappeTestCase's
        # per-method savepoint rollback; without this they leak across the test DB
        # (the @example.com Project User Permission cross-test-pollution class).
        frappe.set_user("Administrator")
        frappe.db.delete("User Permission",
                         {"allow": "Project", "for_value": cls.pa, "user": cls.sup})
        for p in (cls.pa, cls.pb):
            if frappe.db.exists("Project", p):
                frappe.delete_doc("Project", p, ignore_permissions=True, force=True)
        frappe.db.commit()
        super().tearDownClass()

    @staticmethod
    def _project(name):
        p = frappe.db.get_value("Project", {"project_name": name}, "name")
        if not p:
            p = frappe.get_doc({"doctype": "Project", "project_name": name}).insert(
                ignore_permissions=True).name
        return p

    def _doc(self, project):
        return frappe._dict({"doctype": "Fuel Request", "project": project})

    def test_scoped_user_allowed_in_their_project(self):
        self.assertIsNone(scoped_has_permission(self._doc(self.pa), "read", user=self.sup))

    def test_scoped_user_denied_other_project(self):
        self.assertFalse(scoped_has_permission(self._doc(self.pb), "read", user=self.sup))

    def test_scoped_user_denied_null_project(self):
        self.assertFalse(scoped_has_permission(self._doc(None), "read", user=self.sup))

    def test_unscoped_user_sees_everything(self):
        self.assertIsNone(scoped_has_permission(self._doc(self.pb), "read", user=self.mgr))
        self.assertIsNone(scoped_has_permission(self._doc(None), "read", user=self.mgr))
