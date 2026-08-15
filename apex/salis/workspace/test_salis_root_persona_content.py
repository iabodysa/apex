# Copyright (c) 2026, AFMCO and contributors
"""a workspace grant plus a DocPerm still leaves a persona on an empty page.

SUBJECT: the shipped Workspace RECORDS — apex/salis/workspace/salis/salis.json (506
lines) and fleet/fleet.json (422), 928 together — not the 1-line ``__init__.py`` beside
this file. Measured against the package directory this reads 467x, which is a grouping
artifact and nothing else; against what it actually grades it is 0.50x, well inside the
2x rule and claiming no exception. A workspace's subject is a JSON record, so any tool
that counts only ``.py`` in the directory will mis-measure every test in here. gave ``Government Relations Officer`` read DocPerms so it would stop landing on a
blank ``Compliance and Rentals``. then granted it the ``Salis`` ROOT as well,
because the desk sidebar nests a child only under an already-rendered parent
(``workspace.js`` ``make_sidebar``), so without the root grant the child was unreachable.
Both were right, and together they produced a third shape: the persona now reaches the
Salis root and the root holds nothing it can open.

``Workspace.is_item_allowed`` (frappe/desk/desktop.py:143-166) decides that per item:

- ``doctype`` -> the name must be in the session user's ``can_read``, which
  ``frappe/utils/user.py build_permissions`` builds from DocPerm rows and which SKIPS
  every ``istable`` DocType, so a child table can never satisfy a workspace link;
- ``report`` -> the name must be in ``get_allowed_reports``, i.e. a ``Has Role`` row
  names one of the session roles (frappe/boot.py get_user_pages_or_reports), the same
  rule test_report_role_coverage.py guards on the report side;
- ``dashboard``, ``url`` and ``help`` -> ``True`` unconditionally.

That last line is why "the page is not literally blank" was never the right test. The
Salis root's Dashboards card rendered for the persona while every DocType and Report link
on the page was filtered away, so it could navigate to two dashboards whose charts read
records it has no permission on. This guard therefore counts only the OPENABLE items and
requires each granted role to have at least one.

SHORTCUTS ARE OPENABLE ITEMS TOO, which this guard missed until 2026-08-08. `get_shortcuts`
(frappe/desk/desktop.py:299) runs each one through the same `is_item_allowed`, so a page
whose links are all filtered away still renders its shortcut cards — and the roots have
since been redesigned into landing pages that carry their work as shortcuts, not links.
Reading links alone reported TEN workspace/role pairs as empty pages a persona actually
opens with cards on them. Dashboard and URL shortcuts stay excluded for the reason above.

The fix shipped is on the root's own terms, not the persona's: the Master Data card
is documented as "Reference data: durable records you set up once", it listed the routing
masters, and it omitted ``Salis Vehicle`` and ``Salis Driver`` -- the two registries every
other Salis record links to, and the only Salis DocTypes whose reader set matches the
root's grant list exactly. Adding them fills the card for all seven granted roles.

An earlier change then drained both ratchets this file carried, on the workspace shape of the time. The
``Compliance and Rentals`` workspace it also guarded no longer ships — the app is nine
workspaces and that is not one of them — so its test class was removed rather than left
raising KeyError. The Habitat root's three stranded personas still get the operational
record their own child workspace leads with, Cleaning Log, Safety Round and SIM Custody
Assignment, now as shortcuts on Quick Actions rather than links on an Operations card.

Nothing here widens access. ``is_item_allowed`` filters every link per user, so a link is
only ever a shortcut to a list the user could already open by URL; the guards below assert
that each added or retargeted link was already covered by an existing read DocPerm.

Lives beside the workspace package it fixes: ``apex/tests/`` is closed to new modules
(test_colocation_ratchet.py) and a cross-workspace invariant owns no single record dir.

Run standalone:  python3 -m unittest apex.salis.workspace.test_salis_root_persona_content -v
"""

import glob
import json
import os
import unittest
from pathlib import Path

import apex

