# Copyright (c) 2026, AFMCO and contributors
"""A-162 — a workspace grant without a DocPerm ships a role that can navigate but not read.

``Government Relations Officer`` was named in the ``Compliance and Rentals`` workspace
``roles`` table and in two Salis Notifications, yet held ZERO DocPerm rows anywhere in the
app. Frappe let it into the sidebar and then emptied the page:
``Workspace.is_item_allowed`` (frappe/desk/desktop.py) keeps a DocType link only when the
name is in the session user's ``can_read``, and ``can_read`` is built purely from DocPerm
rows (frappe/utils/user.py ``build_permissions``). A role with no DocPerm therefore
resolves to an empty ``can_read``, every card link is filtered away, and the persona lands
on a blank workspace with no error to explain it.

This guard makes that shape unshippable: every role named in ANY workspace's ``roles``
grant must hold at least one DocPerm somewhere in apex. It is file-level and stdlib-only
on purpose — the invariant is a property of the shipped is_standard JSON, so it has to
fail on the change that WRITES the bad JSON rather than on a site that already migrated it.

Run standalone:  python3 -m unittest apex.tests.test_workspace_role_docperm_guard -v
"""

import glob
import json
import os
import unittest

from apex.tests.training_charter import charter_count, role_charters

_APP = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_WORKSPACE_GLOB = os.path.join(_APP, "*", "workspace", "*", "*.json")
_DOCTYPE_GLOB = os.path.join(_APP, "*", "doctype", "*", "*.json")

# The A-162 persona, asserted by name so it can never be ratcheted away.
GRO_ROLE = "Government Relations Officer"

# The two machine-readable claims this guard binds itself to inside the published
# charter. They are lookup keys INTO docs/training/README.md, never a local copy of
# it: each is asserted to still be present before the property it implies is checked,
# so a reworded charter reds here instead of silently unhooking the assertion.
NO_EDIT_PHRASE = "no record-edit rights"
DOCTYPE_COUNT_CLAIM = r"on (\w+) vehicle and driver compliance records"

# Every DocPerm flag that lets a holder change something. A viewer charter grants none of
# them; `read`/`report`/`export`/`print`/`email`/`select` are the read-side flags.
WRITE_FLAGS = (
    "write",
    "create",
    "delete",
    "submit",
    "cancel",
    "amend",
    "share",
    "import",
    "set_user_permissions",
)

KNOWN_NAVIGATION_ONLY_ROLES = {
    # Frozen baseline of pre-existing offenders, role -> why it is tolerated. A ratchet,
    # not an excuse list: the assertion is exact equality, so a NEW entry fails the build
    # and a FIXED entry fails until it is removed from here.
    "Administrator": (
        "superuser short-circuit: is_item_allowed returns True for Administrator before "
        "any can_read lookup (frappe/desk/desktop.py), so a DocPerm row would change "
        "nothing. Granted on the Habitat workspace."
    ),
}


def _docperm_rows():
    """role -> list of (doctype name, permission row) for every DocPerm shipped by apex."""
    rows = {}
    for path in sorted(glob.glob(_DOCTYPE_GLOB)):
        with open(path, encoding="utf-8") as fh:
            try:
                data = json.load(fh)
            except json.JSONDecodeError:
                continue
        if not isinstance(data, dict) or data.get("doctype") != "DocType":
            continue
        for row in data.get("permissions") or []:
            role = row.get("role")
            if role:
                rows.setdefault(role, []).append((data.get("name"), row))
    return rows


def _workspace_grants():
    """role -> sorted workspace titles that name it in their `roles` child table."""
    grants = {}
    for path in sorted(glob.glob(_WORKSPACE_GLOB)):
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        title = data.get("title") or data.get("name")
        for row in data.get("roles") or []:
            if row.get("role"):
                grants.setdefault(row["role"], set()).add(title)
    return {role: sorted(titles) for role, titles in grants.items()}


def _navigation_only_roles(grants, permitted_roles):
    """Roles a workspace grants that hold no DocPerm at all — pure, so it can be driven
    with synthetic input by the self-test below."""
    return {role for role in grants if role not in permitted_roles}


