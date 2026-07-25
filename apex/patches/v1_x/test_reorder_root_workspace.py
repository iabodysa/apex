# Copyright (c) 2026, AFMCO and contributors
"""P-108: prove reorder_root_workspace_creation.execute() sorts the module root first.

Desk breadcrumbs resolve a DocType's module workspace as
``module_wise_workspaces[module][0]`` (frappe breadcrumbs.js:161), and that list
is built ordered by the Workspace row's ``creation`` column
(``Workspace.get_module_wise_workspaces``, ``order_by="creation"`` at
workspace.py:140). The P-108 patch rewrites the single public root workspace's
``creation`` to one second before its earliest sibling, so the root always sorts
first — making ``/app/<module-root>`` the deterministic breadcrumb target no
matter what order the workspace JSONs were imported in.

This test proves the mechanism INDEPENDENT of the install path: a fresh install
runs the SAME ``execute()`` via the ``after_install`` hook and a migrated site
via ``after_migrate``. We synthesise the OUT-OF-ORDER condition (child workspaces
created BEFORE the module root) on a real single-root module, run ``execute()``,
and assert root-first ordering is restored — asserting both the raw ``creation``
order and the framework resolver (``get_module_wise_workspaces``) the breadcrumb
consumes.

Self-contained: creates its own synthetic children, forces ``developer_mode`` off
so the insert does not export workspace JSON to the repo tree, and restores the
real root's ``creation`` on teardown.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, get_datetime

from apex.patches.v1_x import reorder_root_workspace_creation

# [#2sb8rz]
_MODULE = "Salis"
_ROOT = "Salis"  # [#h4z3kl]


class TestReorderRootWorkspace(FrappeTestCase):
    def setUp(self):
        self._synthetic = []
        # [#a140as] The single-public-root shape is the precondition execute() acts on
        # AND the thing this class asserts, so skipping on it reported success for a
        # site whose workspaces never synced. The app ships salis/workspace/salis.json
        # with parent_page "" and its two children under it, and install/migrate
        # imports them, so anything else is a real regression — fail, do not skip.
        roots = self._public_roots()
        self.assertEqual(
            roots,
            [_ROOT],
            f"{_MODULE} must carry exactly one public root workspace ({_ROOT}); "
            f"found {roots}. The shipped workspace JSONs are imported on install/migrate.",
        )
        # [#k5mwfr]
        self._orig_dev_mode = frappe.conf.get("developer_mode")
        frappe.conf.developer_mode = 0
        self._orig_root_creation = frappe.db.get_value("Workspace", _ROOT, "creation")

    def tearDown(self):
        for name in self._synthetic:
            if frappe.db.exists("Workspace", name):
                frappe.delete_doc("Workspace", name, force=True, ignore_permissions=True)
        if getattr(self, "_orig_root_creation", None) and frappe.db.exists("Workspace", _ROOT):
            # [#997j86]
            frappe.db.set_value(
                "Workspace", _ROOT, "creation", self._orig_root_creation, update_modified=False
            )
        if hasattr(self, "_orig_dev_mode"):
            frappe.conf.developer_mode = self._orig_dev_mode

    # [#f9hua6]
    def _public_roots(self):
        """The public, parent-less workspaces of _MODULE — the set execute() requires
        to hold exactly one member before it will reorder anything."""
        return frappe.get_all(
            "Workspace",
            filters={"module": _MODULE, "public": 1, "for_user": "", "parent_page": ""},
            pluck="name",
        )

    def _module_creations(self):
        """{workspace_name: creation-as-datetime} for every public row of _MODULE."""
        rows = frappe.get_all(
            "Workspace",
            filters={"module": _MODULE, "public": 1, "for_user": ""},
            fields=["name", "creation"],
        )
        return {r.name: get_datetime(r.creation) for r in rows}

    def _make_child_before_root(self, label, seconds_before):
        """Insert a public child workspace, then back-date its creation before the root."""
        doc = frappe.get_doc(
            {
                "doctype": "Workspace",
                "label": label,
                "title": label,
                "module": _MODULE,
                "public": 1,
                "parent_page": _ROOT,
                "content": "[]",
            }
        ).insert(ignore_permissions=True)
        self._synthetic.append(doc.name)
        root_creation = get_datetime(frappe.db.get_value("Workspace", _ROOT, "creation"))
        frappe.db.set_value(
            "Workspace",
            doc.name,
            "creation",
            add_to_date(root_creation, seconds=-seconds_before),
            update_modified=False,
        )
        return doc.name

    # [#kz11hh]
    def test_execute_orders_root_before_every_sibling(self):
        h = frappe.generate_hash(length=12)
        child_a = self._make_child_before_root(f"P108 Child A {h}", seconds_before=30)
        child_b = self._make_child_before_root(f"P108 Child B {h}", seconds_before=20)

        # [#2lpurj]
        before = self._module_creations()
        root_before = before.pop(_ROOT)
        self.assertTrue(
            any(created < root_before for created in before.values()),
            "precondition failed: expected at least one sibling created before the root",
        )
        self.assertIn(child_a, before)
        self.assertIn(child_b, before)

        reorder_root_workspace_creation.execute()

        # [#k8t1ki]
        after = self._module_creations()
        root_after = after.pop(_ROOT)
        for name, created in after.items():
            self.assertLess(
                root_after,
                created,
                f"after execute() the root must sort before sibling {name}",
            )

        # [#1fvlcv]
        from frappe.desk.doctype.workspace.workspace import Workspace

        ordered = Workspace.get_module_wise_workspaces().get(_MODULE, [])
        self.assertTrue(ordered, f"no public workspaces resolved for module {_MODULE}")
        self.assertEqual(
            ordered[0],
            _ROOT,
            "module_wise_workspaces[module][0] must be the module root — the breadcrumb target",
        )

    def test_execute_is_idempotent(self):
        # [#kilssi]
        child = self._make_child_before_root(f"P108 Child C {frappe.generate_hash(length=12)}", 30)  # noqa: F841

        reorder_root_workspace_creation.execute()
        first = get_datetime(frappe.db.get_value("Workspace", _ROOT, "creation"))
        reorder_root_workspace_creation.execute()
        second = get_datetime(frappe.db.get_value("Workspace", _ROOT, "creation"))

        self.assertEqual(first, second, "second execute() must not move an already-first root")


if __name__ == "__main__":
    import unittest

    unittest.main()
