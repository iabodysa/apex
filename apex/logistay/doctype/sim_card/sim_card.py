# Copyright (c) 2026, afmcoltd
"""SIM Card controller.

The mobile number is human-editable, so uniqueness is enforced on a derived,
normalized key (``mobile_number_normalized``) rather than the display string.
ICCID follows the same rule but only when present. Custody state
(``status`` / ``current_*``) is a read-only projection written by the SIM Custody
Assignment engine via :func:`set_projection`; nothing here sets it directly.
"""

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
        """Normalizes identifiers, binds the SIM to an in-force contract of its own company, and enforces unique mobile and ICCID."""
        self._normalize_identifiers()
        self._enforce_contract_binding()
        self._enforce_unique_mobile()
        self._enforce_unique_iccid()

    def _normalize_identifiers(self):
        """Derives the normalized mobile number and ICCID keys used for uniqueness checks."""
        self.mobile_number_normalized = normalize_msisdn(self.mobile_number)
        if not self.mobile_number_normalized:
            frappe.throw(_("Mobile Number must contain at least one digit."))
        self.iccid_normalized = normalize_iccid(self.iccid)

    def _enforce_contract_binding(self):
        """A SIM may only hang off an IN-FORCE contract, and must share its company.

        The company rule keeps the company-scoped permission on the SIM from ever
        diverging from the contract it belongs to. The docstatus rule is the same
        fail-closed idea in time rather than scope: ``status`` is derived, not a gate,
        so nothing else on the server stops a REST insert naming a Draft contract or a
        save that leaves the SIM hanging off one already cancelled. Both read from the
        one row fetch.
        """
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
        """Blocks saving when another SIM Card already holds the same normalized mobile number."""
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
        """Blocks saving when another SIM Card already holds the same normalized ICCID."""
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
        """Refreshes the linked telecom contract's SIM count after a new SIM Card is inserted."""
        self._refresh_contract_counts()

    def on_update(self):
        """Refreshes the current and, on a contract move, the previous contract's SIM count."""
        self._refresh_contract_counts()

    def after_delete(self):
        """Refreshes the linked telecom contract's SIM count after the SIM Card is deleted.

        ``after_delete``, not ``on_trash``: Frappe runs on_trash BEFORE the row leaves the
        table (frappe/model/delete_doc.py:126 then :145), so a recount taken there still
        counts the SIM being deleted and the contract keeps a count one too high forever.
        """
        self._refresh_contract_counts()

    def _refresh_contract_counts(self):
        """Keep both the current and (on a move) the previous contract's SIM count
        in sync with reality."""
        from apex.logistay.doctype.telecom_contract.telecom_contract import (
            refresh_sim_count,
        )

        refresh_sim_count(self.telecom_contract)
        before = self.get_doc_before_save()
        if before and before.telecom_contract and before.telecom_contract != self.telecom_contract:
            refresh_sim_count(before.telecom_contract)


def set_projection(sim_card: str, **fields) -> None:
    """Write the custody projection onto a SIM Card in one guarded db_set.

    Only the projection fields are touched, and ``update_modified`` is kept so the
    SIM's timeline reflects the custody change. Called exclusively by the SIM
    Custody Assignment engine, which already holds the SIM row lock.
    """
    payload = {k: fields.get(k) for k in _PROJECTION_FIELDS if k in fields}
    if payload:
        frappe.db.set_value("SIM Card", sim_card, payload)