class TestEveryWorkspaceRoleHoldsADocPerm(unittest.TestCase):
    """The general invariant behind the A-162 regression."""

    def test_no_workspace_grants_a_navigation_only_role(self):
        grants = _workspace_grants()
        self.assertTrue(grants, "workspace scan found no role grants — the parser broke")
        found = _navigation_only_roles(grants, _docperm_rows())
        self.assertEqual(
            found,
            set(KNOWN_NAVIGATION_ONLY_ROLES),
            "workspace-granted roles holding no DocPerm changed. A NEW name means that "
            "persona reaches the sidebar and then sees an empty page — give it read "
            "DocPerms or drop the grant. A MISSING name means a gap was closed and the "
            "frozen baseline must shrink. Grants on disk: "
            f"{ {role: grants[role] for role in found ^ set(KNOWN_NAVIGATION_ONLY_ROLES)} }",
        )

    def test_the_detector_flags_a_planted_grant(self):
        """Proof the guard can fail: a role granted on a workspace but absent from every
        DocPerm must be reported."""
        grants = dict(_workspace_grants())
        grants["_A162 Planted Role"] = ["Compliance and Rentals"]
        found = _navigation_only_roles(grants, _docperm_rows())
        self.assertIn(
            "_A162 Planted Role",
            found,
            "the detector missed a role with zero DocPerms — the guard proves nothing",
        )

    def test_baseline_entries_carry_a_written_reason(self):
        for role, reason in KNOWN_NAVIGATION_ONLY_ROLES.items():
            with self.subTest(role=role):
                self.assertTrue(
                    reason and reason.strip(),
                    f"baseline entry '{role}' has no documented reason",
                )


class TestGovernmentRelationsOfficerCharter(unittest.TestCase):
    """The A-162 persona itself: a read-only Salis compliance viewer.

    The charter is READ from ``docs/training/README.md`` rather than restated here, so the
    page and the DocPerm JSON cannot drift in either direction: reword the charter and the
    phrase assertions fail, re-grant the JSON and the property assertions fail.
    """

    def test_the_charter_row_still_states_the_viewer_rule(self):
        """Doc side of the loop: the claim this guard enforces must still be published."""
        charter = role_charters().get(GRO_ROLE)
        self.assertIsNotNone(
            charter, f"{GRO_ROLE} has no Roles at a glance row in docs/training/README.md"
        )
        self.assertIn(
            NO_EDIT_PHRASE,
            charter,
            f"the published {GRO_ROLE} charter no longer says '{NO_EDIT_PHRASE}', which is "
            "the rule test_every_row_is_read_only enforces. Restore the wording or retire "
            f"the assertion — do not leave the two out of step. Charter now: {charter!r}",
        )

    def test_the_charter_doctype_count_matches_the_docperms(self):
        """The charter states how many records the persona reads; the JSON must agree."""
        documented = charter_count(GRO_ROLE, DOCTYPE_COUNT_CLAIM)
        held = sorted({doctype for doctype, _row in _docperm_rows().get(GRO_ROLE, [])})
        self.assertEqual(
            len(held),
            documented,
            f"docs/training/README.md says {GRO_ROLE} reads {documented} vehicle and driver "
            f"compliance records, but it holds DocPerms on {len(held)}: {held}. Update "
            "whichever side is wrong; they are one claim, not two.",
        )

    def test_the_persona_is_never_allowlisted(self):
        self.assertNotIn(
            GRO_ROLE,
            KNOWN_NAVIGATION_ONLY_ROLES,
            "A-162 must stay fixed in the DocType JSON, never frozen into the baseline",
        )

    def test_the_role_holds_read_docperms(self):
        self.assertIn(
            GRO_ROLE,
            _docperm_rows(),
            f"{GRO_ROLE} holds no DocPerm — it is a navigation-only role again",
        )

    def test_every_row_is_read_only(self):
        charter = role_charters().get(GRO_ROLE) or ""
        self.assertIn(
            NO_EDIT_PHRASE,
            charter,
            "the read-only rule below is only enforceable while the published charter "
            "still states it; it does not, so this assertion has lost its source",
        )
        for doctype, row in _docperm_rows().get(GRO_ROLE, []):
            with self.subTest(doctype=doctype):
                self.assertTrue(row.get("read"), f"{GRO_ROLE} row on {doctype} grants no read")
                granted = [flag for flag in WRITE_FLAGS if row.get(flag)]
                self.assertEqual(
                    granted,
                    [],
                    f"{GRO_ROLE} is a viewer charter with no record-edit rights, but its "
                    f"{doctype} row grants {granted}",
                )

    def test_the_role_reads_what_its_notifications_watch(self):
        """A notification recipient that cannot open the record it was alerted about is
        the same broken shape A-162 fixed, one layer down."""
        watched = set()
        for path in sorted(glob.glob(os.path.join(_APP, "*", "notification", "*", "*.json"))):
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            roles = {row.get("receiver_by_role") for row in data.get("recipients") or []}
            if GRO_ROLE in roles and data.get("document_type"):
                watched.add(data["document_type"])
        readable = {doctype for doctype, _row in _docperm_rows().get(GRO_ROLE, [])}
        self.assertTrue(watched, f"no shipped Notification names {GRO_ROLE} — scan broke")
        self.assertEqual(
            watched - readable,
            set(),
            f"{GRO_ROLE} is emailed about {sorted(watched - readable)} but holds no read "
            "DocPerm on it, so the alert links to a page it cannot open",
        )
