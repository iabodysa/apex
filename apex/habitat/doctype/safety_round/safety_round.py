# Copyright (c) 2026, afmcoltd
"""Safety Round controller. Periodic safety pass over one building for a given cadence (Daily / Weekly / Monthly / Quarterly / Annual). The individual checks live on Safety Task Execution rows; this record groups them and, on submit, derives a single overall_result from their execution statuses.

Result rule: any "Not Done" -> Fail; otherwise any "Poor" -> Needs Attention; otherwise Pass.

Maker-checker: the Safety Officer holds create + write and NOT submit (see the DocPerms), so the officer composes the round as DRAFTS and a manager / supervisor closes it. Submitting is the CHECKER's act of ratifying the maker's evidence, and on_submit performs that ratification: every still-draft execution on the round is submitted before the result is derived. Without it the checker's approval read the maker's drafts as absent — an all-"Not Done" round closed as "Pass" and none of its findings reached the Safety Finding Ledger. before_submit refuses a round carrying no rated task at all, so an unrated round can never claim a result; it is deliberately NOT in validate(), because the maker must SAVE the round first to have something for the executions to link to.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from apex.apex_core.utils.portal_live import notify_building
from apex.habitat.safety_engine import post_safety_findings, reverse_safety_findings
from apex.habitat.tasks.safety import zero_rounds_alert_subject


class SafetyRound(Document):
    def validate(self):
        """Runs the duplicate-round guard when a Safety Round is saved."""
        self._guard_duplicate()

    def _guard_duplicate(self):
        """Blocks a Safety Round duplicating an existing one for the same building, date and cadence."""
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
        """Runs the no-rated-task guard before a Safety Round can be submitted."""
        self._guard_rated()

    def _guard_rated(self):
        """Refuse to close a round nobody rated.

        The overall result is derived from the linked Safety Task Execution rows,
        so a round carrying none derives "Pass" — a submitted, signed-off record
        asserting the building was checked and found sound when nothing was
        checked at all. Counts drafts too (docstatus < 2): the maker's unratified
        rows ARE the ratings, and on_submit is about to submit them. Cancelled
        rows (docstatus 2) do not count, so cancelling every execution of a round
        cannot leave a rated-looking round behind.

        In before_submit rather than validate so the maker can still SAVE the
        round first — an execution needs an existing round to link to.
        """
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
        """Submits draft executions, stores the derived overall result, and posts safety findings."""
        self._ratify_executions()
        self.db_set("overall_result", self._derive_overall_result())
        post_safety_findings(self)
        self._clear_building_scan_alerts()
        notify_building(self.building)

    def _ratify_executions(self) -> int:
        """Submit the round's still-draft executions, then return how many.

        The maker (Safety Officer) cannot submit a Safety Task Execution, so the
        evidence they record stays at docstatus 0 until someone with submit
        closes the round. Everything downstream of this method reads
        ``docstatus == 1`` — _derive_overall_result, post_safety_findings, the
        report email — so without this step the checker's approval silently
        discards the maker's ratings and findings.

        Deliberately NOT ignore_permissions: submitting a round is a claim about
        its evidence, so the closer must hold submit on the evidence too. Every
        role that can submit a Safety Round (System Manager, Accommodation
        Manager, Resident Supervisor) also holds submit on Safety Task Execution,
        so this is not a new gate — it just refuses loudly instead of closing a
        round whose rows nobody was entitled to ratify.

        A no-op for the portal / API path (safety_checklist._create_round), which
        submits each execution before submitting the round.
        """
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
        """Auto-clear the unread "no recent safety round" bell alerts for this building.

        A submitted round of any cadence satisfies the daily zero-rounds scan (which
        only checks for a submitted round in the trailing window), so its alerts are now
        stale. Two writes because the scan raises the same notice on two keys: the
        responsible supervisor's copy is Building-linked, while the Safety Officer's
        carries no link (that role holds no read on Building) and is keyed by subject.
        The weekly-coverage alert has its own subject and stays untouched: a daily round
        does not satisfy weekly coverage."""
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
        """Reverses this round's posted safety findings and rings the building's watchers."""
        reverse_safety_findings(self.name)
        notify_building(self.building)

    def _derive_overall_result(self):
        """Derives Fail, Needs Attention or Pass from the round's task execution statuses."""
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
