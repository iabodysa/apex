# Copyright (c) 2026, AFMCO and contributors
"""SIM Custody Assignment controller — the SIM custody engine.

Each submitted SIM Custody Assignment is one immutable custody event (Assign,
Transfer, Return, Suspend, Reactivate). A SIM's live state (``status`` and the
``current_*`` fields on SIM Card) is never edited by hand: it is REBUILT by
replaying every submitted event for that SIM, so the projection always equals the
latest submitted custody state. State transitions take a row lock on the SIM so
two concurrent actions cannot both apply — guaranteeing exactly one active custody
per SIM.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from apex.sim_operations.doctype.sim_card.sim_card import set_projection
from apex.sim_operations.utils.cost_center import (
    resolve_employee_cost_center,
    resolve_project_cost_center,
)

# Actions that take a custodian (employee or project); the rest take none.
CUSTODIAN_ACTIONS = ("Assign", "Transfer")

# The SIM status that must hold immediately BEFORE each action is applied.
ALLOWED_PRIOR_STATUS = {
    "Assign": ("Available",),
    "Transfer": ("Assigned",),
    "Return": ("Assigned",),
    "Suspend": ("Available", "Assigned"),
    "Reactivate": ("Suspended",),
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
        if self.sim_card and not self.company:
            self.company = frappe.db.get_value("SIM Card", self.sim_card, "company")
        self._validate_custodian_inputs()
        self._enforce_company_compatibility()
        self._snapshot_cost_centers()
        if self.sim_card:
            # Friendly early guard; the authoritative one runs under lock at submit.
            self._check_prior_status(frappe.db.get_value("SIM Card", self.sim_card, "status"))

    def _validate_custodian_inputs(self):
        if self.action in CUSTODIAN_ACTIONS:
            if not self.custodian_type:
                frappe.throw(_("Custodian Type is required to {0} a SIM.").format(self.action))
            if self.custodian_type == "Employee" and not self.employee:
                frappe.throw(_("Select the Employee receiving the SIM."))
            if self.custodian_type == "Project" and not self.project:
                frappe.throw(_("Select the Project receiving the SIM."))
            # Keep only the field matching the chosen custodian type.
            if self.custodian_type == "Employee":
                self.project = None
            else:
                self.employee = None
        else:
            # Return / Suspend / Reactivate carry no custodian input.
            self.custodian_type = None
            self.employee = None
            self.project = None

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
        # Immutable snapshot of the custody state this event supersedes.
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
        # Lock the SIM row for the whole transaction, read the prior status UNDER
        # the lock, and re-check the transition. This is the race-safe guarantee of
        # exactly one active custody per SIM (a concurrent action blocks here).
        locked_status = frappe.db.get_value(
            "SIM Card", self.sim_card, "status", for_update=True
        )
        self._check_prior_status(locked_status)
        rebuild_sim_projection(self.sim_card)

    def on_cancel(self):
        # Roll the SIM back by replaying the remaining submitted events (this one is
        # now cancelled and excluded).
        frappe.db.get_value("SIM Card", self.sim_card, "status", for_update=True)
        rebuild_sim_projection(self.sim_card)


def _apply_event(state, event):
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

    A terminal status set outside the custody chain (Lost / Terminated) is
    preserved: replaying custody must never silently resurrect a lost SIM.
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

    current = frappe.db.get_value("SIM Card", sim_card, "status")
    if current in ("Lost", "Terminated"):
        state["status"] = current

    set_projection(sim_card, **state)
