# Copyright (c) 2026, AFMCO and contributors
"""a workspace grant plus a DocPerm still leaves a persona on an empty page.

The subject is the shipped Workspace RECORDS — apex/salis/workspace/salis/salis.json and
fleet/fleet.json — not the ``__init__.py`` beside this file. Granting a persona read DocPerms on a
child workspace is not enough on its own: the desk sidebar nests a child only under an
already-rendered parent, so the root has to be granted too, and a root that holds nothing the
persona can open is the third shape this guard exists to catch.

WHAT MOVED HERE AND WHY. This module used to reimplement ``Workspace.is_item_allowed``
(frappe/desk/desktop.py) and ``build_permissions`` (frappe/utils/user.py) by hand, parsing the
shipped JSON directly and unit-testing its own reimplementation with planted synthetic pages. Two
whitelisted endpoints already ask the live question with no reimplementation needed:

- ``get_workspace_sidebar_items()`` returns exactly the pages the session user's own sidebar
  would list — reachability, asked of the framework.
- ``get_desktop_page(json.dumps({"name": ...}))`` runs the real ``Workspace.build_workspace()``
  and returns the real, permission-filtered cards and shortcuts for the session user — content,
  asked of the framework.

Both are called below as real single-role test users, so the DocPerm resolution, module
allow-list and everything else ``is_item_allowed`` weighs is the framework's own, not a hand-rolled
copy that can drift from it. What is NOT replaced: whether a content block names a Card Break that
exists, and whether a DocType link points at a child table. Neither has a live counterpart — the
desk silently fails to render in both cases with no exception to catch — so those two stay as
direct checks on the shipped JSON, each already a real (non-pinned) rule rather than a value pin.

Lives beside the workspace package it fixes: ``apex/tests/`` is closed to new modules
(test_colocation_ratchet.py) and a cross-workspace invariant owns no single record dir.
"""

from __future__ import annotations

import glob
import json
import os
from pathlib import Path

import frappe
from frappe.desk.desktop import get_desktop_page, get_workspace_sidebar_items
from frappe.tests.utils import FrappeTestCase

import apex
from apex.tests._helpers import _user, as_user

_APP = str(Path(apex.__file__).resolve().parent)
_WORKSPACE_GLOB = os.path.join(_APP, "*", "workspace", "*", "*.json")

GRO_ROLE = "Government Relations Officer"
SALIS_ROOT = "Salis"
HABITAT_ROOT = "Habitat"

# Both short-circuit is_item_allowed (Administrator) or hold read on every core DocType
# through means this scan cannot usefully vary (System Manager), so their absence from a
# page is never the bug this guard hunts.
_ALWAYS_PERMITTED = {"System Manager", "Administrator"}

# Shortcut types get_shortcuts() lets through unconditionally (is_item_allowed returns True
# without asking anything), so they render on a page holding nothing else the persona may
# open. Excluding them keeps the guard measuring reachable WORK, not the always-present cards.
_NOT_OPENABLE_SHORTCUT_TYPES = {"Dashboard", "URL"}

ADDED_TO_SALIS_ROOT = ("Salis Vehicle", "Salis Driver")
ADDED_TO_HABITAT_ROOT = {
    "Cleaning Supervisor": "Cleaning Log",
    "Safety Officer": "Safety Round",
    "SIM Operations User": "SIM Custody Assignment",
}

# Frozen baseline of (workspace, role) -> reason. Exact equality: a NEW pair fails the
# build and a CLOSED pair fails until it is pruned from here. Empty since the fix.
KNOWN_EMPTY_WORKSPACE_ROLES: dict[tuple[str, str], str] = {}

# A DocType link at an istable target is dead for everyone but Administrator, because
# build_permissions never puts a child table into can_read. Not permissionable — the
# link has to point at the embedding parent instead. Empty since that change.
KNOWN_CHILD_TABLE_LINKS: dict[tuple[str, str], str] = {}


def _load_workspaces():
    """Every shipped is_standard Workspace, keyed by name."""
    out = {}
    for path in sorted(glob.glob(_WORKSPACE_GLOB)):
        with open(path, encoding="utf-8") as fh:
            try:
                data = json.load(fh)
            except json.JSONDecodeError:
                continue
        if isinstance(data, dict) and data.get("doctype") == "Workspace":
            out[data["name"]] = data
    return out


