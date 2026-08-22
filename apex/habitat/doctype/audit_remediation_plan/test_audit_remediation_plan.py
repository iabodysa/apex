# Copyright (c) 2026, afmcoltd
"""What Audit Remediation Plan guarantees, asserted against the DocType itself.

Patterned on ``frappe/tests/test_document.py`` — the subject is ``validate`` (via
``derive_overall_status``), ``before_update_after_submit``, and the whitelisted
``transition_item``. ``overall_status`` is always DERIVED, never hand-set: all items
Verified closes the plan, a past deadline with anything left open makes it Overdue,
and otherwise it tracks how far the items have progressed. Once submitted, an item may
move only through its own permitted transition (Open -> In Progress -> Evidence
Submitted -> Verified/Rejected -> back to In Progress), evidence is required before an
item can claim "Evidence Submitted", and every other shape of edit — adding/reordering
items, changing an immutable finding field, hand-setting the overall status, or editing
a mutable item field outside ``transition_item`` — is refused.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from apex.habitat.doctype.audit_remediation_plan.audit_remediation_plan import (
    refresh_overall_status,
    transition_item,
)

test_dependencies = ["Project"]


def _new_plan(remediation_deadline, items=None):
    record = frappe.copy_doc(frappe.get_test_records("Audit Remediation Plan")[0])
    record.remediation_deadline = remediation_deadline
    record.remediation_items = []
    for item in items or []:
        row = {"remediation_action": "Fix the finding", "due_date": today(), **item}
        record.append("remediation_items", row)
    record.insert()
    return record


class TestAuditRemediationPlan(FrappeTestCase):
    def test_overall_status_is_derived_from_items_and_deadline(self):
        """Five shapes of the same rollup, none of them ever hand-set."""
        open_plan = _new_plan(add_days(today(), 365))
        self.assertEqual(open_plan.overall_status, "Open")

        overdue_plan = _new_plan(add_days(today(), -1))
        self.assertEqual(
            overdue_plan.overall_status,
            "Overdue",
            "a past deadline with nothing closed must roll up to Overdue",
        )

        in_progress_plan = _new_plan(
            add_days(today(), 365),
            items=[{"finding_description": "Finding A", "status": "In Progress"}],
        )
        self.assertEqual(in_progress_plan.overall_status, "In Progress")

        evidence_plan = _new_plan(
            add_days(today(), 365),
            items=[
                {"finding_description": "Finding A", "status": "Evidence Submitted"},
                {"finding_description": "Finding B", "status": "Verified by Client"},
            ],
        )
        self.assertEqual(evidence_plan.overall_status, "Evidence Submitted")

        closed_plan = _new_plan(
            add_days(today(), -1),  # even a past deadline must not override this
            items=[
                {"finding_description": "Finding A", "status": "Verified by Client"},
                {"finding_description": "Finding B", "status": "Verified by Client"},
            ],
        )
        self.assertEqual(
            closed_plan.overall_status,
            "Closed by Client",
            "every item verified must close the plan regardless of the deadline",
        )

    def test_transition_item_is_refused_on_a_draft_plan(self):
        """Items can only be progressed once the plan itself is submitted."""
        plan = _new_plan(
            add_days(today(), 365),
            items=[{"finding_description": "Finding A", "status": "Open"}],
        )

        with self.assertRaisesRegex(frappe.ValidationError, "Only submitted remediation plans"):
            transition_item(plan.name, plan.remediation_items[0].name, "In Progress")

    def test_transition_item_walks_only_its_permitted_path_and_requires_evidence(self):
        """The acceptance path through every state, and the two guards along it."""
        plan = _new_plan(
            add_days(today(), 365),
            items=[{"finding_description": "Finding A", "status": "Open"}],
        )
        plan.submit()
        item_name = plan.remediation_items[0].name

        with self.assertRaisesRegex(frappe.ValidationError, "Cannot move"):
            transition_item(plan.name, item_name, "Evidence Submitted")

        transition_item(plan.name, item_name, "In Progress")

        with self.assertRaisesRegex(frappe.ValidationError, "Evidence is required"):
            transition_item(plan.name, item_name, "Evidence Submitted")

        result = transition_item(
            plan.name, item_name, "Evidence Submitted", evidence_attached="/files/proof.pdf"
        )
        self.assertEqual(result["overall_status"], "Evidence Submitted")
        reloaded = frappe.get_doc("Audit Remediation Plan", plan.name)
        self.assertEqual(reloaded.remediation_items[0].status, "Evidence Submitted")
        self.assertIsNotNone(reloaded.remediation_items[0].completion_date)

        with self.assertRaisesRegex(frappe.ValidationError, "Cannot move"):
            transition_item(plan.name, item_name, "In Progress")

        transition_item(plan.name, item_name, "Rejected by Client")
        transition_item(plan.name, item_name, "In Progress")
        reopened = frappe.get_doc("Audit Remediation Plan", plan.name)
        self.assertIsNone(
            reopened.remediation_items[0].completion_date,
            "returning a rejected action to In Progress must clear its completion date",
        )

    def test_editing_an_immutable_item_field_after_submit_is_refused(self):
        """A finding's description is fixed once the plan carrying it is submitted."""
        plan = _new_plan(
            add_days(today(), 365),
            items=[{"finding_description": "Finding A", "status": "Open"}],
        )
        plan.submit()
        plan.reload()

        plan.remediation_items[0].finding_description = "Rewritten after submission"
        with self.assertRaisesRegex(frappe.ValidationError, "cannot change after submission"):
            plan.save()

    def test_editing_a_mutable_item_field_outside_transition_item_is_refused(self):
        """A status move must go through transition_item; a raw save of the same
        field is refused even though the field itself is mutable in principle, and
        even when the caller also supplies the correctly-derived overall status —
        a save on a submitted plan never runs ``validate`` (Frappe routes it through
        ``update_after_submit`` instead), so the caller must match that derivation
        by hand for this second guard to be the one that fires."""
        plan = _new_plan(
            add_days(today(), 365),
            items=[{"finding_description": "Finding A", "status": "Open"}],
        )
        plan.submit()
        plan.reload()

        plan.remediation_items[0].status = "In Progress"
        plan.overall_status = "In Progress"
        with self.assertRaisesRegex(frappe.ValidationError, "remediation action controls"):
            plan.save()

    def test_refresh_overall_status_rolls_up_a_deadline_that_has_since_passed(self):
        """A submitted plan's status is re-derived, not left stamped at submit time."""
        plan = _new_plan(
            add_days(today(), 5),
            items=[{"finding_description": "Finding A", "status": "Open"}],
        )
        plan.submit()
        self.assertEqual(plan.overall_status, "Open")

        # Push the deadline into the past directly (db_set): the plan's own re-derive
        # must use the same real today() this call does, so the deadline has to have
        # genuinely passed rather than being simulated through an on_date argument
        # that validate()'s own recompute inside the same save would not honour.
        frappe.db.set_value(
            "Audit Remediation Plan", plan.name, "remediation_deadline", add_days(today(), -1)
        )

        result = refresh_overall_status(plan.name)

        self.assertEqual(result["previous_status"], "Open")
        self.assertEqual(result["overall_status"], "Overdue")
        self.assertEqual(
            frappe.db.get_value("Audit Remediation Plan", plan.name, "overall_status"), "Overdue"
        )
