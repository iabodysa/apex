# Copyright (c) 2026, AFMCO and contributors
"""Every shipped Workspace keeps name == label == title (A-126).

File-level test -- stdlib only, no Frappe site needed.

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

Run standalone:  python3 -m unittest apex.tests.test_workspace_identity_consistency -v
"""

import glob
import json
import os
import unittest
from pathlib import Path

import apex

APP_ROOT = str(Path(apex.__file__).resolve().parent)
WORKSPACE_GLOB = os.path.join(APP_ROOT, "*", "workspace", "*", "*.json")

# Workspaces allowed to break the name == label == title rule, by path relative
# to apex/. DELIBERATELY EMPTY: every workspace the app ships is consistent as of
# A-126. Adding an entry here is an explicit, reviewable exemption -- it is not a
# place to park a new violation.
KNOWN_INCONSISTENT: frozenset = frozenset()


def _workspaces():
    """(relative path, parsed record) for every is_standard Workspace JSON."""
    out = []
    for path in sorted(glob.glob(WORKSPACE_GLOB)):
        with open(path, encoding="utf-8") as fh:
            out.append((os.path.relpath(path, APP_ROOT), json.load(fh)))
    return out


class TestWorkspaceIdentityConsistency(unittest.TestCase):

    def test_scan_is_non_vacuous(self):
        """A glob that silently matches nothing would make every other assertion
        in this file pass for the wrong reason."""
        found = _workspaces()
        self.assertGreaterEqual(
            len(found), 9, f"workspace scan found only {len(found)} records -- glob drifted"
        )
        # Probe by PATH, not by name -- a non-vacuity guard must not restate the
        # assertion it is guarding.
        self.assertIn(
            os.path.join("salis", "workspace", "fleet", "fleet.json"),
            {rel for rel, _ in found},
            "the Fleet workspace must be in scope of this scan",
        )

    def test_name_label_and_title_are_identical(self):
        """name drives the awesomebar label + its translation, label drives
        autoname, title drives parent_page resolution. All three must agree."""
        violations = {}
        for rel, data in _workspaces():
            if rel in KNOWN_INCONSISTENT:
                continue
            identity = (data.get("name"), data.get("label"), data.get("title"))
            if len(set(identity)) != 1 or not identity[0]:
                violations[rel] = identity
        self.assertEqual(
            violations,
            {},
            "workspace name/label/title disagree (name, label, title):\n"
            + "\n".join(f"  {rel}: {ids}" for rel, ids in sorted(violations.items())),
        )

    def test_every_parent_page_resolves_to_a_shipped_title(self):
        """A parent_page that matches no shipped title is a permanently orphaned
        child: Frappe compares it to the parent's title and simply renders nothing."""
        records = _workspaces()
        titles = {data.get("title") for _, data in records}
        orphans = {
            rel: data.get("parent_page")
            for rel, data in records
            if data.get("parent_page") and data["parent_page"] not in titles
        }
        self.assertEqual(
            orphans,
            {},
            "workspace parent_page does not match any shipped workspace title -- "
            "these children would never render:\n"
            + "\n".join(f"  {rel}: parent_page={pp!r}" for rel, pp in sorted(orphans.items())),
        )

if __name__ == "__main__":
    unittest.main()