def _load_doctypes():
    """Every shipped is_standard DocType, keyed by name — used only by the child-table
    link check below, which has no live counterpart to ask instead."""
    pattern = os.path.join(_APP, "*", "doctype", "*", "*.json")
    out = {}
    for path in sorted(glob.glob(pattern)):
        with open(path, encoding="utf-8") as fh:
            try:
                data = json.load(fh)
            except json.JSONDecodeError:
                continue
        if isinstance(data, dict) and data.get("doctype") == "DocType":
            out[data["name"]] = data
    return out


def _shipped_role_grants(workspaces):
    """[(workspace, role)] for every non-always-permitted role any shipped Workspace
    grants, in file order."""
    pairs = []
    for name, workspace in workspaces.items():
        for row in workspace.get("roles") or []:
            role = row.get("role")
            if role and role not in _ALWAYS_PERMITTED:
                pairs.append((name, role))
    return pairs


def _reaches(workspace_name):
    """True when the session user's OWN sidebar lists this workspace — the root-grant
    half: a workspace with no roles row for this user never appears here at all."""
    sidebar = get_workspace_sidebar_items()
    return any(page.get("name") == workspace_name for page in sidebar.get("pages") or [])


def _openable_items(workspace_name):
    """(cards, shortcuts) the session user can actually open on the page, asked of
    get_desktop_page — the same call the desk page itself makes on load."""
    desktop = get_desktop_page(json.dumps({"name": workspace_name}))
    cards = desktop.get("cards", {}).get("items") or []
    shortcuts = [
        item
        for item in desktop.get("shortcuts", {}).get("items") or []
        if item.get("type") not in _NOT_OPENABLE_SHORTCUT_TYPES
    ]
    return cards, shortcuts


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


