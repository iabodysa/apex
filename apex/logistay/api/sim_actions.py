# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import today

from apex.logistay.utils.normalize import normalize_msisdn

_VALID_ACTIONS = (
    "Assign",
    "Transfer",
    "Return",
    "Suspend",
    "Reactivate",
    "Lost",
    "Terminated",
)


def _load_sim(sim_card):
    if not sim_card or not frappe.db.exists("SIM Card", {"name": sim_card}):
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
    if action not in _VALID_ACTIONS:
        frappe.throw(_("Unknown custody action: {0}").format(action))
    sim = _load_sim(sim_card)
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
    if not mobile_number or not normalize_msisdn(mobile_number):
        frappe.throw(_("Enter a valid mobile number."))
    sim = _load_sim(sim_card)
    sim.check_permission("write")
    frappe.db.get_value("SIM Card", sim.name, "name", for_update=True)
    sim.reload()
    sim.mobile_number = mobile_number
    sim.save()
    return {"mobile_number": sim.mobile_number}


@frappe.whitelist(methods=["POST"])
def move_to_contract(sim_card, telecom_contract):
    if not telecom_contract or not frappe.db.exists("Telecom Contract", {"name": telecom_contract}):
        frappe.throw(_("Telecom Contract {0} does not exist.").format(telecom_contract))
    sim = _load_sim(sim_card)
    sim.check_permission("write")

    target = frappe.db.get_value(
        "Telecom Contract", telecom_contract, ["company", "docstatus"], as_dict=True
    )
    if target.docstatus != 1:
        frappe.throw(_("A SIM can only move to a submitted contract."))
    if target.company != sim.company:
        frappe.throw(_("A SIM can only move to a contract within its own company."))

    frappe.db.get_value("SIM Card", sim.name, "name", for_update=True)
    sim.reload()
    sim.telecom_contract = telecom_contract
    sim.save()
    return {"telecom_contract": sim.telecom_contract, "company": sim.company}
