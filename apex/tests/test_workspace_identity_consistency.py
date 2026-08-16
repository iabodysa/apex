# Copyright (c) 2026, AFMCO and contributors
"""Every shipped Workspace keeps name == label == title, on the site, not just on disk.

Frappe reads a workspace's identity from three fields that must not drift:

  * ``name``  -- the row's primary key. ``frappe/desk/desktop.py`` builds the boot
    sidebar payload as ``page["label"] = _(page.get("name"))``, so the awesomebar
    "Open <workspace>" entry AND its translation lookup are keyed on the name. A
    name that is not the human label ships an untranslated, mis-cased entry.
  * ``label`` -- the Workspace DocType autonames ``field:label``, so the name is
    supposed to BE the label. ``frappe.rename_doc`` even writes the new key back
    into ``label`` (update_autoname_field), which is the framework stating the
    invariant outright.
  * ``title`` -- what ``parent_page`` is compared against. Both
    ``Workspace.get_children`` (``filters={"parent_page": doc.title}``) and the
    Desk sidebar (``page.parent_page == item.title``) resolve a child by the
    parent's TITLE and never by its name.

The failure mode is silent, which is why it needs a guard: a child declaring its
parent by name renders nowhere, forever, with no error anywhere.

READS THE SITE, NOT THE JSON. What breaks is the row Desk actually resolves against
at request time (``frappe.get_cached_doc("Workspace", name)`` -- desktop.py:48), and
that row can legally differ from the shipped JSON the moment a patch, a hand fix, or
a migrate re-import has run. Scoping to Apex's own workspaces uses the same table the
framework itself uses to decide app ownership -- ``Module Def.app_name`` -- rather
than a hand-kept list of module names or a directory glob.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

# Workspaces allowed to break the name == label == title rule, by Workspace name.
# DELIBERATELY EMPTY: every workspace the app ships is consistent. Adding an entry
# here is an explicit, reviewable exemption -- it is not a place to park a new
# violation.
KNOWN_INCONSISTENT: frozenset = frozenset()


def _apex_workspaces():
    """Every Workspace row belonging to a module Apex owns (Module Def.app_name)."""
    modules = frappe.get_all("Module Def", filters={"app_name": "apex"}, pluck="name")
    return frappe.get_all(
        "Workspace",
        filters={"module": ("in", modules)},
        fields=["name", "label", "title", "parent_page"],
    )


class TestWorkspaceIdentityConsistency(FrappeTestCase):

    def test_scan_is_non_vacuous(self):
        """A filter that silently matched nothing would make every other assertion
        in this file pass for the wrong reason."""
        found = _apex_workspaces()
        self.assertGreaterEqual(
            len(found), 9, f"workspace scan found only {len(found)} records -- scope drifted"
        )
        self.assertIn(
            "Fleet",
            {row.name for row in found},
            "the Fleet workspace must be in scope of this scan",
        )

    def test_name_label_and_title_are_identical(self):
        """name drives the awesomebar label + its translation, label drives
        autoname, title drives parent_page resolution. All three must agree."""
        violations = {}
        for row in _apex_workspaces():
            if row.name in KNOWN_INCONSISTENT:
                continue
            identity = (row.name, row.label, row.title)
            if len(set(identity)) != 1 or not identity[0]:
                violations[row.name] = identity
        self.assertEqual(
            violations,
            {},
            "workspace name/label/title disagree (name, label, title):\n"
            + "\n".join(f"  {name}: {ids}" for name, ids in sorted(violations.items())),
        )

    def test_every_parent_page_resolves_to_a_shipped_title(self):
        """A parent_page that matches no shipped title is a permanently orphaned
        child: Frappe compares it to the parent's title and simply renders nothing."""
        records = _apex_workspaces()
        titles = {row.title for row in records}
        orphans = {
            row.name: row.parent_page
            for row in records
            if row.parent_page and row.parent_page not in titles
        }
        self.assertEqual(
            orphans,
            {},
            "workspace parent_page does not match any shipped workspace title -- "
            "these children would never render:\n"
            + "\n".join(f"  {name}: parent_page={pp!r}" for name, pp in sorted(orphans.items())),
        )
