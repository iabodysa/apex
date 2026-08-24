# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, fmt_money, now_datetime

from apex.apex_core.doctype.salis_settings.salis_settings import get_salis_float
from apex.apex_core.utils.company import display_currency

from apex.salis.utils import add_timeline_note

_OPERATIONS_ROLES = {"Fleet Manager", "System Manager"}


class VehicleDamageWriteOff(Document):
    def validate(self):
        if self.status and self.status != "Open" and not self.evidence:
            frappe.throw(_("Evidence is required before moving the write-off case beyond Open."))
        if self.estimated_cost is not None and flt(self.estimated_cost) < 0:
            frappe.throw(_("Estimated cost cannot be negative."))
        self._derive_needs_operations()
        self._enforce_doa_gate()
        self._stamp_approver()

    def _derive_needs_operations(self):
        threshold = get_salis_float("writeoff_ops_threshold", 2000.0)
        self.needs_operations = 1 if flt(self.estimated_cost) >= threshold else 0

    def _enforce_doa_gate(self):
        if self.status != "Approved" or not self.needs_operations:
            return
        if not (_OPERATIONS_ROLES & set(frappe.get_roles())):
            frappe.throw(
                _(
                    "This write-off reaches the Operations threshold and can only be approved by Operations-tier authority (Fleet Manager)."
                )
            )

    def on_submit(self):
        self._stamp_source_incident()
        add_timeline_note(
            "Salis Vehicle",
            self.vehicle,
            _("Damage write-off {0} submitted (estimated {1}).").format(
                self.name,
                fmt_money(self.estimated_cost, currency=display_currency("Salis")),
            ),
        )

    def on_cancel(self):
        self._clear_source_incident()
        add_timeline_note(
            "Salis Vehicle",
            self.vehicle,
            _("Damage write-off {0} cancelled.").format(self.name),
        )


    def _stamp_approver(self):
        if self.status in ("Approved", "Closed"):
            if not self.approved_by:
                self.approved_by = frappe.session.user
            if not self.approved_on:
                self.approved_on = now_datetime()
            return
        self.approved_by = None
        self.approved_on = None

    def _stamp_source_incident(self):
        if self.source_incident:
            frappe.db.set_value(
                "Vehicle Incident", self.source_incident, "write_off_case", self.name
            )

    def _clear_source_incident(self):
        if self.source_incident:
            frappe.db.set_value(
                "Vehicle Incident", self.source_incident, "write_off_case", None
            )
