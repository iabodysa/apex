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

import ast
import glob
import json
import os
import unittest

from apex.apex_core.utils import notification_role_guard as guard
from apex.tests.shipped_doctypes import shipped_doctypes
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


_PY_GLOB = os.path.join(_APP, "**", "*.py")

# The one helper that resolves an audience BY ROLE and can attach a document link
# (apex/habitat/tasks/common.py, re-exported from apex.habitat.tasks). Matched on the
# bare attribute name so both the direct call and a module-qualified one are seen.
ROLE_ALERT_HELPERS = frozenset({"_notify_role_system"})

# Frozen baselines, exact equality like the sibling guards: a NEW entry fails the build,
# a REPAIRED one fails until pruned. All three are empty, and that emptiness is the claim.
KNOWN_UNREADABLE_ROLE_ALERTS: dict[tuple[str, str, str], str] = {}
KNOWN_ROLE_ALERTS_WITHOUT_A_DOCPERM: dict[tuple[str, str], str] = {}
KNOWN_DYNAMIC_ROLE_ALERTS: dict[tuple[str, int], str] = {}


class RoleAlert(tuple):
    """One ``_notify_role_system`` call site, as read off disk.

    ``role``/``document_type`` are the literal values, or None when the argument is
    absent or is not a literal. ``links`` is True only when BOTH document_type and
    document_name were passed, which is the exact condition under which
    ``apex_core.utils.system_notify.notify_user_system`` writes the link onto the row.
    ``dynamic`` names the arguments that were present but could not be read literally.
    """

    __slots__ = ()

    def __new__(cls, module, lineno, role, document_type, links, dynamic):
        return super().__new__(cls, (module, lineno, role, document_type, links, dynamic))

    module = property(lambda self: self[0])
    lineno = property(lambda self: self[1])
    role = property(lambda self: self[2])
    document_type = property(lambda self: self[3])
    links = property(lambda self: self[4])
    dynamic = property(lambda self: self[5])


def _string_literal(node):
    """The node's value when it is a plain string literal, else None."""
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def role_alert_calls(tree, module):
    """Every role-alert call site in one parsed module. Pure, so the proofs below can
    drive it with synthetic source instead of planting a call in a shipped file.

    Only ``role`` is read positionally: the helper declares document_type/document_name
    keyword-only (apex/habitat/tasks/common.py), so they can never arrive as args.
    """
    found = []
    for call in ast.walk(tree):
        if not isinstance(call, ast.Call):
            continue
        func = call.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if name not in ROLE_ALERT_HELPERS:
            continue
        passed = {"role": call.args[0] if call.args else None}
        for keyword in call.keywords:
            if keyword.arg in ("role", "document_type", "document_name"):
                passed[keyword.arg] = keyword.value
        values = {key: _string_literal(arg) for key, arg in passed.items() if arg is not None}
        dynamic = frozenset(
            key for key in ("role", "document_type") if key in passed and values.get(key) is None
        )
        links = passed.get("document_type") is not None and passed.get("document_name") is not None
        found.append(
            RoleAlert(
                module,
                call.lineno,
                values.get("role"),
                values.get("document_type"),
                links,
                dynamic,
            )
        )
    return found


def shipped_role_alerts():
    """Every role-alert call site the app ships, outside its own test modules.

    Test modules are skipped deliberately: a guard grades what runs in production, and a
    test is free to construct a deliberately broken call as a fixture. The proofs below
    therefore build their inputs with ``ast.parse`` on a source string, never by planting
    a call in a file this scan would read back.
    """
    calls = []
    for path in sorted(glob.glob(_PY_GLOB, recursive=True)):
        if os.path.basename(path).startswith("test_"):
            continue
        with open(path, encoding="utf-8") as fh:
            source = fh.read()
        if not any(helper in source for helper in ROLE_ALERT_HELPERS):
            continue
        calls.extend(
            role_alert_calls(ast.parse(source), os.path.relpath(path, _APP).replace(os.sep, "/"))
        )
    return calls


def unreadable_role_alerts(calls, doctypes):
    """(module, role, document_type) for every LINKED alert whose role cannot open it.

    A document_type this app does not ship is skipped rather than graded — the same line
    ``notification_role_guard.unreachable_pairs`` draws, and pinned to empty below.
    """
    out = set()
    for call in calls:
        if not (call.links and call.role and call.document_type):
            continue
        if call.role in guard.ALWAYS_PERMITTED:
            continue
        shipped = doctypes.get(call.document_type)
        if shipped is None:
            continue
        allowed = guard.roles_that_can_open(shipped.get("permissions"), shipped.get("istable"))
        if call.role not in allowed:
            out.add((call.module, call.role, call.document_type))
    return sorted(out)


def role_alerts_without_a_docperm(calls, permitted_roles):
    """(module, role) for every alerted role holding no DocPerm anywhere in apex."""
    return sorted(
        {
            (call.module, call.role)
            for call in calls
            if call.role
            and call.role not in guard.ALWAYS_PERMITTED
            and call.role not in permitted_roles
        }
    )


