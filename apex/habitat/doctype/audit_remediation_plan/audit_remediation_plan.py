# Copyright (c) 2026, afmcoltd
"""Client Audit Remediation Plan lifecycle.

``refresh_overall_status`` saves with ``ignore_permissions`` because the plan's status is DERIVED
from its items closing, and the person who closes the last item is rarely the plan's owner. The
field is machine-maintained; a role able to write it could report a plan complete by hand.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, today

ALLOWED_ITEM_TRANSITIONS = {
    "Open": ("In Progress",),
    "In Progress": ("Evidence Submitted",),
    "Evidence Submitted": ("Verified by Client", "Rejected by Client"),
    "Rejected by Client": ("In Progress",),
    "Verified by Client": (),
}

_IMMUTABLE_ITEM_FIELDS = (
    "finding_description",
    "remediation_action",
    "owner_role",
    "owner_user",
    "due_date",
)
_MUTABLE_ITEM_FIELDS = ("status", "completion_date", "evidence_attached")
_TRANSITION_SAVEPOINT = "audit_remediation_transition"


def derive_overall_status(items, remediation_deadline, on_date=None) -> str:
    """Roll item states and deadline into one deterministic plan state."""
    statuses = [str(item.status or "Open") for item in items]
    if statuses and all(status == "Verified by Client" for status in statuses):
        return "Closed by Client"
    if remediation_deadline and getdate(remediation_deadline) < getdate(
        on_date or today()
    ):
        return "Overdue"
    if (
        statuses
        and all(
            status in ("Evidence Submitted", "Verified by Client")
            for status in statuses
        )
        and any(status == "Evidence Submitted" for status in statuses)
    ):
        return "Evidence Submitted"
    if any(status != "Open" for status in statuses):
        return "In Progress"
    return "Open"


def _snapshot(row, fields):
    return {field: row.get(field) for field in fields}


class AuditRemediationPlan(Document):
    def validate(self):
        """Keep the parent status derived from item progress and deadline."""
        self.overall_status = derive_overall_status(
            self.remediation_items,
            self.remediation_deadline,
        )

    def before_update_after_submit(self):
        """Reject direct child edits; only server-owned transitions may change them."""
        previous = self.get_doc_before_save()
        if not previous:
            frappe.throw(_("Could not verify the submitted remediation plan changes."))

        old_rows = list(previous.remediation_items or [])
        new_rows = list(self.remediation_items or [])
        old_names = [row.name for row in old_rows]
        new_names = [row.name for row in new_rows]
        if old_names != new_names:
            frappe.throw(
                _(
                    "Remediation actions cannot be added, removed, or reordered after submission."
                )
            )

        old_by_name = {row.name: row for row in old_rows}
        for row in new_rows:
            old_row = old_by_name[row.name]
            if _snapshot(row, _IMMUTABLE_ITEM_FIELDS) != _snapshot(
                old_row, _IMMUTABLE_ITEM_FIELDS
            ):
                frappe.throw(
                    _("Remediation action details cannot change after submission.")
                )

        expected_overall = derive_overall_status(
            new_rows,
            self.remediation_deadline,
        )
        if self.overall_status != expected_overall:
            frappe.throw(_("Overall Status must match the remediation actions."))

        transition = self.flags.get("remediation_transition")
        rollup_only = self.flags.get("remediation_rollup_only")
        if rollup_only:
            if any(
                _snapshot(row, _MUTABLE_ITEM_FIELDS)
                != _snapshot(old_by_name[row.name], _MUTABLE_ITEM_FIELDS)
                for row in new_rows
            ):
                frappe.throw(
                    _("The deadline rollup cannot change remediation actions.")
                )
            return

        if not transition:
            if previous.overall_status != self.overall_status or any(
                _snapshot(row, _MUTABLE_ITEM_FIELDS)
                != _snapshot(old_by_name[row.name], _MUTABLE_ITEM_FIELDS)
                for row in new_rows
            ):
                frappe.throw(
                    _(
                        "Use the remediation action controls to update submitted actions."
                    )
                )
            return

        item_name = transition["item_name"]
        if item_name not in old_by_name:
            frappe.throw(_("The selected remediation action no longer exists."))
        for row in new_rows:
            old_row = old_by_name[row.name]
            old_values = _snapshot(old_row, _MUTABLE_ITEM_FIELDS)
            new_values = _snapshot(row, _MUTABLE_ITEM_FIELDS)
            if row.name == item_name:
                if (
                    old_values != transition["before"]
                    or new_values != transition["after"]
                ):
                    frappe.throw(
                        _("The remediation transition changed unexpected values.")
                    )
            elif old_values != new_values:
                frappe.throw(_("Only the selected remediation action may change."))


def _find_item(plan, item_name: str):
    for item in plan.remediation_items:
        if item.name == item_name:
            return item
    frappe.throw(_("Remediation action {0} was not found.").format(item_name))


@frappe.whitelist(methods=["POST"])
def transition_item(
    name: str,
    item_name: str,
    target_status: str,
    evidence_attached: str | None = None,
) -> dict:
    """Apply one permitted item transition and roll up the parent atomically."""
    plan = frappe.get_doc("Audit Remediation Plan", name, for_update=True)
    plan.check_permission("write")
    if plan.docstatus != 1:
        frappe.throw(_("Only submitted remediation plans can be progressed."))

    item = _find_item(plan, item_name)
    current_status = str(item.status or "Open")
    target_status = str(target_status or "").strip()
    if target_status not in ALLOWED_ITEM_TRANSITIONS.get(current_status, ()):
        frappe.throw(
            _("Cannot move a remediation action from {0} to {1}.").format(
                current_status,
                target_status or _("an empty status"),
            )
        )

    evidence = str(evidence_attached or item.evidence_attached or "").strip()
    if target_status == "Evidence Submitted" and not evidence:
        frappe.throw(_("Evidence is required before submitting a remediation action."))

    before = _snapshot(item, _MUTABLE_ITEM_FIELDS)
    item.status = target_status
    if target_status == "Evidence Submitted":
        item.evidence_attached = evidence
        item.completion_date = today()
    elif current_status == "Rejected by Client" and target_status == "In Progress":
        item.completion_date = None

    after = _snapshot(item, _MUTABLE_ITEM_FIELDS)
    plan.overall_status = derive_overall_status(
        plan.remediation_items,
        plan.remediation_deadline,
    )
    plan.flags.remediation_transition = {
        "item_name": item.name,
        "before": before,
        "after": after,
    }

    frappe.db.savepoint(_TRANSITION_SAVEPOINT)
    try:
        plan.save()
        plan.add_comment(
            "Comment",
            _("Remediation action {0}: {1} to {2}.").format(
                item.name,
                current_status,
                target_status,
            ),
        )
    except Exception:
        frappe.db.rollback(save_point=_TRANSITION_SAVEPOINT)
        raise
    return {
        "name": plan.name,
        "item": item.name,
        "item_status": target_status,
        "overall_status": plan.overall_status,
    }


def refresh_overall_status(name: str, on_date=None) -> dict:
    """Recompute one submitted plan through the same rollup used by actions."""
    plan = frappe.get_doc("Audit Remediation Plan", name, for_update=True)
    if plan.docstatus != 1:
        frappe.throw(_("Only submitted remediation plans can be rolled up."))
    previous_status = plan.overall_status
    status = derive_overall_status(
        plan.remediation_items,
        plan.remediation_deadline,
        on_date,
    )
    if status != previous_status:
        plan.flags.remediation_rollup_only = True
        plan.overall_status = status
        plan.save(ignore_permissions=True)
    return {
        "name": plan.name,
        "previous_status": previous_status,
        "overall_status": status,
    }
