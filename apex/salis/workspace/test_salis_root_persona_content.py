# Copyright (c) 2026, AFMCO and contributors
"""A-172 — a workspace grant plus a DocPerm still leaves a persona on an empty page.

A-162 gave ``Government Relations Officer`` read DocPerms so it would stop landing on a
blank ``Compliance and Rentals``. A-125 then granted it the ``Salis`` ROOT as well,
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
records it has no permission on. This guard therefore counts only the OPENABLE items --
DocType and Report links -- and requires each granted role to have at least one.

The fix A-172 shipped is on the root's own terms, not the persona's: the Master Data card
is documented as "Reference data: durable records you set up once", it listed the routing
masters, and it omitted ``Salis Vehicle`` and ``Salis Driver`` -- the two registries every
other Salis record links to, and the only Salis DocTypes whose reader set matches the
root's grant list exactly. Adding them fills the card for all seven granted roles.

A-178 then drained both ratchets this file carried. The ``Compliance and Rentals``
Compliance card held exactly one link, at the istable ``Salis Vehicle Compliance``, so the
whole card rendered for no non-Administrator; it now points at ``Salis Vehicle``, which
embeds those rows in its ``compliance_documents`` Table field and is readable by every one
of the six roles the workspace grants. The Habitat root's three stranded personas each
gained the operational record their own child workspace leads with — Cleaning Log, Safety
Round, SIM Custody Assignment — on the Operations card, which already collects the
module's daily operational records.

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

_APP = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
_WORKSPACE_GLOB = os.path.join(_APP, "*", "workspace", "*", "*.json")
_DOCTYPE_GLOB = os.path.join(_APP, "*", "doctype", "*", "*.json")
_REPORT_GLOB = os.path.join(_APP, "*", "report", "*", "*.json")

GRO_ROLE = "Government Relations Officer"
SALIS_ROOT = "Salis"

# Both short-circuit is_item_allowed or hold read on every core DocType, so their absence
# from a page is never the bug this guard hunts.
_ALWAYS_PERMITTED = {"System Manager", "Administrator"}

# The links A-172 added to the Salis root, each with the DocPerm that already let the
# persona open the same list by URL.
ADDED_TO_SALIS_ROOT = ("Salis Vehicle", "Salis Driver")

HABITAT_ROOT = "Habitat"
COMPLIANCE_WORKSPACE = "Compliance and Rentals"

# A-178 drained both ratchets below to empty. The Habitat root's Operations card gained
# one operational record per stranded persona, and the Compliance card was retargeted off
# the child table onto its embedding parent. Each entry left as it was fixed, which is what
# keeps the exact-equality assertions honest.
ADDED_TO_HABITAT_ROOT = {
    "Cleaning Supervisor": "Cleaning Log",
    "Safety Officer": "Safety Round",
    "SIM Operations User": "SIM Custody Assignment",
}

# The Compliance card's retarget. Salis Vehicle embeds the compliance rows in its
# `compliance_documents` Table field, and its reader set covers every role the workspace
# grants — so the card renders for all of them.
COMPLIANCE_CARD_TARGET = "Salis Vehicle"

KNOWN_EMPTY_WORKSPACE_ROLES = {
    # Frozen baseline of (workspace, role) -> reason. Exact equality: a NEW pair fails the
    # build and a CLOSED pair fails until it is pruned from here. Empty since A-178.
}

KNOWN_CHILD_TABLE_LINKS = {
    # A DocType link at an istable target is dead for everyone but Administrator, because
    # build_permissions never puts a child table into can_read. Not permissionable — the
    # link has to point at the embedding parent instead. Empty since A-178.
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


def _openable_items(workspace, role, doctypes, reports):
    """The DocType and Report links of one workspace that survive is_item_allowed."""
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
    return items


def _empty_pairs(workspaces, doctypes, reports):
    """{(workspace, role)} where a granted role can open nothing on the page.

    Pure over its inputs so the self-test below can drive it with planted data.
    """
    found = set()
    for name, workspace in workspaces.items():
        for row in workspace.get("roles") or []:
            role = row.get("role")
            if not role or role in _ALWAYS_PERMITTED:
                continue
            if not _openable_items(workspace, role, doctypes, reports):
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
    """The general invariant behind the A-172 regression."""

    def setUp(self):
        self.workspaces = _workspaces()
        self.doctypes = _doctypes()
        self.reports = _reports()

    def test_scan_is_non_vacuous(self):
        self.assertIn(SALIS_ROOT, self.workspaces, "workspace glob broke")
        self.assertTrue(self.doctypes, "doctype glob broke")
        self.assertTrue(self.reports, "report glob broke")

    def test_no_new_empty_workspace_role(self):
        found = _empty_pairs(self.workspaces, self.doctypes, self.reports)
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
        DETECTOR rather than the current file contents."""
        planted = dict(self.workspaces)
        page = dict(planted[SALIS_ROOT])
        page["roles"] = [*(page.get("roles") or []), {"role": "_A172 Planted Role"}]
        planted[SALIS_ROOT] = page
        found = _empty_pairs(planted, self.doctypes, self.reports)
        self.assertIn(
            (SALIS_ROOT, "_A172 Planted Role"),
            found,
            "the detector missed a role that can open nothing on the page",
        )

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
    """A-172's own outcome, asserted by name so it cannot be ratcheted away."""

    def setUp(self):
        self.workspaces = _workspaces()
        self.doctypes = _doctypes()
        self.reports = _reports()

    def test_the_persona_is_granted_the_root(self):
        granted = {row.get("role") for row in self.workspaces[SALIS_ROOT].get("roles") or []}
        self.assertIn(
            GRO_ROLE,
            granted,
            "the root grant is what makes Compliance and Rentals reachable in the sidebar",
        )

    def test_the_persona_can_open_something_on_the_root(self):
        items = _openable_items(
            self.workspaces[SALIS_ROOT], GRO_ROLE, self.doctypes, self.reports
        )
        self.assertTrue(items, f"{GRO_ROLE} lands on the Salis root with nothing to open")
        for target in ADDED_TO_SALIS_ROOT:
            with self.subTest(link=target):
                self.assertIn(target, items)

    def test_the_persona_is_never_frozen_into_the_baseline(self):
        for _workspace, role in KNOWN_EMPTY_WORKSPACE_ROLES:
            self.assertNotEqual(
                role,
                GRO_ROLE,
                "A-172 must stay fixed in the workspace JSON, never frozen as a known gap",
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


class TestComplianceCardRendersForItsGrantedRoles(unittest.TestCase):
    """A-178's first half: the Compliance card pointed at a child table, so it rendered
    for nobody. Asserted by name so the retarget cannot be silently reverted."""

    def setUp(self):
        self.workspaces = _workspaces()
        self.doctypes = _doctypes()
        self.reports = _reports()
        self.workspace = self.workspaces[COMPLIANCE_WORKSPACE]

    def _compliance_card_links(self):
        """The links between the `Compliance` Card Break and the next one."""
        out, inside = [], False
        for link in self.workspace.get("links") or []:
            if link.get("type") == "Card Break":
                if inside:
                    break
                inside = link.get("label") == "Compliance"
                continue
            if inside:
                out.append(link)
        return out

    def test_the_card_still_exists(self):
        self.assertTrue(
            self._compliance_card_links(), "the Compliance card lost all of its links"
        )

    def test_no_card_link_targets_a_child_table(self):
        for link in self._compliance_card_links():
            with self.subTest(link=link.get("link_to")):
                target = self.doctypes.get(link.get("link_to"), {})
                self.assertFalse(
                    target.get("istable"),
                    f"{link.get('link_to')} is istable; build_permissions never puts a "
                    "child table into can_read, so the link renders for nobody",
                )

    def test_the_card_targets_the_embedding_parent(self):
        targets = {link.get("link_to") for link in self._compliance_card_links()}
        self.assertIn(COMPLIANCE_CARD_TARGET, targets)

    def test_the_parent_actually_embeds_the_compliance_rows(self):
        """The retarget is only correct if the parent is where the records live."""
        fields = self.doctypes[COMPLIANCE_CARD_TARGET].get("fields") or []
        embedded = [
            f["fieldname"]
            for f in fields
            if f.get("fieldtype") == "Table" and f.get("options") == "Salis Vehicle Compliance"
        ]
        self.assertTrue(
            embedded,
            f"{COMPLIANCE_CARD_TARGET} has no Table field of Salis Vehicle Compliance, so "
            "it is not the surface that shows the compliance records",
        )

    def test_every_granted_role_can_open_the_card_target(self):
        """The goal: the card shows the records to the roles the workspace is gated to."""
        for row in self.workspace.get("roles") or []:
            role = row.get("role")
            if not role or role in _ALWAYS_PERMITTED:
                continue
            with self.subTest(role=role):
                self.assertIn(
                    COMPLIANCE_CARD_TARGET,
                    _can_read(role, self.doctypes),
                    f"{role} is granted {COMPLIANCE_WORKSPACE} but cannot read "
                    f"{COMPLIANCE_CARD_TARGET}, so the Compliance card is empty for it",
                )

    def test_the_retarget_exposes_nothing_new(self):
        """is_item_allowed filters every link per user, so the link is only a shortcut to
        a list the role could already open by URL — it must already hold the read row."""
        rows = [
            row
            for row in self.doctypes[COMPLIANCE_CARD_TARGET].get("permissions") or []
            if row.get("read") and not row.get("permlevel")
        ]
        self.assertTrue(rows, f"{COMPLIANCE_CARD_TARGET} ships no permlevel-0 read row")

    def test_the_read_only_register_stays_on_the_reports_card(self):
        """The card is an input screen ("open an item to create or edit records"); the
        read-only register belongs to the Reports card and must not be duplicated here."""
        card_targets = {link.get("link_to") for link in self._compliance_card_links()}
        self.assertNotIn("Vehicle Compliance Register", card_targets)
        all_reports = {
            link.get("link_to")
            for link in self.workspace.get("links") or []
            if link.get("link_type") == "Report"
        }
        self.assertIn("Vehicle Compliance Register", all_reports)


class TestHabitatRootPersonasCanOpenSomething(unittest.TestCase):
    """A-178's second half: three roles were granted the Habitat root while every link on
    it was System-Manager-only framework metadata. The root is their gateway — the desk
    sidebar nests a child workspace only under an already-rendered parent — so each needs
    something openable there."""

    def setUp(self):
        self.workspaces = _workspaces()
        self.doctypes = _doctypes()
        self.reports = _reports()

    def test_each_persona_is_still_granted_the_root(self):
        granted = {row.get("role") for row in self.workspaces[HABITAT_ROOT].get("roles") or []}
        for role in ADDED_TO_HABITAT_ROOT:
            with self.subTest(role=role):
                self.assertIn(role, granted)

    def test_each_persona_can_open_something_on_the_root(self):
        for role, target in ADDED_TO_HABITAT_ROOT.items():
            with self.subTest(role=role):
                items = _openable_items(
                    self.workspaces[HABITAT_ROOT], role, self.doctypes, self.reports
                )
                self.assertTrue(items, f"{role} lands on the Habitat root with nothing to open")
                self.assertIn(target, items)

    def test_no_persona_is_frozen_into_the_baseline(self):
        for _workspace, role in KNOWN_EMPTY_WORKSPACE_ROLES:
            self.assertNotIn(
                role,
                ADDED_TO_HABITAT_ROOT,
                "A-178 must stay fixed in the workspace JSON, never frozen as a known gap",
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
