"""Vehicle Stop controller.

Stops a vehicle, capturing its prior status into previous_status so the effect
can be reliably reversed on cancel.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from apex_habitat.salis.utils import add_timeline_note, lock_vehicle


class VehicleStop(Document):
    def validate(self):
        if self.vehicle and not self.ownership_at_stop:
            self.ownership_at_stop = frappe.db.get_value("Salis Vehicle", self.vehicle, "ownership")

    def before_submit(self):
        # [#ku7cqs]
        if self.stop_reason in ("Accident", "Violation") and not self.evidence:
            frappe.throw(
                _("Evidence is required to submit a stop with reason {0}.").format(_(self.stop_reason))
            )

    def on_submit(self):
        lock_vehicle(self.vehicle)

        # [#bp5wlg]
        self.db_set("previous_status", frappe.db.get_value("Salis Vehicle", self.vehicle, "status"))

        frappe.db.set_value("Salis Vehicle", self.vehicle, "status", "Stopped")

        self.add_comment("Comment", _("Vehicle {0} stopped: {1}.").format(self.vehicle, self.stop_reason))
        add_timeline_note(
            "Salis Vehicle",
            self.vehicle,
            _("Stopped via {0}: {1}.").format(self.name, _(self.stop_reason)),
        )

    def on_cancel(self):
        lock_vehicle(self.vehicle)

        # [#r0a24i]
        # [#iodhu1]
        # [#r47amw]
        # [#cn2wtu]
        # [#d0gbu0]
        another_stop_in_force = frappe.db.exists(
            "Vehicle Stop",
            {"vehicle": self.vehicle, "docstatus": 1, "name": ["!=", self.name]},
        )
        if (
            not another_stop_in_force
            and frappe.db.get_value("Salis Vehicle", self.vehicle, "status") == "Stopped"
        ):
            restore = self.previous_status or "Active"
            frappe.db.set_value("Salis Vehicle", self.vehicle, "status", restore)

        add_timeline_note(
            "Salis Vehicle",
            self.vehicle,
            _("Stop {0} cancelled.").format(self.name),
        )
