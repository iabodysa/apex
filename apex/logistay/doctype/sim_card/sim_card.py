# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from apex.logistay.utils.normalize import normalize_iccid, normalize_msisdn

_PROJECTION_FIELDS = (
    "status",
    "current_custodian_type",
    "current_custodian_employee",
    "current_project",
    "current_cost_center",
    "current_assignment",
    "assigned_on",
)


class SIMCard(Document):
    def validate(self):
        self._normalize_identifiers()
        self._enforce_contract_binding()
        self._enforce_unique_mobile()
        self._enforce_unique_iccid()

    def _normalize_identifiers(self):
        self.mobile_number_normalized = normalize_msisdn(self.mobile_number)
        if not self.mobile_number_normalized:
            frappe.throw(_("Mobile Number must contain at least one digit."))
        self.iccid_normalized = normalize_iccid(self.iccid)

    def _enforce_contract_binding(self):
        if not self.telecom_contract:
            return
        contract = frappe.db.get_value(
            "Telecom Contract", self.telecom_contract, ["company", "docstatus"], as_dict=True
        )
        if not contract or contract.docstatus != 1:
            frappe.throw(
                _("Telecom Contract {0} is not submitted, so no SIM can be attached to it.").format(
                    self.telecom_contract
                )
            )
        if contract.company and self.company != contract.company:
            frappe.throw(
                _("SIM company {0} must match its contract's company {1}.").format(
                    self.company, contract.company
                )
            )

    def _enforce_unique_mobile(self):
        clash = frappe.db.get_value(
            "SIM Card",
            {
                "mobile_number_normalized": self.mobile_number_normalized,
                "name": ["!=", self.name or ""],
            },
        )
        if clash:
            frappe.throw(
                _("Mobile number {0} is already registered on SIM {1}.").format(
                    self.mobile_number, clash
                )
            )

    def _enforce_unique_iccid(self):
        if not self.iccid_normalized:
            return
        clash = frappe.db.get_value(
            "SIM Card",
            {
                "iccid_normalized": self.iccid_normalized,
                "name": ["!=", self.name or ""],
            },
        )
        if clash:
            frappe.throw(
                _("ICCID {0} is already registered on SIM {1}.").format(self.iccid, clash)
            )

    def after_insert(self):
        self._refresh_contract_counts()

    def on_update(self):
        self._refresh_contract_counts()

    def after_delete(self):
        self._refresh_contract_counts()

    def _refresh_contract_counts(self):
        from apex.logistay.doctype.telecom_contract.telecom_contract import (
            refresh_sim_count,
        )

        refresh_sim_count(self.telecom_contract)
        before = self.get_doc_before_save()
        if before and before.telecom_contract and before.telecom_contract != self.telecom_contract:
            refresh_sim_count(before.telecom_contract)


def set_projection(sim_card: str, **fields) -> None:
    payload = {k: fields.get(k) for k in _PROJECTION_FIELDS if k in fields}
    if payload:
        frappe.db.set_value("SIM Card", sim_card, payload)
