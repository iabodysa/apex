# Copyright (c) 2026, afmcoltd
"""SIM Custody Assignment controller — the SIM custody engine.

Each submitted SIM Custody Assignment is one immutable custody event (Assign,
Transfer, Return, Suspend, Reactivate, Lost, Terminated). A SIM's live state
(``status`` and the ``current_*`` fields on SIM Card) is never edited by hand: it
is REBUILT by replaying every submitted event for that SIM, so the projection
always equals the latest submitted custody state. State transitions take a row
lock on the SIM so two concurrent actions cannot both apply — guaranteeing exactly
one active custody per SIM.

Retirement (Lost / Terminated) is an event in this same chain rather than a status
edit, so a retired SIM keeps its full history, is reversible by cancelling the
event, and is never deleted. Retiring CLOSES the active custody: the current_*
projection is cleared while the event itself keeps the previous_* snapshot of who
held the SIM, so accountability survives the retirement.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate

from apex.logistay.doctype.sim_card.sim_card import set_projection
from apex.logistay.utils.cost_center import (
    resolve_employee_cost_center,
    resolve_project_cost_center,
)

CUSTODIAN_ACTIONS = ("Assign", "Transfer")

TERMINAL_ACTIONS = ("Lost", "Terminated")

ALLOWED_PRIOR_STATUS = {
    "Assign": ("Available",),
    "Transfer": ("Assigned",),
    "Return": ("Assigned",),
    "Suspend": ("Available", "Assigned"),
    "Reactivate": ("Suspended",),
    "Lost": ("Available", "Assigned", "Suspended"),
    "Terminated": ("Available", "Assigned", "Suspended", "Lost"),
}

_INITIAL_STATE = {
    "status": "Available",
    "current_custodian_type": "Unassigned",
    "current_custodian_employee": None,
    "current_project": None,
    "current_cost_center": None,
    "current_assignment": None,
    "assigned_on": None,
}


class SIMCustodyAssignment(Document):
    def validate(self):
        """Runs custodian, retirement, company, cost-center, and prior-status checks before saving."""
        if self.sim_card and not self.company:
            self.company = frappe.db.get_value("SIM Card", self.sim_card, "company")
        self._validate_custodian_inputs()
        self._require_retirement_reason()
        self._reject_back_dated_retirement()
        self._enforce_company_compatibility()
        self._snapshot_cost_centers()
        if self.sim_card:
            self._check_prior_status(frappe.db.get_value("SIM Card", self.sim_card, "status"))

    def _validate_custodian_inputs(self):
        """Requires a custodian type and matching employee or project on an Assign or Transfer action."""
        if self.action in CUSTODIAN_ACTIONS:
            if not self.custodian_type:
                frappe.throw(_("Custodian Type is required to {0} a SIM.").format(self.action))
            if self.custodian_type == "Employee" and not self.employee:
                frappe.throw(_("Select the Employee receiving the SIM."))
            if self.custodian_type == "Project" and not self.project:
                frappe.throw(_("Select the Project receiving the SIM."))
            if self.custodian_type == "Employee":
                self.project = None
            else:
                self.employee = None
        else:
            self.custodian_type = None
            self.employee = None
            self.project = None

    def _require_retirement_reason(self):
        """Retiring a SIM must say why, on the server."""
        if self.action in TERMINAL_ACTIONS and not (self.reason or "").strip():
            frappe.throw(
                _("A Reason is required to record SIM {0} as {1}.").format(
                    self.sim_card, _(self.action)
                ),
                title=_("Reason Required"),
            )

    def _reject_back_dated_retirement(self):
        """A retirement must be the LAST event on the SIM by date, not just by clock.

        ``rebuild_sim_projection`` replays events ordered by ``assignment_date``, so a
        Lost event dated before an existing Assign replays FIRST and the Assign then
        overwrites it — the operator retires the SIM and the SIM still reads Assigned.
        The submit-time status check cannot catch this: it reads the CURRENT status,
        which legitimately allows the transition.
        """
        if self.action not in TERMINAL_ACTIONS or not (self.sim_card and self.assignment_date):
            return
        latest = frappe.get_all(
            "SIM Custody Assignment",
            filters={"sim_card": self.sim_card, "docstatus": 1, "name": ["!=", self.name or ""]},
            pluck="assignment_date",
            order_by="assignment_date desc",
            limit=1,
        )
        latest = latest[0] if latest else None
        if latest and getdate(self.assignment_date) < getdate(latest):
            frappe.throw(
                _(
                    "The {0} date {1} is before SIM {2}'s last custody event on {3}. "
                    "Record the retirement on or after that date."
                ).format(_(self.action), self.assignment_date, self.sim_card, latest),
                title=_("Back-Dated Retirement"),
            )

    def _enforce_company_compatibility(self):
        """An employee custodian must belong to the SIM's company. The SIM company
        is the security scope, so a cross-company custody would leak a SIM into a
        company the holder is not in — fail closed."""
        if (
            self.action in CUSTODIAN_ACTIONS
            and self.custodian_type == "Employee"
            and self.employee
        ):
            emp_company = frappe.db.get_value("Employee", self.employee, "company")
            if emp_company and self.company and emp_company != self.company:
                frappe.throw(
                    _("Employee {0} belongs to company {1}, not the SIM's company {2}.").format(
                        self.employee, emp_company, self.company
                    )
                )

    def _snapshot_cost_centers(self):
        """Resolve and freeze the cost centers on the event itself, so a later edit
        to the Employee/Department/Project never rewrites this record's history."""
        if self.action in CUSTODIAN_ACTIONS:
            self.employee_cost_center = (
                resolve_employee_cost_center(self.employee, self.company)
                if self.custodian_type == "Employee"
                else None
            )
            self.project_cost_center = (
                resolve_project_cost_center(self.project)
                if self.custodian_type == "Project"
                else None
            )
            self.cost_center = self.employee_cost_center or self.project_cost_center
        else:
            self.employee_cost_center = None
            self.project_cost_center = None
            self.cost_center = None

    def _check_prior_status(self, status):
        """Blocks the action unless the SIM's current status is one it is allowed to start from."""
        allowed = ALLOWED_PRIOR_STATUS.get(self.action, ())
        if status not in allowed:
            frappe.throw(
                _("Cannot {0} SIM {1}: its status is {2}, expected {3}.").format(
                    self.action,
                    self.sim_card,
                    status or _("unknown"),
                    " / ".join(allowed) or _("none"),
                )
            )

    def before_submit(self):
        """Snapshots the SIM's previous custodian before this event overwrites the projection."""
        prior = (
            frappe.db.get_value(
                "SIM Card",
                self.sim_card,
                ["current_custodian_type", "current_custodian_employee", "current_project"],
                as_dict=True,
            )
            or {}
        )
        self.previous_custodian_type = prior.get("current_custodian_type")
        self.previous_custodian_employee = prior.get("current_custodian_employee")
        self.previous_project = prior.get("current_project")

    def on_submit(self):
        """Rechecks the SIM's locked status, then rebuilds its custody projection."""
        locked_status = frappe.db.get_value(
            "SIM Card", self.sim_card, "status", for_update=True
        )
        self._check_prior_status(locked_status)
        rebuild_sim_projection(self.sim_card)

    def on_cancel(self):
        """Rebuilds the SIM's custody projection after this event is cancelled."""
        frappe.db.get_value("SIM Card", self.sim_card, "status", for_update=True)
        rebuild_sim_projection(self.sim_card)


