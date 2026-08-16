# Copyright (c) 2026, AFMCO and contributors
"""A-122 — a child workspace is reachable only when every ancestor is reachable too.

The SIM fold retired the root ``SIM Operations`` workspace and moved its surface into
``Custody and Costs``, which hangs off ``Habitat``. Nothing in the permission model broke:
``/app/custody`` still resolves, ``Custody and Costs`` still grants ``SIM Operations User``,
and every static gate stayed green. What broke was navigation, and only navigation.

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

A-127 promoted the scan itself into ``tests/workspace_reachability.py`` so a second
suite (``test_b5_role_workspaces.py``) can assert parent-chain reachability without
either copying the logic or importing a sibling ``test_*`` module — which
``tests/test_no_cross_test_imports.py`` forbids. This file keeps the A-122 persona
assertions and the detector's own falsifiability tests.
"""

import unittest

from apex.tests.workspace_reachability import (
    ancestors as _ancestors,
    orphan_pairs as _orphan_pairs,
    workspace_titles as _workspace_titles,
    workspaces as _workspaces,
)

# The A-122 persona: the single role a SIM operator holds, and the workspace that
# absorbed the SIM surface when the root SIM Operations workspace was folded away.
SIM_ROLE = "SIM Operations User"
SIM_WORKSPACE = "Custody and Costs"

# Ratchet, not an excuse list. A-125 closed the last two entries — Compliance and Rentals
# granted Government Relations Officer and Internal Auditor while its Salis parent granted
# neither — by widening the Salis root, so the set is now empty and ANY orphan fails.
KNOWN_ORPHAN_PAIRS = frozenset()


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
            f"the {SIM_ROLE} / '{SIM_WORKSPACE}' pair must be fixed in the workspace "
            "JSON, never frozen into the ratchet",
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
        """Every population this file's assertions grade must actually hold something.

        This does not assert that every workspace carries roles — an EMPTY roles list is
        world-visible by design (``blocks()`` treats it as blocking nobody), and the global
        root ``Apex`` plus the personal ``My Tasks`` page are deliberately world-visible.
        The (workspace, role) orphan model only needs SOME roled workspace to exist so
        ``orphan_pairs`` has something to grade; requiring every single workspace to carry
        roles was asserting a least-privilege policy this file does not otherwise enforce,
        over two workspaces that ship empty roles on purpose.
        """
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
        self.assertTrue(
            [t for t, p in pages.items() if p["roles"]],
            "no workspace carries a roles list, so the (workspace, role) orphan model "
            "would be vacuous",
        )


if __name__ == "__main__":
    unittest.main()
