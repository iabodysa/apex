# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from apex.apex_core.utils.portal_live import notify_building
from apex.habitat.safety_engine import post_safety_findings, reverse_safety_findings
from apex.habitat.tasks.safety import zero_rounds_alert_subject


class SafetyRound(Document):
    def validate(self):
        self._guard_duplicate()

    def _guard_duplicate(self):
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

    def before_submit(self):
        self._guard_rated()

    def _guard_rated(self):
        if frappe.db.exists(
            "Safety Task Execution",
            {"safety_round": self.name, "docstatus": ["<", 2]},
        ):
            return
        frappe.throw(
            _(
                "Safety Round {0} has no rated safety task. Record at least one "
                "Safety Task Execution against the round before submitting it."
            ).format(self.name),
            title=_("No Rated Safety Task"),
        )

    def on_submit(self):
        self._ratify_executions()
        self.db_set("overall_result", self._derive_overall_result())
        post_safety_findings(self)
        self._clear_building_scan_alerts()
        notify_building(self.building)

    def _ratify_executions(self) -> int:
        drafts = frappe.get_all(
            "Safety Task Execution",
            filters={"safety_round": self.name, "docstatus": 0},
            pluck="name",
            order_by="creation asc",
        )
        for name in drafts:
            frappe.get_doc("Safety Task Execution", name).submit()
        return len(drafts)

    def _clear_building_scan_alerts(self) -> None:
        label = frappe.db.get_value("Building", self.building, "building_name") or self.building
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
            frappe.db.set_value(
                "Notification Log",
                {
                    "type": "Alert",
                    "read": 0,
                    "subject": zero_rounds_alert_subject(label),
                },
                "read",
                1,
                update_modified=False,
            )
        except Exception:
            frappe.log_error(
                message=frappe.get_traceback(),
                title=f"Safety Round alert clear failed for {self.building}"[:140],
            )

    def on_cancel(self):
        reverse_safety_findings(self.name)
        notify_building(self.building)

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
