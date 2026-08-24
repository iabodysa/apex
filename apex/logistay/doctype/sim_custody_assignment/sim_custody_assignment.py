# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate

from apex.apex_core.utils.system_notify import notify_user_system
from apex.logistay import permissions
from apex.logistay.doctype.sim_card.sim_card import set_projection
from apex.logistay.utils.cost_center import (
    resolve_employee_cost_center,
    resolve_project_cost_center,
)
from apex.logistay.utils.roles import sim_operations_users

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
        self._validate_custodian_inputs()
        self._require_retirement_reason()
        self._reject_back_dated_event()
        self._enforce_company_compatibility()
        self._snapshot_cost_centers()
        if self.sim_card:
            self._check_prior_status(frappe.db.get_value("SIM Card", self.sim_card, "status"))

    def _validate_custodian_inputs(self):
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
        if self.action in TERMINAL_ACTIONS and not (self.reason or "").strip():
            frappe.throw(
                _("A Reason is required to record SIM {0} as {1}.").format(
                    self.sim_card, _(self.action)
                ),
                title=_("Reason Required"),
            )

    def _reject_back_dated_event(self):
        if not (self.sim_card and self.assignment_date):
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
                    "Record it on or after that date."
                ).format(_(self.action), self.assignment_date, self.sim_card, latest),
                title=_("Back-Dated Custody Event"),
            )

    def _enforce_company_compatibility(self):
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
                    _(self.action),
                    self.sim_card,
                    _(status) if status else _("unknown"),
                    " / ".join(_(s) for s in allowed) or _("none"),
                )
            )

    def before_submit(self):
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
        locked_status = frappe.db.get_value(
            "SIM Card", self.sim_card, "status", for_update=True
        )
        self._check_prior_status(locked_status)
        rebuild_sim_projection(self.sim_card)
        if self.action == "Suspend":
            self._notify_suspended()

    def _notify_suspended(self):
        subject = _("SIM Suspended: {0}").format(self.sim_card)
        if self.previous_custodian_employee:
            body = _("A SIM has been suspended: {0} (held by {1}).").format(
                self.sim_card, self.previous_custodian_employee
            )
        else:
            body = _("A SIM has been suspended: {0}.").format(self.sim_card)

        for user in sim_operations_users():
            restrict, allowed = permissions.report_company_scope(user, doctype="SIM Card")
            if restrict and self.company not in (allowed or []):
                continue
            notify_user_system(
                user, subject, body,
                document_type="SIM Custody Assignment", document_name=self.name,
            )

    def on_cancel(self):
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
    Event = frappe.qb.DocType("SIM Custody Assignment")
    events = (
        frappe.qb.from_(Event)
        .select(
            Event.name,
            Event.action,
            Event.custodian_type,
            Event.employee,
            Event.project,
            Event.cost_center,
            Event.assignment_date,
        )
        .where(Event.sim_card == sim_card)
        .where(Event.docstatus == 1)
        .orderby(Event.assignment_date)
        .orderby(Event.creation)
        .for_update()
        .run(as_dict=True)
    )
    state = dict(_INITIAL_STATE)
    for event in events:
        _apply_event(state, event)

    set_projection(sim_card, **state)
