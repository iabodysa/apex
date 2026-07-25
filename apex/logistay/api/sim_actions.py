# Copyright (c) 2026, AFMCO and contributors
"""POST-only custody + edit actions behind the Telecom Control page.

Each action re-checks permission and state ON THE SERVER — the page's button
state is only a hint. Custody transitions run through the SIM Custody Assignment
controller, whose on_submit takes the SIM row lock and re-validates the transition
under that lock, so a stale, concurrent, or out-of-state click fails cleanly. These
methods deliberately do NOT use ignore_permissions: the acting user's own create /
submit / write permission (and the company-scope has_permission hook) is what
authorizes the action. Editing a mobile number updates the SIM in place and never
creates a separate history DocType — track_changes records the edit natively.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import today

from apex.logistay.utils.normalize import normalize_msisdn

_VALID_ACTIONS = ("Assign", "Transfer", "Return", "Suspend", "Reactivate")


def _load_sim(sim_card):
    if not sim_card or not frappe.db.exists("SIM Card", sim_card):
        frappe.throw(_("SIM Card {0} does not exist.").format(sim_card))
    return frappe.get_doc("SIM Card", sim_card)


@frappe.whitelist(methods=["POST"])
def perform_custody_action(
    sim_card,
    action,
    custodian_type=None,
    employee=None,
    project=None,
    assignment_date=None,
    reason=None,
):
    """Create and submit one SIM Custody Assignment for the given action.

    The controller enforces the state machine, the single-active-custody row lock,
    the company compatibility check, and the cost-center snapshot. Permission is the
    acting user's own create/submit right plus the company-scope hook — no bypass.
    """
    if action not in _VALID_ACTIONS:
        frappe.throw(_("Unknown custody action: {0}").format(action))
    sim = _load_sim(sim_card)
    # Read scope on the SIM the action targets (company-scoped has_permission).
    sim.check_permission("read")

    doc = frappe.get_doc(
        {
            "doctype": "SIM Custody Assignment",
            "company": sim.company,
            "sim_card": sim.name,
            "action": action,
            "assignment_date": assignment_date or today(),
            "custodian_type": custodian_type,
            "employee": employee,
            "project": project,
            "reason": reason,
        }
    )
    doc.insert()
    doc.submit()

    return {
        "assignment": doc.name,
        "status": frappe.db.get_value("SIM Card", sim.name, "status"),
    }


@frappe.whitelist(methods=["POST"])
def edit_mobile_number(sim_card, mobile_number):
    """Update a SIM's mobile number in place (re-validates normalized uniqueness).

    No separate history DocType is created — the number stays on SIM Card and the
    change is captured by the SIM Card timeline (track_changes).
    """
    if not mobile_number or not normalize_msisdn(mobile_number):
        frappe.throw(_("Enter a valid mobile number."))
    sim = _load_sim(sim_card)
    sim.check_permission("write")
    # Lock the row so a concurrent edit / custody action cannot interleave.
    frappe.db.get_value("SIM Card", sim.name, "name", for_update=True)
    sim.reload()
    sim.mobile_number = mobile_number
    sim.save()
    return {"mobile_number": sim.mobile_number}


@frappe.whitelist(methods=["POST"])
def move_to_contract(sim_card, telecom_contract):
    """Move a SIM to another submitted contract, syncing its company + supplier.

    The SIM controller re-validates that the SIM company matches the new contract's
    company, so a cross-company move fails closed.
    """
    if not telecom_contract or not frappe.db.exists("Telecom Contract", telecom_contract):
        frappe.throw(_("Telecom Contract {0} does not exist.").format(telecom_contract))
    sim = _load_sim(sim_card)
    sim.check_permission("write")

    target = frappe.db.get_value(
        "Telecom Contract", telecom_contract, ["company", "docstatus"], as_dict=True
    )
    if target.docstatus != 1:
        frappe.throw(_("A SIM can only move to a submitted contract."))
    # Fail closed on a cross-company move: a SIM stays within its own company so its
    # company-scoped permission never diverges from the contract it belongs to.
    if target.company != sim.company:
        frappe.throw(_("A SIM can only move to a contract within its own company."))

    frappe.db.get_value("SIM Card", sim.name, "name", for_update=True)
    sim.reload()
    sim.telecom_contract = telecom_contract
    sim.save()
    return {"telecom_contract": sim.telecom_contract, "company": sim.company}