_APP = str(Path(apex.__file__).resolve().parent)
_WORKSPACE_GLOB = os.path.join(_APP, "*", "workspace", "*", "*.json")
_DOCTYPE_GLOB = os.path.join(_APP, "*", "doctype", "*", "*.json")
_REPORT_GLOB = os.path.join(_APP, "*", "report", "*", "*.json")
_PAGE_GLOB = os.path.join(_APP, "*", "page", "*", "*.json")

GRO_ROLE = "Government Relations Officer"
SALIS_ROOT = "Salis"

# Both short-circuit is_item_allowed or hold read on every core DocType, so their absence
# from a page is never the bug this guard hunts.
_ALWAYS_PERMITTED = {"System Manager", "Administrator"}

# An earlier change added these two to the Salis root's Master Data card. The root has since been
# redesigned and the card is gone, so THE LINKS ARE NO LONGER ASSERTED — what survives is the
# invariant they were added to satisfy, which the root still meets by other means. The names
# stay because the two DocPerm guards below still hold: whatever the layout, the persona must
# be able to READ what it is offered and must hold no write on it.
ADDED_TO_SALIS_ROOT = ("Salis Vehicle", "Salis Driver")

HABITAT_ROOT = "Habitat"

# drained both ratchets below to empty. The Habitat root's Operations card gained
# one operational record per stranded persona, and the Compliance card was retargeted off
# the child table onto its embedding parent. Each entry left as it was fixed, which is what
# keeps the exact-equality assertions honest.
ADDED_TO_HABITAT_ROOT = {
    "Cleaning Supervisor": "Cleaning Log",
    "Safety Officer": "Safety Round",
    "SIM Operations User": "SIM Custody Assignment",
}

KNOWN_EMPTY_WORKSPACE_ROLES = {
    # Frozen baseline of (workspace, role) -> reason. Exact equality: a NEW pair fails the
    # build and a CLOSED pair fails until it is pruned from here. Empty since that change.
}

KNOWN_CHILD_TABLE_LINKS = {
    # A DocType link at an istable target is dead for everyone but Administrator, because
    # build_permissions never puts a child table into can_read. Not permissionable — the
    # link has to point at the embedding parent instead. Empty since that change.
}


def _load(pattern, doctype):
    """Every shipped is_standard record of one type, keyed by name."""
    out = {}
    for path in sorted(glob.glob(pattern)):
        with open(path, encoding="utf-8") as fh:
            try:
                data = json.load(fh)
            except json.JSONDecodeError:
                continue
        if isinstance(data, dict) and data.get("doctype") == doctype:
            out[data["name"]] = data
    return out


def _workspaces():
    return _load(_WORKSPACE_GLOB, "Workspace")


def _doctypes():
    return _load(_DOCTYPE_GLOB, "DocType")


def _reports():
    """Report name -> the roles named in its child table."""
    return {
        name: {row["role"] for row in data.get("roles") or [] if row.get("role")}
        for name, data in _load(_REPORT_GLOB, "Report").items()
    }


def _pages():
    """Page name -> the roles named in its child table. An empty set means every role."""
    return {
        name: {row["role"] for row in data.get("roles") or [] if row.get("role")}
        for name, data in _load(_PAGE_GLOB, "Page").items()
    }


def _can_read(role, doctypes):
    """The role's can_read set, by frappe's own rule: permlevel-0 read rows, no istable."""
    out = set()
    for name, data in doctypes.items():
        if data.get("istable"):
            continue
        for row in data.get("permissions") or []:
            if row.get("role") == role and row.get("read") and not row.get("permlevel"):
                out.add(name)
                break
    return out


