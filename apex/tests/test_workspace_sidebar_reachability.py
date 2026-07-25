# Copyright (c) 2026, AFMCO and contributors
"""A-122 — a child workspace is reachable only when every ancestor is reachable too.

The SIM fold retired the root ``SIM Operations`` workspace and moved its surface into
``Custody``, which hangs off ``Habitat``. Nothing in the permission model broke:
``/app/custody`` still resolves, ``Custody`` still grants ``SIM Operations User``, and
every static gate stayed green. What broke was navigation, and only navigation.

Frappe draws the desk sidebar in two stages. ``get_workspace_sidebar_items``
(frappe/desk/desktop.py) drops any workspace the session user is not permitted on —
``Workspace.is_permitted`` passes only when the roles child table is empty or shares a
role with the user. The client then seeds the sidebar from ROOT pages alone,
``page.parent_page == "" || page.parent_page == null``
(frappe/public/js/frappe/views/workspace/workspace.js, ``make_sidebar``), and nests each
child under an ALREADY RENDERED parent via
``pages.filter(page => page.parent_page == item.title)``.

So a child whose parent the user cannot see is never drawn. Worse, the permitted list is
not empty — the child is in it — so the ``Welcome Workspace`` fallback never fires
either, and the persona lands on a blank sidebar. A user holding only
``SIM Operations User`` hit exactly that.

Two consequences this file encodes:

- ``parent_page`` is matched against the parent's TITLE by the client, so this scan keys
  workspaces by title, not by record name.
- an ancestor that is public-but-hidden is dropped for every user without
  ``Workspace Manager``, which orphans its whole subtree the same way.

File-level and stdlib-only on purpose: the invariant is a property of the shipped
is_standard JSON, so it has to fail on the change that writes the bad JSON rather than on
a site that has already migrated it.
"""

import glob
import json
import os
import unittest

_APP = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_WORKSPACE_GLOB = os.path.join(_APP, "*", "workspace", "*", "*.json")

# The A-122 persona: the single role a SIM operator holds, and the workspace that
# absorbed the SIM surface when the root SIM Operations workspace was folded away.
SIM_ROLE = "SIM Operations User"
SIM_WORKSPACE = "Custody"

# Ratchet, not an excuse list: these two pairs pre-date A-122 and are a live navigation
# gap on the board, so the guard freezes them exactly rather than tolerating any orphan.
KNOWN_ORPHAN_PAIRS = frozenset(
    {
        ("Compliance and Rentals", "Government Relations Officer"),
        ("Compliance and Rentals", "Internal Auditor"),
    }
)


def _workspaces():
    """title -> {roles, parent, hidden, path} for every is_standard workspace on disk."""
    pages = {}
    for path in sorted(glob.glob(_WORKSPACE_GLOB)):
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        title = data.get("title") or data.get("name")
        pages[title] = {
            "roles": {row["role"] for row in data.get("roles", []) if row.get("role")},
            "parent": data.get("parent_page") or "",
            "hidden": bool(data.get("is_hidden")),
            "path": os.path.relpath(path, _APP),
        }
    return pages


def _workspace_titles():
    """Every workspace title on disk, WITH duplicates, so a collision stays visible."""
    titles = []
    for path in sorted(glob.glob(_WORKSPACE_GLOB)):
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        titles.append(data.get("title") or data.get("name"))
    return titles


def _ancestors(pages, title):
    """Parent chain from the immediate parent up to the root; None if the chain is broken."""
    chain = []
    seen = {title}
    parent = pages[title]["parent"]
    while parent:
        if parent not in pages or parent in seen:
            return None
        chain.append(parent)
        seen.add(parent)
        parent = pages[parent]["parent"]
    return chain


def _orphan_pairs(pages):
    """(workspace, role) pairs whose sidebar node no holder of that role can ever reach."""
    orphans = set()
    for title, page in pages.items():
        chain = _ancestors(pages, title)
        if chain is None:
            continue
        for ancestor in chain:
            forebear = pages[ancestor]
            for role in page["roles"]:
                if forebear["hidden"] or (forebear["roles"] and role not in forebear["roles"]):
                    orphans.add((title, role))
    return orphans


