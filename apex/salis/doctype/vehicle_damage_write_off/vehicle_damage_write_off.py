# Copyright (c) 2026, AFMCO and contributors
"""Vehicle Damage Write-Off controller.

Submittable damage write-off case raised from a Vehicle Handover discrepancy.
Write-off authority is enforced by the native Frappe Workflow "Vehicle Damage
Write-Off Workflow": the Approve transition is restricted to the Fleet Manager /
System Manager roles, with self-approval disabled.

Delegation-of-Authority gate: ``estimated_cost`` is compared on save against the
Write-Off Operations Threshold (``writeoff_ops_threshold`` in Salis Settings)
to derive ``needs_operations``. The workflow's "Authorize (Regional)" transition
(Fleet Supervisor) is gated off when that flag is set, so only the Operations tier
(Fleet Manager / System Manager) can approve a high-value case. ``_enforce_doa_gate``
is the hard, no-bypass server guard held in addition to the workflow condition
(defence in depth) — any submit landing the case in Approved without the required
tier is blocked even if it bypasses the workflow action.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from apex.salis.utils import add_timeline_note

# [#4xgl2m]
_OPERATIONS_ROLES = {"Fleet Manager", "System Manager"}


class VehicleDamageWriteOff(Document):
    def validate(self):
        # [#83ntz1]
        if self.status and self.status != "Open" and not self.evidence:
            frappe.throw(_("Evidence is required before moving the write-off case beyond Open."))
        # [#kh1fqw]
        if self.estimated_cost is not None and flt(self.estimated_cost) < 0:
            frappe.throw(_("Estimated cost cannot be negative."))
        self._derive_needs_operations()
        self._enforce_doa_gate()
        self._stamp_approver()

    def _derive_needs_operations(self):
        """Server-side DoA derivation: set ``needs_operations`` when the estimated
        cost reaches the Write-Off Operations Threshold (read via the zero-trap
        helper). Derived here — never trusted from the client — so the gate cannot
        be under-stated."""
        from apex.apex_core.doctype.salis_settings.salis_settings import get_salis_float

        threshold = get_salis_float("writeoff_ops_threshold", 2000.0)
        self.needs_operations = 1 if flt(self.estimated_cost) >= threshold else 0

    def _enforce_doa_gate(self):
        """Hard, no-bypass DoA block (defence in depth alongside the workflow
        condition). When a write-off enters the Approved state and the case needs
        Operations authority, the approver must hold an Operations-tier role; this
        cannot be bypassed even on a save that does not go through the workflow."""
        if self.status != "Approved" or not self.needs_operations:
            return
        if not (_OPERATIONS_ROLES & set(frappe.get_roles())):
            frappe.throw(
                _(
                    "This write-off reaches the Operations threshold and can only be approved by Operations-tier authority (Fleet Manager)."
                )
            )

    def on_submit(self):
        self._stamp_source_incident()
        add_timeline_note(
            "Salis Vehicle",
            self.vehicle,
            _("Damage write-off {0} submitted (estimated {1} SAR).").format(
                self.name, self.estimated_cost
            ),
        )

    def on_cancel(self):
        self._clear_source_incident()
        add_timeline_note(
            "Salis Vehicle",
            self.vehicle,
            _("Damage write-off {0} cancelled.").format(self.name),
        )

    # [#f9hua6]

    def _stamp_approver(self):
        if self.status == "Approved" and not self.approved_by:
            self.approved_by = frappe.session.user

    def _stamp_source_incident(self):
        # [#oxkzun]
        if self.source_incident:
            frappe.db.set_value(
                "Vehicle Incident", self.source_incident, "write_off_case", self.name
            )

    def _clear_source_incident(self):
        # [#d04slv]
        if self.source_incident:
            frappe.db.set_value(
                "Vehicle Incident", self.source_incident, "write_off_case", None
            )
