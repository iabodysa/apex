from __future__ import annotations

import json
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from apex.habitat.doctype.audit_remediation_plan import audit_remediation_plan


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
