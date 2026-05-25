"""Salis Driver master controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, today


class SalisDriver(Document):
    # NOTE: current_vehicle mirrors Vehicle.current_driver for quick reference only.
    # Vehicle Assignment is the authoritative source of the driver<->vehicle pairing.
    def validate(self):
        if self.license_expiry and getdate(self.license_expiry) < getdate(today()):
            frappe.msgprint(
                _("Driver license expired on {0}.").format(self.license_expiry),
                indicator="orange",
                title=_("License Expired"),
            )
