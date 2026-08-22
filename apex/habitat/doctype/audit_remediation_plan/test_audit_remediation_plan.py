# Copyright (c) 2026, AFMCO and contributors
from __future__ import annotations
import frappe
from frappe.tests.utils import FrappeTestCase
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import apex
from apex.habitat import permissions as P
from apex.tests.factories import make_scoped_supervisor
from unittest import TestCase
from unittest.mock import MagicMock
from apex.habitat.doctype.audit_remediation_plan import audit_remediation_plan



class TestClientAuditRemediationPlan(FrappeTestCase):

    def test_create_valid_plan(self):
        doc = frappe.get_doc({
            "doctype": "Audit Remediation Plan",
            "naming_series": "CARP-.YYYY.-.####",
            "client_project": "PROJ-QA",
            "audit_received_date": "2026-05-01",
            "remediation_deadline": "2026-07-01",
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertIsNotNone(doc.name)
        frappe.delete_doc("Audit Remediation Plan", doc.name, force=True, ignore_permissions=True)

    def test_missing_project_raises(self):
        doc = frappe.get_doc({
            "doctype": "Audit Remediation Plan",
            "naming_series": "CARP-.YYYY.-.####",
            "audit_received_date": "2026-05-01",
            "remediation_deadline": "2026-07-01",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_missing_deadline_raises(self):
        doc = frappe.get_doc({
            "doctype": "Audit Remediation Plan",
            "naming_series": "CARP-.YYYY.-.####",
            "client_project": "PROJ-QA",
            "audit_received_date": "2026-05-01",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

test_ignore = ['Additional Salary', 'Asset', 'Asset Movement', 'Company', 'Cost Center', 'Currency', 'Employee', 'Item', 'Payment Entry', 'Project', 'Purchase Invoice', 'Role', 'Salary Component', 'Supplier', 'User']


# --- merged from test_audit_remediation_plan_building_scope.py ---
DOCTYPE = "Audit Remediation Plan"
CHILD_DOCTYPE = "Audit Remediation Building Scope"
CHILD_FIELD = "buildings_in_scope"
QUERY_FN = "apex.habitat.permissions.building_scope_query"
HANDLER = "apex.habitat.permissions.building_scoped_has_permission"
BLD_A = "ARP-BLD-A"
BLD_B = "ARP-BLD-B"
def _h(n=12):
    return frappe.generate_hash(length=n).upper()
def _plan(*buildings):
    """A doc-shaped stand-in whose child scope names ``buildings``."""
    return SimpleNamespace(
        doctype=DOCTYPE,
        **{CHILD_FIELD: [SimpleNamespace(building=b) for b in buildings]},
    )
def _scoped_to(buildings):
    return (
        patch.object(P, "_building_is_unscoped", return_value=False),
        patch.object(P, "_allowed_buildings", return_value=list(buildings)),
    )
class TestAuditRemediationPlanScopeWiring(unittest.TestCase):
    """Siteless: the two hook entries, the child-table premise, and the verdicts."""

    APEX = Path(apex.__file__).parent

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from apex import hooks

        cls.hooks = hooks
        cls.json = {}
        for slug in ("audit_remediation_plan", "audit_remediation_building_scope"):
            path = cls.APEX / "habitat" / "doctype" / slug / (slug + ".json")
            data = json.loads(path.read_text())
            cls.json[data["name"]] = data

    def test_the_list_view_is_wired_to_the_child_scope_fragment(self):
        self.assertEqual(
            self.hooks.permission_query_conditions.get(DOCTYPE),
            QUERY_FN,
            "the plan list has no building scope",
        )

    def test_the_form_and_rest_paths_are_wired_to_the_dedicated_handler(self):
        self.assertEqual(
            self.hooks.has_permission.get(DOCTYPE),
            HANDLER,
            "an out-of-estate plan is still openable",
        )

    def test_both_wired_targets_resolve_to_a_callable(self):
        for dotted in (QUERY_FN, HANDLER):
            with self.subTest(dotted=dotted):
                self.assertTrue(callable(getattr(P, dotted.rsplit(".", 1)[1])))

    def test_the_plan_really_has_no_building_column_of_its_own(self):
        """The premise of the card. If a `building` field is ever added, the shared
        column fragment becomes the right answer and this says so."""
        fieldnames = {f.get("fieldname") for f in self.json[DOCTYPE]["fields"]}
        self.assertNotIn("building", fieldnames)
        self.assertNotIn(DOCTYPE, P.BUILDING_FETCH_ANCHOR)

    def test_the_scope_table_the_subquery_reads_is_the_one_the_plan_declares(self):
        """A rename on either side would leave the subquery matching nothing --
        silently blacking out every scoped user rather than leaking, but still wrong.

        The fieldtype is asserted as a SET, not a value. ``_render_child`` selects on
        ``parent``, ``parenttype`` and ``building`` in the child table, and both table
        fieldtypes write those three columns identically — so which of the two the form
        uses is a presentation choice the subquery cannot see. What it can see is a
        field that stores no child rows at all, which is what this excludes.
        """
        table = next(
            f
            for f in self.json[DOCTYPE]["fields"]
            if f.get("fieldname") == CHILD_FIELD
        )
        self.assertIn(table.get("fieldtype"), {"Table", "Table MultiSelect"})
        self.assertEqual(table.get("options"), CHILD_DOCTYPE)
        child = self.json[CHILD_DOCTYPE]
        self.assertEqual(child.get("istable"), 1)
        building = next(
            f for f in child["fields"] if f.get("fieldname") == "building"
        )
        self.assertEqual(building.get("options"), "Building")
        self.assertEqual(building.get("reqd"), 1)

    def test_the_handler_defers_in_estate_and_denies_out_of_estate(self):
        """Paired both ways: a handler that denied everything would pass half of this."""
        outer, inner = _scoped_to([BLD_A])
        with outer, inner:
            self.assertIsNone(
                P.building_scoped_has_permission(_plan(BLD_A), "read", user="sup"),
                "a supervisor was denied a plan naming their own building",
            )
            self.assertIs(
                P.building_scoped_has_permission(_plan(BLD_B), "read", user="sup"),
                False,
                "a plan naming only another estate was readable",
            )

    def test_a_plan_naming_several_buildings_is_visible_if_any_one_is_mine(self):
        """The set semantics the subquery has: a shared plan reaches every estate on it."""
        outer, inner = _scoped_to([BLD_A])
        with outer, inner:
            self.assertIsNone(
                P.building_scoped_has_permission(
                    _plan(BLD_B, BLD_A), "read", user="sup"
                )
            )

    def test_a_plan_naming_no_building_at_all_fails_closed(self):
        outer, inner = _scoped_to([BLD_A])
        with outer, inner:
            self.assertIs(
                P.building_scoped_has_permission(_plan(), "read", user="sup"),
                False,
            )
            self.assertIs(
                P.building_scoped_has_permission(
                    SimpleNamespace(doctype=DOCTYPE), "read", user="sup"
                ),
                False,
                "a plan with no scope table at all must be denied, not deferred",
            )

    def test_every_action_is_denied_out_of_estate_not_only_read(self):
        outer, inner = _scoped_to([BLD_A])
        with outer, inner:
            for ptype in ("read", "write", "create", "submit", "cancel", "delete"):
                with self.subTest(ptype=ptype):
                    self.assertIs(
                        P.building_scoped_has_permission(
                            _plan(BLD_B), ptype, user="sup"
                        ),
                        False,
                    )

    def test_oversight_defers_and_a_permissionless_scoped_user_is_denied(self):
        with patch.object(P, "_building_is_unscoped", return_value=True):
            self.assertIsNone(
                P.building_scoped_has_permission(_plan(BLD_B), "read", user="mgr")
            )
        outer, inner = _scoped_to([])
        with outer, inner:
            self.assertIs(
                P.building_scoped_has_permission(_plan(BLD_A), "read", user="sup"),
                False,
            )

    def test_the_fragment_renders_the_two_edge_cases_the_siblings_render(self):
        with patch.object(P, "_building_is_unscoped", return_value=True):
            self.assertEqual(P.building_scope_query(doctype=DOCTYPE, user="mgr"), "")
        outer, inner = _scoped_to([])
        with outer, inner:
            self.assertEqual(P.building_scope_query(doctype=DOCTYPE, user="sup"), "1=0")

    def test_the_fragment_subqueries_the_child_table_and_escapes_its_values(self):
        """The injection shape this must never take: an apostrophe in a building name
        has to arrive escaped, not spliced."""
        outer, inner = _scoped_to(["O'Hare Camp"])
        with outer, inner, patch.object(
            frappe, "db", SimpleNamespace(escape=lambda v: "'{0}'".format(v.replace("'", "\\'")))
        ):
            fragment = P.building_scope_query(doctype=DOCTYPE, user="sup")
        self.assertIn("`tabAudit Remediation Building Scope`", fragment)
        self.assertIn("select `parent`", fragment)
        self.assertIn("`parenttype` = 'Audit Remediation Plan'", fragment)
        self.assertIn("O\\'Hare Camp", fragment)
class TestAuditRemediationPlanScopeRuntime(FrappeTestCase):
    """Needs a bench site: real buildings, real child rows, a real User Permission."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.b1 = cls._building()
        cls.b2 = cls._building()
        cls.scoped = make_scoped_supervisor(cls._user, cls.b1, cls.addClassCleanup)
        # Same role, NO Building User Permission -- the user frappe's native match
        # leaves completely unrestricted.
        cls.unpermitted = cls._user("Resident Supervisor")
        cls.oversight = cls._user("Accommodation Manager")

    @classmethod
    def _building(cls):
        doc = frappe.get_doc({"doctype": "Building", "building_name": "ARP-" + _h()})
        doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        cls.addClassCleanup(
            frappe.delete_doc, "Building", doc.name, force=True, ignore_permissions=True
        )
        return doc.name

    @classmethod
    def _user(cls, role):
        email = "arp-{0}@example.com".format(_h()).lower()
        frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": "Scope",
                "send_welcome_email": 0,
                "roles": [{"role": role}],
            }
        ).insert(ignore_permissions=True)
        cls.addClassCleanup(
            frappe.delete_doc, "User", email, force=True, ignore_permissions=True
        )
        return email

    def _payload(self, *buildings):
        return {
            "doctype": DOCTYPE,
            "naming_series": "CARP-.YYYY.-.####",
            "client_project": "ARP-SCOPE-PROBE",
            "audit_received_date": frappe.utils.today(),
            "remediation_deadline": frappe.utils.today(),
            CHILD_FIELD: [{"building": b} for b in buildings],
        }

    def _plan(self, *buildings):
        doc = frappe.get_doc(self._payload(*buildings))
        doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        return doc.name

    def _pair(self):
        return self._plan(self.b1), self._plan(self.b2)

    def _rows_the_fragment_returns(self, user):
        """The names the desk list would return for ``user``.

        The fragment is exactly what `permission_query_conditions` AND-s into
        `DatabaseQuery`'s WHERE clause, built from `frappe.db.escape`d values, so
        running it verbatim is the same read the list view performs.
        """
        fragment = P.building_scope_query(doctype=DOCTYPE, user=user)
        if fragment == "1=0":
            return set()
        where = " where {0}".format(fragment) if fragment else ""
        return set(
            frappe.db.sql_list("select name from `tabAudit Remediation Plan`" + where)
        )

    def test_the_scoped_list_keeps_a_plan_naming_this_estate_and_drops_the_other(self):
        mine, theirs = self._pair()
        names = self._rows_the_fragment_returns(self.scoped)
        self.assertIn(mine, names, "the supervisor lost a plan naming their building")
        self.assertNotIn(theirs, names, "a plan naming only another estate leaked")

    def test_a_plan_naming_both_estates_reaches_the_scoped_supervisor(self):
        shared = self._plan(self.b1, self.b2)
        self.assertIn(shared, self._rows_the_fragment_returns(self.scoped))

    def test_a_plan_naming_no_building_is_hidden_from_scope_and_kept_by_oversight(self):
        """Fail closed, and prove it is the SCOPE hiding it rather than the row missing."""
        empty = self._plan()
        self.assertNotIn(empty, self._rows_the_fragment_returns(self.scoped))
        self.assertIn(empty, self._rows_the_fragment_returns(self.oversight))

    def test_oversight_sees_both_estates(self):
        """The control that stops a deny-everything fragment from passing."""
        mine, theirs = self._pair()
        names = self._rows_the_fragment_returns(self.oversight)
        self.assertIn(mine, names)
        self.assertIn(theirs, names)

    def test_a_supervisor_with_no_building_permission_sees_nothing(self):
        mine, theirs = self._pair()
        self.assertEqual(P.building_scope_query(doctype=DOCTYPE, user=self.unpermitted), "1=0")
        names = self._rows_the_fragment_returns(self.unpermitted)
        self.assertNotIn(mine, names)
        self.assertNotIn(theirs, names)

    def test_the_fragment_names_only_this_estate(self):
        fragment = P.building_scope_query(doctype=DOCTYPE, user=self.scoped)
        self.assertIn(self.b1, fragment)
        self.assertNotIn(self.b2, fragment)
        self.assertEqual(P.building_scope_query(doctype=DOCTYPE, user=self.oversight), "")

    def test_the_controller_hook_opens_this_estate_and_denies_the_other(self):
        """Isolates the hook from frappe's native check, which cannot see a child
        table at all and so would deny neither."""
        mine, theirs = self._pair()
        self.assertIsNone(
            P.building_scoped_has_permission(
                frappe.get_doc(DOCTYPE, mine), "read", user=self.scoped
            )
        )
        self.assertIs(
            P.building_scoped_has_permission(
                frappe.get_doc(DOCTYPE, theirs), "read", user=self.scoped
            ),
            False,
        )

    def test_the_scope_table_is_already_populated_at_the_create_check(self):
        """Why this DocType owes no BUILDING_FETCH_ANCHOR entry, checked rather than
        assumed: an unsaved doc built from a payload already carries its child rows,
        so the create verdict is decided on the real scope both ways."""
        for building, expected in ((self.b1, None), (self.b2, False)):
            with self.subTest(building=building):
                draft = frappe.get_doc(self._payload(building))
                self.assertEqual(
                    [row.building for row in draft.get(CHILD_FIELD)], [building]
                )
                self.assertIs(
                    P.building_scoped_has_permission(
                        draft, "create", user=self.scoped
                    ),
                    expected,
                )
if __name__ == "__main__":
    unittest.main(verbosity=2)


# --- merged from test_audit_remediation_state_contract.py ---
def _raising_frappe() -> MagicMock:
    fake = MagicMock()

    def throw(message, exc=None, **_kwargs):
        raise (exc or frappe.ValidationError)(message)

    fake.throw.side_effect = throw
    return fake
def _call(endpoint, *args, **kwargs):
    return getattr(endpoint, "__wrapped__", endpoint)(*args, **kwargs)
def _item(
    name: str, status: str, evidence: str | None = None, completion: str | None = None
):
    return frappe._dict(
        name=name,
        finding_description=f"Finding {name}",
        remediation_action=f"Action {name}",
        owner_role="Accommodation Manager",
        owner_user="owner@example.com",
        due_date="2026-08-20",
        status=status,
        completion_date=completion,
        evidence_attached=evidence,
    )
class TestAuditRemediationRollup(TestCase):
    def test_rollup_precedence_is_deterministic(self):
        cases = (
            (
                ["Verified by Client", "Verified by Client"],
                "2026-08-01",
                "Closed by Client",
            ),
            (["Open", "In Progress"], "2026-08-01", "Overdue"),
            (
                ["Evidence Submitted", "Verified by Client"],
                "2026-08-20",
                "Evidence Submitted",
            ),
            (["Rejected by Client", "Open"], "2026-08-20", "In Progress"),
            (["Open", "Open"], "2026-08-20", "Open"),
        )
        for statuses, deadline, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(
                    audit_remediation_plan.derive_overall_status(
                        [
                            _item(str(index), status)
                            for index, status in enumerate(statuses)
                        ],
                        deadline,
                        "2026-08-14",
                    ),
                    expected,
                )

    def test_allowed_item_transitions_are_narrow_and_verified_is_terminal(self):
        self.assertEqual(
            audit_remediation_plan.ALLOWED_ITEM_TRANSITIONS,
            {
                "Open": ("In Progress",),
                "In Progress": ("Evidence Submitted",),
                "Evidence Submitted": ("Verified by Client", "Rejected by Client"),
                "Rejected by Client": ("In Progress",),
                "Verified by Client": (),
            },
        )
class TestAuditRemediationActions(TestCase):
    def test_transition_checks_write_permission_before_mutation(self):
        row = _item("ITEM-1", "Open")
        plan = MagicMock(docstatus=1, overall_status="Open")
        plan.name = "ARP-1"
        plan.remediation_deadline = "2026-08-30"
        plan.remediation_items = [row]
        plan.flags = frappe._dict()
        plan.check_permission.side_effect = frappe.PermissionError("denied")
        fake = _raising_frappe()
        fake.get_doc.return_value = plan

        with patch.object(audit_remediation_plan, "frappe", fake):
            with self.assertRaises(frappe.PermissionError):
                _call(
                    audit_remediation_plan.transition_item,
                    "ARP-1",
                    "ITEM-1",
                    "In Progress",
                )

        self.assertEqual(row.status, "Open")
        plan.save.assert_not_called()

    def test_evidence_submission_requires_evidence_and_stamps_completion(self):
        row = _item("ITEM-1", "In Progress")
        plan = MagicMock(docstatus=1, overall_status="In Progress")
        plan.name = "ARP-1"
        plan.remediation_deadline = "2026-08-30"
        plan.remediation_items = [row]
        plan.flags = frappe._dict()
        fake = _raising_frappe()
        fake.get_doc.return_value = plan

        with (
            patch.object(audit_remediation_plan, "frappe", fake),
            patch.object(
                audit_remediation_plan, "_", side_effect=lambda message: message
            ),
            patch.object(audit_remediation_plan, "today", return_value="2026-08-14"),
        ):
            with self.assertRaises(frappe.ValidationError):
                _call(
                    audit_remediation_plan.transition_item,
                    "ARP-1",
                    "ITEM-1",
                    "Evidence Submitted",
                )
            result = _call(
                audit_remediation_plan.transition_item,
                "ARP-1",
                "ITEM-1",
                "Evidence Submitted",
                "/private/files/proof.pdf",
            )

        self.assertEqual(row.status, "Evidence Submitted")
        self.assertEqual(row.completion_date, "2026-08-14")
        self.assertEqual(row.evidence_attached, "/private/files/proof.pdf")
        self.assertEqual(plan.overall_status, "Evidence Submitted")
        plan.save.assert_called_once()
        self.assertEqual(result["item_status"], "Evidence Submitted")

    def test_rejected_item_can_restart_but_verified_item_cannot(self):
        row = _item("ITEM-1", "Rejected by Client", "/files/proof.pdf", "2026-08-13")
        plan = MagicMock(docstatus=1, overall_status="In Progress")
        plan.name = "ARP-1"
        plan.remediation_deadline = "2026-08-30"
        plan.remediation_items = [row]
        plan.flags = frappe._dict()
        fake = _raising_frappe()
        fake.get_doc.return_value = plan

        with (
            patch.object(audit_remediation_plan, "frappe", fake),
            patch.object(
                audit_remediation_plan, "_", side_effect=lambda message: message
            ),
            patch.object(audit_remediation_plan, "today", return_value="2026-08-14"),
        ):
            _call(
                audit_remediation_plan.transition_item, "ARP-1", "ITEM-1", "In Progress"
            )
            self.assertIsNone(row.completion_date)
            row.status = "Verified by Client"
            plan.reset_mock()
            with self.assertRaises(frappe.ValidationError):
                _call(
                    audit_remediation_plan.transition_item,
                    "ARP-1",
                    "ITEM-1",
                    "In Progress",
                )
        plan.save.assert_not_called()

    def test_direct_after_submit_item_edit_is_refused(self):
        before = frappe._dict(
            overall_status="In Progress",
            remediation_items=[_item("ITEM-1", "In Progress")],
        )
        current = frappe._dict(
            overall_status="In Progress",
            remediation_items=[
                _item("ITEM-1", "Evidence Submitted", "/files/proof.pdf")
            ],
            flags=frappe._dict(),
        )
        current.get_doc_before_save = lambda: before
        fake = _raising_frappe()

        with (
            patch.object(audit_remediation_plan, "frappe", fake),
            patch.object(
                audit_remediation_plan, "_", side_effect=lambda message: message
            ),
        ):
            with self.assertRaises(frappe.ValidationError):
                audit_remediation_plan.AuditRemediationPlan.before_update_after_submit(
                    current
                )

    def test_the_transition_gate_itself_refuses_a_hand_edit(self):
        """The case above is stopped by the roll-up check — its overall_status no longer
        matches its rows — so the gate that reads ``remediation_transition`` never runs and
        could be deleted whole. Here the roll-up already agrees and the flag is absent, so
        only the transition gate can refuse."""
        before = frappe._dict(
            overall_status="Evidence Submitted",
            remediation_items=[_item("ITEM-1", "In Progress")],
        )
        current = frappe._dict(
            overall_status="Evidence Submitted",
            remediation_items=[
                _item("ITEM-1", "Evidence Submitted", "/files/proof.pdf")
            ],
            flags=frappe._dict(),
        )
        current.get_doc_before_save = lambda: before
        fake = _raising_frappe()

        self.assertEqual(
            audit_remediation_plan.derive_overall_status(
                current.remediation_items, None
            ),
            current.overall_status,
            "the roll-up must already agree, or it is what refuses and the gate is untested",
        )

        with (
            patch.object(audit_remediation_plan, "frappe", fake),
            patch.object(
                audit_remediation_plan, "_", side_effect=lambda message: message
            ),
        ):
            with self.assertRaises(frappe.ValidationError) as raised:
                audit_remediation_plan.AuditRemediationPlan.before_update_after_submit(
                    current
                )

        self.assertIn("remediation action controls", str(raised.exception))
class TestAuditRemediationMetadata(TestCase):
    def test_only_transition_fields_are_mutable_after_submit(self):
        root = Path(__file__).parents[1]
        plan_meta = json.loads(
            (Path(__file__).with_name("audit_remediation_plan.json")).read_text(
                encoding="utf-8"
            )
        )
        item_meta = json.loads(
            (root / "audit_remediation_item" / "audit_remediation_item.json").read_text(
                encoding="utf-8"
            )
        )
        overall = next(
            field
            for field in plan_meta["fields"]
            if field["fieldname"] == "overall_status"
        )
        self.assertTrue(overall["read_only"])
        self.assertTrue(overall["allow_on_submit"])

        fields = {field["fieldname"]: field for field in item_meta["fields"]}
        self.assertTrue(fields["status"]["read_only"])
        self.assertTrue(fields["status"]["allow_on_submit"])
        self.assertTrue(fields["completion_date"]["read_only"])
        self.assertTrue(fields["completion_date"]["allow_on_submit"])
        self.assertTrue(fields["evidence_attached"]["allow_on_submit"])
        for fieldname in (
            "finding_description",
            "remediation_action",
            "owner_role",
            "owner_user",
            "due_date",
        ):
            self.assertFalse(fields[fieldname].get("allow_on_submit", False))
