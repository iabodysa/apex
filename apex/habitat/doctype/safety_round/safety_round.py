# Copyright (c) 2026, AFMCO and contributors
"""Safety Round controller.

A Safety Round is the periodic safety pass over one building for a given cadence
(Daily / Weekly / Monthly / Quarterly / Annual). The individual checks live on
Safety Task Execution rows that point back at the round via their safety_round
link; this record groups them and, on submit, derives a single overall_result
from their execution statuses. It supersedes the legacy Safety Inspection Report.

Result rule (worst status wins): any "Not Done" -> Fail; otherwise any "Poor" ->
Needs Attention; otherwise Pass. A round with no linked executions is a Pass
(nothing failed).
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class SafetyRound(Document):
    def validate(self):
        self._guard_duplicate()

    def _guard_duplicate(self):
        # [#swjvq9]
        if self.is_reinspection:
            return

        duplicate = frappe.db.exists(
            "Safety Round",
            {
                "building": self.building,
                "round_date": self.round_date,
                "cadence": self.cadence,
                "is_reinspection": 0,
                "docstatus": ["<", 2],
                "name": ["!=", self.name or ""],
            },
        )
        if duplicate:
            frappe.throw(
                _(
                    "A {0} Safety Round already exists for {1} on {2} ({3}). "
                    "Tick Is Re-inspection to record a follow-up round."
                ).format(self.cadence, self.building, self.round_date, duplicate)
            )

    def on_submit(self):
        self.db_set("overall_result", self._derive_overall_result())
        # [#rylc44]
        from apex.habitat.safety_engine import post_safety_findings

        post_safety_findings(self)
        # [#a069cl]
        self._clear_building_scan_alerts()
        # [#23qg97]
        self._publish_safety_update("submit")

    def _clear_building_scan_alerts(self) -> None:
        """Auto-clear the unread "no recent safety round" bell alerts for this building.

        A submitted round of any cadence satisfies the daily zero-rounds scan (which
        only checks for a submitted round in the trailing window), so its Building-linked
        Notification Log alerts — raised to the Safety Officer and the responsible
        supervisor — are now stale; mark every unread Alert linked to this Building read
        in one write. The weekly-coverage alert is subject-keyed (no Building link) and
        intentionally untouched: a daily round does not satisfy weekly coverage."""
        try:
            frappe.db.set_value(
                "Notification Log",
                {
                    "type": "Alert",
                    "read": 0,
                    "document_type": "Building",
                    "document_name": self.building,
                },
                "read",
                1,
                update_modified=False,
            )
        except Exception:
            # Cosmetic cleanup — swallow (no rollback here, which would abort the submit).
            frappe.log_error(
                message=frappe.get_traceback(),
                title=f"Safety Round alert clear failed for {self.building}"[:140],
            )

    def on_cancel(self):
        # [#qgyftc]
        from apex.habitat.safety_engine import reverse_safety_findings

        reverse_safety_findings(self.name)
        # [#c7t1n3]
        self._publish_safety_update("cancel")

    def _publish_safety_update(self, action: str) -> None:
        """Signal the /safety portal to refetch its due set ahead of a manual
        reload. Routed to the Safety Round doctype room; the socket server
        delivers only to recipients with read permission, so building scope is
        honoured without extra filtering. after_commit so subscribers refetch
        committed state. The payload is advisory only — the SPA refetches via
        get_due_cadences, it does not trust the message body."""
        frappe.publish_realtime(
            "safety_update",
            {"building": self.building, "cadence": self.cadence, "action": action},
            doctype="Safety Round",
            after_commit=True,
        )

    def _derive_overall_result(self):
        statuses = frappe.get_all(
            "Safety Task Execution",
            filters={"safety_round": self.name, "docstatus": 1},
            pluck="execution_status",
        )
        if "Not Done" in statuses:
            return "Fail"
        if "Poor" in statuses:
            return "Needs Attention"
        return "Pass"