class TestNoGrantedRoleLandsOnAnEmptyPage(FrappeTestCase):
    """The general invariant behind the regression, asked of the live desk endpoints —
    one real, single-role test user per role, reused across every workspace it is
    granted on."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.workspaces = _load_workspaces()
        cls.doctypes = _load_doctypes()
        cls.pairs = _shipped_role_grants(cls.workspaces)
        cls.role_user = {}
        for _workspace, role in cls.pairs:
            if role not in cls.role_user:
                slug = role.lower().replace(" ", "_")
                cls.role_user[role] = _user(f"wsrole.{slug}@example.com", role)

    def test_scan_is_non_vacuous(self):
        self.assertIn(SALIS_ROOT, self.workspaces, "workspace glob broke")
        self.assertIn(HABITAT_ROOT, self.workspaces, "workspace glob broke")
        self.assertGreater(len(self.pairs), 10, "workspace/role grant scan found implausibly few")
        for name in {workspace for workspace, _role in self.pairs}:
            self.assertTrue(
                frappe.db.exists("Workspace", name), f"{name} is granted in JSON but not on site"
            )

    def test_every_granted_role_reaches_its_workspace_and_can_open_something(self):
        """Reachability from get_workspace_sidebar_items, content from
        get_desktop_page, both asked as the actual granted role — real DocPerm
        resolution, real module allow-list, no reimplementation to drift from either."""
        unreachable = set()
        empty = set()
        for workspace, role in self.pairs:
            with as_user(self.role_user[role]):
                if not _reaches(workspace):
                    unreachable.add((workspace, role))
                    continue
                cards, shortcuts = _openable_items(workspace)
            if not cards and not shortcuts:
                empty.add((workspace, role))
        self.assertEqual(
            unreachable,
            set(),
            "granted role(s) do not reach their own workspace root in the sidebar "
            f"(get_workspace_sidebar_items): {sorted(unreachable)}",
        )
        self.assertEqual(
            empty,
            set(KNOWN_EMPTY_WORKSPACE_ROLES),
            "granted role(s) reach a workspace with nothing openable on it "
            f"(get_desktop_page): {sorted(empty)}. Give the workspace a link the role "
            "can read, or freeze it above with a written reason.",
        )

    def test_every_frozen_pair_carries_a_reason(self):
        for pair, reason in KNOWN_EMPTY_WORKSPACE_ROLES.items():
            with self.subTest(pair=pair):
                self.assertTrue(reason and reason.strip(), f"{pair} has no documented reason")

    def test_every_card_block_names_a_card_break(self):
        """A card renders only when a Card Break label equals the block's card_name.
        No live counterpart: the desk silently omits the block, raising nothing."""
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

    def test_child_table_links_stay_frozen(self):
        """A link at an istable target is dead for every non-Administrator session —
        build_permissions never puts a child table in can_read, so is_item_allowed
        can never pass it, but get_desktop_page as Administrator would never show the
        gap either. Kept as a direct JSON check for that reason."""
        found = _child_table_links(self.workspaces, self.doctypes)
        self.assertEqual(
            found,
            set(KNOWN_CHILD_TABLE_LINKS),
            "workspace DocType links pointing at a child table changed. build_permissions "
            "skips istable, so such a link can never render — point it at the embedding "
            f"parent instead. On disk: {sorted(found)}",
        )

    def test_the_child_table_detector_flags_a_planted_link(self):
        """Proof the istable detector can still fail once its baseline is empty."""
        istable = next(n for n, d in self.doctypes.items() if d.get("istable"))
        planted = dict(self.workspaces)
        page = dict(planted[SALIS_ROOT])
        page["links"] = [
            *(page.get("links") or []),
            {"type": "Link", "link_type": "DocType", "link_to": istable},
        ]
        planted[SALIS_ROOT] = page
        found = _child_table_links(planted, self.doctypes)
        self.assertIn((SALIS_ROOT, istable), found, "the detector missed a planted child-table link")


class TestGovernmentRelationsOfficerReachesTheSalisRoot(FrappeTestCase):
    """The named regression: GRO was granted the Salis root while every link on it was
    filtered away, asked live so it cannot be ratcheted back without this failing."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.gro = _user("wsrole.gro_named.test@example.com", GRO_ROLE)

    def test_the_persona_is_granted_the_root_and_can_open_something(self):
        with as_user(self.gro):
            self.assertTrue(_reaches(SALIS_ROOT), f"{GRO_ROLE} does not reach the Salis root")
            cards, shortcuts = _openable_items(SALIS_ROOT)
        self.assertTrue(cards or shortcuts, f"{GRO_ROLE} lands on the Salis root with nothing to open")

    def test_the_persona_is_never_frozen_into_the_baseline(self):
        for _workspace, role in KNOWN_EMPTY_WORKSPACE_ROLES:
            self.assertNotEqual(
                role,
                GRO_ROLE,
                f"{GRO_ROLE} must stay fixed in the workspace JSON, never frozen as a known gap",
            )

    def test_the_added_links_expose_nothing_new(self):
        """Every added link was already covered by a read DocPerm the persona held —
        asked of frappe.has_permission, not the DocPerm JSON block."""
        with as_user(self.gro):
            for target in ADDED_TO_SALIS_ROOT:
                with self.subTest(link=target):
                    self.assertTrue(
                        frappe.has_permission(target, "read"),
                        f"{target} was linked without a pre-existing read grant — the "
                        "link would be dead, and adding one would be a permission change",
                    )

    def test_the_persona_holds_no_write_on_what_it_can_open(self):
        """The charter is a viewer charter; a navigation fix must not smuggle in rights."""
        with as_user(self.gro):
            for target in ADDED_TO_SALIS_ROOT:
                for action in ("write", "create", "delete", "submit", "cancel", "amend", "share"):
                    with self.subTest(link=target, action=action):
                        self.assertFalse(
                            frappe.has_permission(target, action),
                            f"{GRO_ROLE} must not be able to {action} {target}",
                        )


class TestHabitatRootPersonasCanOpenSomething(FrappeTestCase):
    """Three roles were granted the Habitat root while every link on it was
    System-Manager-only framework metadata; the root is their gateway, so each needs
    something openable there — asked live, per persona."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.role_user = {
            role: _user(f"wsrole.habitat_named.{role.lower().replace(' ', '_')}@example.com", role)
            for role in ADDED_TO_HABITAT_ROOT
        }

    def test_each_persona_reaches_the_root_and_can_open_something(self):
        for role, target in ADDED_TO_HABITAT_ROOT.items():
            with self.subTest(role=role):
                with as_user(self.role_user[role]):
                    self.assertTrue(_reaches(HABITAT_ROOT), f"{role} does not reach the Habitat root")
                    cards, shortcuts = _openable_items(HABITAT_ROOT)
                opened = {
                    link.get("link_to")
                    for card in cards
                    for link in card.get("links") or []
                } | {item.get("link_to") for item in shortcuts}
                self.assertTrue(cards or shortcuts, f"{role} lands on the Habitat root with nothing to open")
                self.assertIn(target, opened, f"{role} does not reach {target} on the Habitat root")

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
                with as_user(self.role_user[role]):
                    self.assertTrue(
                        frappe.has_permission(target, "read"),
                        f"{target} was linked without a pre-existing read grant for "
                        f"{role} — the link would be dead, and adding one would be a "
                        "permission change",
                    )


if __name__ == "__main__":
    import unittest

    unittest.main()