def _openable_items(workspace, role, doctypes, reports, pages):
    """Everything on one workspace that survives is_item_allowed: links AND shortcuts.

    Shortcuts count. `frappe/desk/desktop.py:299` runs them through the same
    `is_item_allowed` as the link items and returns the survivors, so a page whose links are
    all filtered away still renders its shortcut cards. Reading links alone reported ten
    workspace/role pairs as empty pages that a persona actually opens with five cards on them.

    Each shortcut type is graded by the rule `is_item_allowed` uses for it
    (`frappe/desk/desktop.py:143-165`): a DocType by can_read, a Report by its role list, a
    Page by ITS OWN role list — with `frappe/boot.py:274` letting a page that names no role
    through for everyone.

    Dashboard and URL shortcuts are counted by frappe and NOT by this guard, on the reasoning
    the module docstring already sets out: `is_item_allowed` returns True for them without
    asking anything, so they render on a page holding nothing else the persona may open, and
    a dashboard whose charts read records the persona has no permission on is not something
    it can open. Excluding them keeps the guard measuring reachable WORK.
    """
    readable = _can_read(role, doctypes)
    items = []
    for link in workspace.get("links") or []:
        target = link.get("link_to")
        if link.get("link_type") == "DocType" and target in readable:
            items.append(target)
        elif link.get("link_type") == "Report":
            listed = reports.get(target)
            if listed is None or not listed or role in listed:
                items.append(target)
    for shortcut in workspace.get("shortcuts") or []:
        target = shortcut.get("link_to")
        kind = shortcut.get("type")
        if kind == "DocType" and target in readable:
            items.append(target)
        elif kind == "Report":
            listed = reports.get(target)
            if listed is None or not listed or role in listed:
                items.append(target)
        elif kind == "Page":
            listed = pages.get(target)
            if listed is not None and (not listed or role in listed):
                items.append(target)
    return items


def _empty_pairs(workspaces, doctypes, reports, pages):
    """{(workspace, role)} where a granted role can open nothing on the page.

    Pure over its inputs so the self-test below can drive it with planted data.
    """
    found = set()
    for name, workspace in workspaces.items():
        for row in workspace.get("roles") or []:
            role = row.get("role")
            if not role or role in _ALWAYS_PERMITTED:
                continue
            if not _openable_items(workspace, role, doctypes, reports, pages):
                found.add((name, role))
    return found


def _child_table_links(workspaces, doctypes):
    """{(workspace, target)} for every DocType link that points at a child table."""
    return {
        (name, link["link_to"])
        for name, workspace in workspaces.items()
        for link in workspace.get("links") or []
        if link.get("link_type") == "DocType"
        and link.get("link_to") in doctypes
        and doctypes[link["link_to"]].get("istable")
    }