class TestSimOperationsSidebarReachability(unittest.TestCase):
    """The A-122 persona itself, asserted by name so it can never be ratcheted away."""

    def test_sim_operations_user_reaches_the_custody_workspace(self):
        pages = _workspaces()
        self.assertIn(SIM_WORKSPACE, pages, f"workspace '{SIM_WORKSPACE}' is missing from disk")
        self.assertIn(
            SIM_ROLE,
            pages[SIM_WORKSPACE]["roles"],
            f"'{SIM_WORKSPACE}' no longer grants {SIM_ROLE} — the SIM surface is unreachable",
        )
        chain = _ancestors(pages, SIM_WORKSPACE)
        self.assertIsNotNone(chain, f"'{SIM_WORKSPACE}' has a broken or cyclic parent chain")
        self.assertTrue(
            chain,
            f"'{SIM_WORKSPACE}' is now a root page, so this guard proves nothing — "
            "re-point it at the parent it actually hangs off",
        )
        for ancestor in chain:
            forebear = pages[ancestor]
            self.assertFalse(
                forebear["hidden"],
                f"ancestor '{ancestor}' ({forebear['path']}) is hidden, so its whole subtree "
                "drops out of the sidebar for every non-Workspace-Manager",
            )
            self.assertTrue(
                not forebear["roles"] or SIM_ROLE in forebear["roles"],
                f"ancestor '{ancestor}' ({forebear['path']}) does not grant {SIM_ROLE}, so a "
                f"user holding only that role never sees '{SIM_WORKSPACE}' in the sidebar",
            )

    def test_the_persona_pair_is_never_allowlisted(self):
        self.assertNotIn(
            (SIM_WORKSPACE, SIM_ROLE),
            KNOWN_ORPHAN_PAIRS,
            "the A-122 persona must be fixed in the workspace JSON, never frozen into the ratchet",
        )


class TestWorkspaceParentChainIntegrity(unittest.TestCase):
    """The general parent/child visibility invariant behind the A-122 regression."""

    def test_no_new_orphaned_workspace_role_pairs(self):
        found = _orphan_pairs(_workspaces())
        self.assertEqual(
            found,
            set(KNOWN_ORPHAN_PAIRS),
            "orphaned (workspace, role) pairs changed. New entries mean a persona lost its "
            "sidebar; removed entries mean a gap was fixed and the ratchet must shrink.",
        )

    def test_every_parent_page_resolves_to_a_workspace_on_disk(self):
        pages = _workspaces()
        for title, page in pages.items():
            with self.subTest(workspace=title):
                self.assertIsNotNone(
                    _ancestors(pages, title),
                    f"'{title}' ({page['path']}) declares parent_page '{page['parent']}', which "
                    "is not an on-disk workspace title — the record can never be nested",
                )

    def test_workspace_titles_are_unique(self):
        titles = _workspace_titles()
        duplicates = sorted({t for t in titles if titles.count(t) > 1})
        self.assertEqual(
            duplicates,
            [],
            f"duplicate workspace titles {duplicates}: parent_page resolves by title and the "
            "sidebar de-duplicates roots by title, so one of each pair is silently dropped",
        )

    def test_scan_is_non_vacuous(self):
        pages = _workspaces()
        self.assertTrue(pages, "no workspace JSON discovered — the glob is wrong")
        self.assertTrue(
            [t for t, p in pages.items() if not p["parent"]],
            "no root workspace discovered, so the sidebar would have nothing to seed from",
        )
        self.assertTrue(
            [t for t, p in pages.items() if p["parent"]],
            "no child workspace discovered, so the parent/child guard would be vacuous",
        )
        for title, page in pages.items():
            with self.subTest(workspace=title):
                self.assertTrue(
                    page["roles"],
                    f"'{title}' ({page['path']}) ships an empty roles list — it is world-visible, "
                    "and the (workspace, role) orphan model cannot describe it",
                )


class TestOrphanDetector(unittest.TestCase):
    """Prove the detector can fail, so a green run above is evidence and not silence."""

    @staticmethod
    def _tree(parent_roles, child_roles, parent_hidden=False):
        return {
            "Root": {"roles": set(parent_roles), "parent": "", "hidden": parent_hidden, "path": "r"},
            "Leaf": {"roles": set(child_roles), "parent": "Root", "hidden": False, "path": "l"},
        }

    def test_detector_flags_a_child_role_the_parent_lacks(self):
        found = _orphan_pairs(self._tree(parent_roles=["Alpha"], child_roles=["Alpha", "Beta"]))
        self.assertEqual(found, {("Leaf", "Beta")})

    def test_detector_clears_a_child_whose_parent_grants_the_role(self):
        found = _orphan_pairs(self._tree(parent_roles=["Alpha", "Beta"], child_roles=["Beta"]))
        self.assertEqual(found, set())

    def test_detector_flags_every_role_under_a_hidden_parent(self):
        tree = self._tree(parent_roles=["Alpha"], child_roles=["Alpha"], parent_hidden=True)
        self.assertEqual(_orphan_pairs(tree), {("Leaf", "Alpha")})

    def test_detector_treats_an_empty_parent_role_list_as_world_visible(self):
        found = _orphan_pairs(self._tree(parent_roles=[], child_roles=["Beta"]))
        self.assertEqual(found, set())

    def test_broken_parent_chain_is_reported_by_its_own_guard_not_as_an_orphan(self):
        tree = {"Leaf": {"roles": {"Beta"}, "parent": "Ghost", "hidden": False, "path": "l"}}
        self.assertIsNone(_ancestors(tree, "Leaf"))
        self.assertEqual(_orphan_pairs(tree), set())


if __name__ == "__main__":
    unittest.main()
