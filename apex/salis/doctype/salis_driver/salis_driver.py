# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, today


class SalisDriver(Document):
    def validate(self):
        self._refuse_a_hand_written_status()
        self._refuse_a_hand_written_pairing()
        if self.license_expiry and getdate(self.license_expiry) < getdate(today()):
            frappe.msgprint(
                _("Driver license expired on {0}.").format(self.license_expiry),
                indicator="orange",
                title=_("License Expired"),
            )

    def _refuse_a_hand_written_status(self):
        if self.is_new():
            self.status = "Active"
            return
        if self.has_value_changed("status"):
            frappe.throw(
                _("Driver status is set by suspension and clearance records, not by editing it."),
                frappe.PermissionError,
            )

    def _refuse_a_hand_written_pairing(self):
        if self.is_new():
            if self.current_vehicle:
                frappe.throw(
                    _("The current vehicle is set by assigning the driver, not by typing it here."),
                    frappe.PermissionError,
                )
            return
        if self.has_value_changed("current_vehicle"):
            frappe.throw(
                _("The current vehicle is set by assigning the driver, not by editing it."),
                frappe.PermissionError,
            )