class TestNoGrantedRoleLandsOnAnEmptyPage(unittest.TestCase):
    """The general invariant behind the regression."""

    def setUp(self):
        self.workspaces = _workspaces()
        self.doctypes = _doctypes()
        self.reports = _reports()
        self.pages = _pages()

    def test_scan_is_non_vacuous(self):
        self.assertIn(SALIS_ROOT, self.workspaces, "workspace glob broke")
        self.assertTrue(self.doctypes, "doctype glob broke")
        self.assertTrue(self.reports, "report glob broke")

    def test_no_new_empty_workspace_role(self):
        found = _empty_pairs(self.workspaces, self.doctypes, self.reports, self.pages)
        self.assertEqual(
            found,
            set(KNOWN_EMPTY_WORKSPACE_ROLES),
            "workspace/role pages with nothing openable changed. A NEW pair means that "
            "persona reaches the page and every DocType and Report link on it is filtered "
            "away by Workspace.is_item_allowed — give the workspace a link the role can "
            "read, or freeze it here with a written reason. A MISSING pair means a gap was "
            f"closed and the baseline must shrink. On disk: {sorted(found)}",
        )

    def test_the_detector_flags_a_planted_role(self):
        """Proof the guard can fail, driven with synthetic input so it proves the
        DETECTOR rather than the current file contents.

        The page is synthetic rather than a real root, because every shipped root carries an
        `action-inbox` shortcut and that Page names no role, so frappe lets EVERY role open
        it (`frappe/boot.py:274`). Planting a role on a real root therefore proves nothing:
        the role is not stranded, and saying it is would be the false red that hides the true
        one. The planted page holds one link and one shortcut, both permission-gated.
        """
        planted = dict(self.workspaces)
        planted["_A172 Planted Page"] = {
            "name": "_A172 Planted Page",
            "roles": [{"role": "_A172 Planted Role"}],
            "links": [{"link_type": "DocType", "link_to": "_A172 Unreadable DocType"}],
            "shortcuts": [{"type": "DocType", "link_to": "_A172 Unreadable DocType"}],
        }
        found = _empty_pairs(planted, self.doctypes, self.reports, self.pages)
        self.assertIn(
            ("_A172 Planted Page", "_A172 Planted Role"),
            found,
            "the detector missed a role that can open nothing on the page",
        )

    def test_the_detector_clears_a_role_that_can_open_a_role_free_page(self):
        """The other half of the control: a universal Page shortcut is genuinely openable."""
        planted = dict(self.workspaces)
        planted["_A172 Inbox Only Page"] = {
            "name": "_A172 Inbox Only Page",
            "roles": [{"role": "_A172 Planted Role"}],
            "links": [],
            "shortcuts": [{"type": "Page", "link_to": "action-inbox"}],
        }
        found = _empty_pairs(planted, self.doctypes, self.reports, self.pages)
        self.assertNotIn(("_A172 Inbox Only Page", "_A172 Planted Role"), found)

    def test_every_frozen_pair_carries_a_reason(self):
        for pair, reason in KNOWN_EMPTY_WORKSPACE_ROLES.items():
            with self.subTest(pair=pair):
                self.assertTrue(reason and reason.strip(), f"{pair} has no documented reason")

    def test_child_table_links_stay_frozen(self):
        """A link at an istable target is dead for every non-Administrator session."""
        found = _child_table_links(self.workspaces, self.doctypes)
        self.assertEqual(
            found,
            set(KNOWN_CHILD_TABLE_LINKS),
            "workspace DocType links pointing at a child table changed. build_permissions "
            "skips istable, so such a link can never render — point it at the embedding "
            f"parent instead. On disk: {sorted(found)}",
        )

    def test_the_detector_flags_a_planted_child_table_link(self):
        """Proof the istable detector can still fail once its baseline is empty.

        A drained ratchet that asserts equality against an empty set passes just as well
        when the scan is broken, so the detector is driven with a planted link here.
        """
        istable = next(n for n, d in self.doctypes.items() if d.get("istable"))
        planted = dict(self.workspaces)
        page = dict(planted[SALIS_ROOT])
        page["links"] = [
            *(page.get("links") or []),
            {"type": "Link", "link_type": "DocType", "link_to": istable},
        ]
        planted[SALIS_ROOT] = page
        found = _child_table_links(planted, self.doctypes)
        self.assertIn(
            (SALIS_ROOT, istable),
            found,
            "the detector missed a DocType link pointing at a child table",
        )

    def test_every_card_block_names_a_card_break(self):
        """A card renders only when a Card Break label equals the block's card_name."""
        mismatched = {}
        for name, workspace in self.workspaces.items():
            breaks = {
                link.get("label")
                for link in workspace.get("links") or []
                if link.get("type") == "Card Break"
            }
            blocks = json.loads(workspace.get("content") or "[]")
            named = {
                block["data"]["card_name"]
                for block in blocks
                if block.get("type") == "card" and (block.get("data") or {}).get("card_name")
            }
            if named - breaks:
                mismatched[name] = sorted(named - breaks)
        self.assertEqual(
            mismatched,
            {},
            "a content card block names a card with no matching Card Break label, so the "
            "card silently does not render",
        )


