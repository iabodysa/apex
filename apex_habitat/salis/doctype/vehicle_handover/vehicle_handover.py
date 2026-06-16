"""Vehicle Handover controller.

Transfers a vehicle from one driver to another, updating the vehicle's
current_driver mirror and odometer. The submitted Vehicle Assignment remains
the authoritative pairing; this controller only updates the denormalized mirror.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from apex_habitat.salis.utils import (
    add_timeline_note,
    lock_vehicle,
    raise_rider_clearance_task,
    rider_block_reason,
)


class VehicleHandover(Document):
    def validate(self):
        if self.from_driver and self.to_driver and self.from_driver == self.to_driver:
            frappe.throw(_("To Driver must differ from From Driver."))

        # [#o0rvu8]
        if self.to_driver:
            reason = rider_block_reason(self.to_driver, self.handover_date)
            if reason:
                frappe.throw(reason)

        # [#bvq76e]
        # [#skw0ub]
        # [#nk1brb]
        if self.from_driver and rider_block_reason(self.from_driver, self.handover_date):
            raise_rider_clearance_task(
                self.from_driver,
                vehicle=self.vehicle,
                source_doctype=self.doctype,
                source_name=self.name,
            )

        if self.vehicle and self.odometer_reading is not None:
            current = frappe.db.get_value("Salis Vehicle", self.vehicle, "odometer") or 0
            if self.odometer_reading < current:
                frappe.throw(
                    _("Odometer reading {0} cannot be lower than the vehicle's current {1}.").format(
                        self.odometer_reading, current
                    )
                )

    def before_submit(self):
        if not self.signed_evidence:
            frappe.throw(_("Signed handover evidence is required before submitting."))

        if self.discrepancy_status == "Discrepancy" and not self.discrepancy_notes:
            frappe.throw(_("Discrepancy notes are required when the discrepancy status is Discrepancy."))

    def on_submit(self):
        lock_vehicle(self.vehicle)

        frappe.db.set_value(
            "Salis Vehicle",
            self.vehicle,
            {"current_driver": self.to_driver, "odometer": self.odometer_reading},
        )

        # [#d74yu0]
        if self.from_driver and (
            frappe.db.get_value("Salis Driver", self.from_driver, "current_vehicle") == self.vehicle
        ):
            frappe.db.set_value("Salis Driver", self.from_driver, "current_vehicle", None)

        if self.to_driver:
            frappe.db.set_value("Salis Driver", self.to_driver, "current_vehicle", self.vehicle)

        self.add_comment(
            "Comment",
            _("Vehicle {0} handed over to driver {1}.").format(self.vehicle, self.to_driver),
        )

        # [#ph347s]
        # [#pstlcl]
        if self.discrepancy_status == "Discrepancy":
            self.add_comment(
                "Comment",
                _(
                    "A handover discrepancy was recorded. Please raise a Vehicle Damage "
                    "Write-Off for vehicle {0} to obtain tiered write-off approval."
                ).format(self.vehicle),
            )

        add_timeline_note(
            "Salis Vehicle",
            self.vehicle,
            _("Handed over from {0} to {1} via {2} (odometer {3}).").format(
                self.from_driver or _("n/a"),
                self.to_driver or _("n/a"),
                self.name,
                self.odometer_reading,
            ),
        )

    def on_cancel(self):
        lock_vehicle(self.vehicle)

        # [#1com2f]
        # [#swwkt7]
        if frappe.db.get_value("Salis Vehicle", self.vehicle, "current_driver") == self.to_driver:
            frappe.db.set_value("Salis Vehicle", self.vehicle, "current_driver", self.from_driver)

            # [#bz5szf]
            if self.to_driver and (
                frappe.db.get_value("Salis Driver", self.to_driver, "current_vehicle") == self.vehicle
            ):
                frappe.db.set_value("Salis Driver", self.to_driver, "current_vehicle", None)
            if self.from_driver:
                frappe.db.set_value("Salis Driver", self.from_driver, "current_vehicle", self.vehicle)

        add_timeline_note(
            "Salis Vehicle",
            self.vehicle,
            _("Handover {0} cancelled.").format(self.name),
        )