class TestPythonRoleAlertsReachARoleThatCanRead(unittest.TestCase):
    """The same defect one layer further out, invisible to both guards above.

    The workspace guard reads workspace JSON and the sibling notification guard
    (apex/apex_core/utils/test_notification_role_guard.py) reads Notification JSON, so a
    scheduler job posting a role-targeted Notification Log from PYTHON is graded by
    neither. ``habitat.tasks.common._notify_role_system`` resolves its audience with
    ``frappe.utils.user.get_users_with_role`` -- a plain Role -> Has Role -> User walk
    with no has_permission on it -- then hands document_type/document_name straight onto
    the row, so delivery always succeeds and the bell link throws PermissionError on
    click with no signal anywhere. The readable surface is the call sites, parsed by ast.

    Two invariants, because two distinct shapes were found: a call site that LINKS a
    document must name a role holding a permlevel-0, non-if_owner read on it (predicate
    imported from notification_role_guard, never restated, so the JSON and Python halves
    cannot disagree); and any alerted role must hold a DocPerm somewhere in apex, linked
    or not, which is the property TestEveryWorkspaceRoleHoldsADocPerm already asserts for
    workspaces -- hence this module rather than a third guard.

    RESIDUAL GAP, STATED RATHER THAN HIDDEN: the scan keys on the helper by NAME, so an
    ``import ... as`` alias, or code calling get_users_with_role itself and writing a
    linked row per user, would dodge it -- in the second case the role is only
    recoverable by dataflow. Neither exists today: every other get_users_with_role site
    (safety_checklist, material_transfer, temporary_worker_engine, salis.api.masar)
    sends mail or an unlinked alert, and no caller aliases the helper.
    """

    @classmethod
    def setUpClass(cls):
        cls.calls = shipped_role_alerts()
        cls.doctypes = shipped_doctypes()
        cls.permitted = set(_docperm_rows())

    def test_the_scan_reaches_the_shipped_call_sites(self):
        """A parser that found nothing would make every assertion below vacuously green."""
        modules = {call.module for call in self.calls}
        self.assertIn(
            "habitat/tasks/safety.py",
            modules,
            "the AST scan found no role alert in habitat/tasks/safety.py — the scan "
            f"broke, or the helper was renamed away from {sorted(ROLE_ALERT_HELPERS)}",
        )
        self.assertGreaterEqual(len(self.calls), 4, "implausibly few role-alert call sites")

    def test_every_linked_alert_names_a_role_that_can_open_the_record(self):
        found = unreadable_role_alerts(self.calls, self.doctypes)
        self.assertEqual(
            found,
            sorted(KNOWN_UNREADABLE_ROLE_ALERTS),
            "a role-targeted alert links a document its own audience cannot open. "
            "get_users_with_role never consults has_permission, so delivery succeeds "
            "and the bell link throws PermissionError on click, silently. Either grant "
            "that role a permlevel-0, non-if_owner read on the document_type, repoint "
            "the call at a role that already holds one, or drop the "
            "document_type/document_name pair so the alert carries no link at all.",
        )

    def test_every_alerted_role_holds_a_docperm_somewhere(self):
        """The Operations Director shape: a role with no grant anywhere in the app."""
        found = role_alerts_without_a_docperm(self.calls, self.permitted)
        self.assertEqual(
            found,
            sorted(KNOWN_ROLE_ALERTS_WITHOUT_A_DOCPERM),
            "a scheduled job alerts a role that holds no DocPerm anywhere in apex, so "
            "its members are told about work they cannot open even without a link. "
            "Repoint the call at a role this app actually grants a surface to.",
        )

    def test_no_call_site_hides_its_role_or_document_behind_a_variable(self):
        """A non-literal role or document_type is UNGRADABLE, not innocent.

        Without this pin, moving a role name into a variable would silently exempt the
        call site from both invariants above and read as a clean build.
        """
        found = sorted({(call.module, call.lineno) for call in self.calls if call.dynamic})
        self.assertEqual(
            found,
            sorted(KNOWN_DYNAMIC_ROLE_ALERTS),
            "role-alert call site(s) compute their role or document_type at runtime, so "
            "this guard cannot grade them. Pass literals, or record why the site is "
            "exempt in KNOWN_DYNAMIC_ROLE_ALERTS.",
        )

    def test_every_linked_document_type_is_ours(self):
        """Pin the one exemption in ``unreadable_role_alerts`` to the empty set."""
        foreign = sorted(
            {
                call.document_type
                for call in self.calls
                if call.links and call.document_type and call.document_type not in self.doctypes
            }
        )
        self.assertEqual(
            foreign,
            [],
            "a role alert links a DocType this app does not ship, so the guard does not "
            "grade it — decide whether to judge another app's DocPerms",
        )

    def test_every_frozen_entry_carries_a_reason(self):
        for baseline in (
            KNOWN_UNREADABLE_ROLE_ALERTS,
            KNOWN_ROLE_ALERTS_WITHOUT_A_DOCPERM,
            KNOWN_DYNAMIC_ROLE_ALERTS,
        ):
            for key, why in baseline.items():
                with self.subTest(entry=key):
                    self.assertTrue(why and why.strip(), f"{key} is frozen with no reason")