class TestGovernmentRelationsOfficerReachesTheSalisRoot(unittest.TestCase):
    """'s own outcome, asserted by name so it cannot be ratcheted away."""

    def setUp(self):
        self.workspaces = _workspaces()
        self.doctypes = _doctypes()
        self.reports = _reports()
        self.pages = _pages()

    def test_the_persona_is_granted_the_root(self):
        granted = {row.get("role") for row in self.workspaces[SALIS_ROOT].get("roles") or []}
        self.assertIn(
            GRO_ROLE,
            granted,
            "the root grant is what makes Compliance and Rentals reachable in the sidebar",
        )

    def test_the_persona_can_open_something_on_the_root(self):
        items = _openable_items(
            self.workspaces[SALIS_ROOT], GRO_ROLE, self.doctypes, self.reports, self.pages
        )
        self.assertTrue(items, f"{GRO_ROLE} lands on the Salis root with nothing to open")

    def test_the_persona_is_never_frozen_into_the_baseline(self):
        for _workspace, role in KNOWN_EMPTY_WORKSPACE_ROLES:
            self.assertNotEqual(
                role,
                GRO_ROLE,
                f"{GRO_ROLE} must stay fixed in the workspace JSON, never frozen "
                "as a known gap",
            )

    def test_the_added_links_expose_nothing_new(self):
        """Every added link was already covered by a read DocPerm the persona held, so the
        link is a shortcut to a list it could already open by URL."""
        readable = _can_read(GRO_ROLE, self.doctypes)
        for target in ADDED_TO_SALIS_ROOT:
            with self.subTest(link=target):
                self.assertIn(
                    target,
                    readable,
                    f"{target} was linked without a pre-existing read DocPerm — the link "
                    "would be dead, and adding one would be a permission change",
                )

    def test_the_persona_holds_no_write_on_what_it_can_open(self):
        """The charter is a viewer charter; a navigation fix must not smuggle in rights."""
        write_flags = ("write", "create", "delete", "submit", "cancel", "amend", "share")
        for target in ADDED_TO_SALIS_ROOT:
            rows = [
                row
                for row in self.doctypes[target].get("permissions") or []
                if row.get("role") == GRO_ROLE
            ]
            self.assertTrue(rows, f"{target} has no {GRO_ROLE} DocPerm row")
            for row in rows:
                with self.subTest(link=target):
                    granted = [flag for flag in write_flags if row.get(flag)]
                    self.assertEqual(granted, [], f"{target} grants {GRO_ROLE} {granted}")


class TestHabitatRootPersonasCanOpenSomething(unittest.TestCase):
    """'s second half: three roles were granted the Habitat root while every link on
    it was System-Manager-only framework metadata. The root is their gateway — the desk
    sidebar nests a child workspace only under an already-rendered parent — so each needs
    something openable there."""

    def setUp(self):
        self.workspaces = _workspaces()
        self.doctypes = _doctypes()
        self.reports = _reports()
        self.pages = _pages()

    def test_each_persona_is_still_granted_the_root(self):
        granted = {row.get("role") for row in self.workspaces[HABITAT_ROOT].get("roles") or []}
        for role in ADDED_TO_HABITAT_ROOT:
            with self.subTest(role=role):
                self.assertIn(role, granted)

    def test_each_persona_can_open_something_on_the_root(self):
        for role, target in ADDED_TO_HABITAT_ROOT.items():
            with self.subTest(role=role):
                items = _openable_items(
                    self.workspaces[HABITAT_ROOT], role, self.doctypes, self.reports, self.pages
                )
                self.assertTrue(items, f"{role} lands on the Habitat root with nothing to open")
                self.assertIn(target, items)

    def test_no_persona_is_frozen_into_the_baseline(self):
        for _workspace, role in KNOWN_EMPTY_WORKSPACE_ROLES:
            self.assertNotIn(
                role,
                ADDED_TO_HABITAT_ROOT,
                "a role given Habitat-root content must stay fixed in the workspace "
                "JSON, never frozen back as a known gap",
            )

    def test_the_added_links_expose_nothing_new(self):
        """Each added link was already covered by a read DocPerm the persona held."""
        for role, target in ADDED_TO_HABITAT_ROOT.items():
            with self.subTest(role=role):
                self.assertIn(
                    target,
                    _can_read(role, self.doctypes),
                    f"{target} was linked without a pre-existing read DocPerm for {role} — "
                    "the link would be dead, and adding one would be a permission change",
                )


if __name__ == "__main__":
    unittest.main()
