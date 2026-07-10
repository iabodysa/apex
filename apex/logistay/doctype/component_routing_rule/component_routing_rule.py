# Copyright (c) 2026, AFMCO and contributors
"""Component Routing Rule controller - the D8 four-way split as data, not code.

Guards the two structural invariants of the split so the ``present_set_targets``
assembler can trust the rows: fee riders (gosi_fee / charge_fee) must ride on the
main timesheet document, and the eos component may only route to the
eos-on-transfer document (event-triggered).
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

_RIDER_COMPONENTS = {"gosi_fee", "charge_fee"}


class ComponentRoutingRule(Document):
    def validate(self) -> None:
        self._guard_rider_consistency()

    def _guard_rider_consistency(self) -> None:
        if self.inv_component in _RIDER_COMPONENTS and self.inv_rides_on != "main_timesheet":
            frappe.throw(
                _("{0} must ride on the main timesheet document.").format(self.inv_component)
            )
        if self.inv_component == "eos" and self.inv_target_document != "eos_on_transfer":
            frappe.throw(_("The eos component routes only to the eos-on-transfer document."))