class TestTheCallSiteDetectorFiresAndStaysSilent(unittest.TestCase):
    """Proof the call-site detector can fail, and does not fail on everything.

    Inputs are parsed from source strings: planting a broken call in a shipped file
    would be picked up by ``shipped_role_alerts`` and red the ratchet above.
    """

    FAKE_DT = "_A309 Alerted Record"
    DEAD_ROLE = "_A309 Role Without A Grant"
    LIVE_ROLE = "_A309 Role That Can Open"
    DOCTYPES = {FAKE_DT: {"name": FAKE_DT, "permissions": [{"role": LIVE_ROLE, "read": 1}]}}

    def _calls(self, source):
        return role_alert_calls(ast.parse(source), "synthetic.py")

    def test_the_detector_flags_a_planted_unreadable_alert(self):
        calls = self._calls(
            f'_notify_role_system("{self.DEAD_ROLE}", subject="s",'
            f' document_type="{self.FAKE_DT}", document_name=x)'
        )
        self.assertEqual(
            unreadable_role_alerts(calls, self.DOCTYPES),
            [("synthetic.py", self.DEAD_ROLE, self.FAKE_DT)],
        )

    def test_the_detector_stays_silent_for_a_role_that_can_open(self):
        """The proof above alone is satisfied by a detector that flags everything."""
        calls = self._calls(
            f'_notify_role_system("{self.LIVE_ROLE}", subject="s",'
            f' document_type="{self.FAKE_DT}", document_name=x)'
        )
        self.assertEqual(unreadable_role_alerts(calls, self.DOCTYPES), [])

    def test_a_document_type_without_a_document_name_does_not_link(self):
        """notify_user_system writes the link only when BOTH are supplied
        (apex/apex_core/utils/system_notify.py), so half a pair is not a broken link."""
        calls = self._calls(
            f'_notify_role_system("{self.DEAD_ROLE}", subject="s", document_type="{self.FAKE_DT}")'
        )
        self.assertFalse(calls[0].links)
        self.assertEqual(unreadable_role_alerts(calls, self.DOCTYPES), [])

    def test_an_unlinked_alert_still_fails_the_docperm_invariant(self):
        """The Operations Director shape: no link to break, no grant either."""
        calls = self._calls(f'_notify_role_system("{self.DEAD_ROLE}", subject="s", message=m)')
        self.assertEqual(
            role_alerts_without_a_docperm(calls, {self.LIVE_ROLE}),
            [("synthetic.py", self.DEAD_ROLE)],
        )
        self.assertEqual(
            role_alerts_without_a_docperm(calls, {self.LIVE_ROLE, self.DEAD_ROLE}), []
        )

    def test_a_role_passed_as_a_keyword_is_read(self):
        calls = self._calls(f'_notify_role_system(role="{self.DEAD_ROLE}", subject="s")')
        self.assertEqual(calls[0].role, self.DEAD_ROLE)

    def test_a_computed_role_is_reported_as_dynamic(self):
        calls = self._calls("_notify_role_system(chosen_role, subject='s')")
        self.assertEqual(calls[0].dynamic, frozenset({"role"}))
        self.assertIsNone(calls[0].role)

    def test_administrator_is_never_the_offender(self):
        calls = self._calls(
            f'_notify_role_system("Administrator", subject="s",'
            f' document_type="{self.FAKE_DT}", document_name=x)'
        )
        self.assertEqual(unreadable_role_alerts(calls, self.DOCTYPES), [])
        self.assertEqual(role_alerts_without_a_docperm(calls, set()), [])


class TestTheRepairedCallSitesStayRepaired(unittest.TestCase):
    """The two repaired defects, pinned by name so a revert is named, not just counted."""

    @classmethod
    def setUpClass(cls):
        cls.calls = [c for c in shipped_role_alerts() if c.module == "habitat/tasks/safety.py"]

    def test_the_safety_officer_alert_carries_no_building_link(self):
        """Building ships its whole Financials tab at permlevel 0, so the fix was to drop
        the link rather than widen a safety persona onto every building's cost model."""
        linked = [c for c in self.calls if c.role == "Safety Officer" and c.links]
        self.assertEqual(
            linked,
            [],
            "a Safety Officer alert links a document again; Safety Officer holds read on "
            f"the safety records only, and would need a grant for {linked}",
        )

    def test_no_safety_alert_names_the_operations_director(self):
        """The role holds no DocPerm anywhere in apex; three shipped Notifications were
        repointed off it earlier for the same reason."""
        self.assertNotIn(
            "Operations Director",
            {call.role for call in self.calls},
            "Operations Director holds no DocPerm anywhere in apex, so alerting it is "
            "the defect this guard exists to catch, not a fix",
        )