def _apply_event(state, event):
    """Folds one custody event into the running projection state."""
    action = event.get("action")
    if action in CUSTODIAN_ACTIONS:
        state.update(
            {
                "status": "Assigned",
                "current_custodian_type": event.get("custodian_type") or "Unassigned",
                "current_custodian_employee": event.get("employee"),
                "current_project": event.get("project"),
                "current_cost_center": event.get("cost_center"),
                "current_assignment": event.get("name"),
                "assigned_on": event.get("assignment_date"),
            }
        )
    elif action == "Return":
        state.update(dict(_INITIAL_STATE))
    elif action in TERMINAL_ACTIONS:
        state.update(dict(_INITIAL_STATE))
        state["status"] = action
    elif action == "Suspend":
        state["status"] = "Suspended"
    elif action == "Reactivate":
        state["status"] = (
            "Assigned" if state["current_custodian_type"] != "Unassigned" else "Available"
        )


def rebuild_sim_projection(sim_card: str) -> None:
    """Replay every submitted custody event for a SIM to compute and store its
    current projection. Deterministic and idempotent — the single source of truth
    behind "current SIM state matches the latest submitted custody state".

    Retirement is IN the chain (Lost / Terminated are events, not out-of-band status
    edits), so the replay is the whole truth and nothing is preserved from the row
    being overwritten. That is what makes retirement reversible: cancelling the Lost
    event drops it from the replay and the SIM returns to the state it had before.
    """
    events = frappe.get_all(
        "SIM Custody Assignment",
        filters={"sim_card": sim_card, "docstatus": 1},
        fields=[
            "name",
            "action",
            "custodian_type",
            "employee",
            "project",
            "cost_center",
            "assignment_date",
        ],
        order_by="assignment_date asc, creation asc",
    )
    state = dict(_INITIAL_STATE)
    for event in events:
        _apply_event(state, event)

    set_projection(sim_card, **state)
