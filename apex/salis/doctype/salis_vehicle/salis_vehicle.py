# Copyright (c) 2026, afmcoltd
"""Salis Vehicle controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, getdate, today

from apex.salis.utils import normalize_plate

DEFAULT_ALERT_LEAD_DAYS = 30

_STATUS_RANK = {"Compliant": 0, "Expiring Soon": 1, "Expired": 2}


class SalisVehicle(Document):
    def validate(self):
        """Defaults the company, normalizes the plate, recomputes compliance, and guards the machine-owned fields."""
        self._set_company_default()
        self._set_plate_normalized()
        self._set_compliance_status()
        self._refuse_a_hand_written_pairing()
        self._refuse_a_status_edit_while_a_stop_owns_the_vehicle()

    def _refuse_a_hand_written_pairing(self):
        """``current_driver`` is half of a mirror Vehicle Assignment owns; writing it alone
        splits the pair, leaving Salis Driver's ``current_vehicle`` pointing elsewhere. It is a
        plain editable Link on a non-submittable DocType, so nothing else refuses a Desk edit or
        a ``frappe.client.set_value``; the sanctioned writers stamp both sides with
        ``frappe.db.set_value``, which runs no controller method and never reaches here."""
        if self.is_new():
            if self.current_driver:
                frappe.throw(
                    _("The current driver is set by assigning the vehicle, not by typing it here."),
                    frappe.PermissionError,
                )
            return
        if self.has_value_changed("current_driver"):
            frappe.throw(
                _("The current driver is set by assigning the vehicle, not by editing it."),
                frappe.PermissionError,
            )

    def _refuse_a_status_edit_while_a_stop_owns_the_vehicle(self):
        """Suspension and Incident ``on_submit`` write ``status`` to Stopped, and the field is
        editable on a non-submittable DocType — so a plain save puts a stopped or stolen vehicle
        back to Active while the stop has no ``return_date`` and the incident is still Open, and
        every board that offers Active vehicles for dispatch believes it. Only the interval a
        machine owns is refused; the operator keeps the field the rest of the time."""
        if self.is_new() or not self.has_value_changed("status"):
            return
        if frappe.db.exists(
            "Vehicle Suspension",
            {"vehicle": self.name, "docstatus": 1, "return_date": ["is", "not set"]},
        ):
            frappe.throw(
                _("This vehicle has an open stop. Close the stop to change its status."),
                frappe.PermissionError,
            )
        if frappe.db.exists(
            "Vehicle Incident",
            {"vehicle": self.name, "docstatus": 1, "status": ["in", ("Open", "Under Review")]},
        ):
            frappe.throw(
                _("This vehicle has an open incident. Close the incident to change its status."),
                frappe.PermissionError,
            )

    def _set_company_default(self):
        """Default the owning company from Salis Settings (asset ownership /
        reporting context). Reference field only - no GL is posted."""
        if not self.company:
            from apex.apex_core.utils.company import resolve_company

            self.company = resolve_company("Salis")

    def _set_plate_normalized(self):
        """Sets the normalized plate number from the raw plate number, or clears it when blank."""
        if self.plate_number:
            self.plate_normalized = normalize_plate(self.plate_number)
        else:
            self.plate_normalized = None

    def _set_compliance_status(self):
        """Derives the vehicle's worst compliance state and nearest expiry from its compliance rows."""
        rows = self.get("compliance_documents") or []
        if not rows:
            self.compliance_status = "Not Tracked"
            self.next_expiry_date = None
            return

        today_date = getdate(today())
        lead_days = self._get_alert_lead_days()
        soon_cutoff = add_days(today_date, lead_days)

        row_to_parent = {
            "Expired": "Expired",
            "Expiring Soon": "Expiring Soon",
            "Valid": "Compliant",
        }

        worst_rank = -1
        worst_status = "Compliant"
        future_expiries = []
        all_expiries = []

        for row in rows:
            if not row.expiry_date:
                continue
            expiry = getdate(row.expiry_date)
            all_expiries.append(expiry)
            if expiry >= today_date:
                future_expiries.append(expiry)

            if expiry < today_date:
                row.status = "Expired"
            elif expiry <= soon_cutoff:
                row.status = "Expiring Soon"
            else:
                row.status = "Valid"

            parent_status = row_to_parent[row.status]
            rank = _STATUS_RANK[parent_status]
            if rank > worst_rank:
                worst_rank = rank
                worst_status = parent_status

        if worst_rank < 0:
            self.compliance_status = "Not Tracked"
            self.next_expiry_date = None
            return

        self.compliance_status = worst_status

        if future_expiries:
            self.next_expiry_date = min(future_expiries)
        elif all_expiries:
            self.next_expiry_date = min(all_expiries)
        else:
            self.next_expiry_date = None

    @staticmethod
    def _get_alert_lead_days():
        """Returns the configured number of lead days before an expiry counts as Expiring Soon."""
        from apex.apex_core.doctype.salis_settings.salis_settings import get_salis_int

        return get_salis_int("alert_lead_days", DEFAULT_ALERT_LEAD_DAYS)
