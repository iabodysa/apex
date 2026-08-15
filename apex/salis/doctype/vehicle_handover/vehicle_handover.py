# Copyright (c) 2026, afmcoltd
"""Vehicle Handover controller.

Transfers a vehicle from one driver to another, updating the vehicle's
current_driver mirror and odometer. The submitted Vehicle Assignment remains
the authoritative pairing; this controller only updates the denormalized mirror.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, nowtime

from apex.salis.utils import (
    add_timeline_note,
    lock_vehicle,
    raise_rider_clearance_task,
    rider_block_reason,
    set_current_driver,
)


class VehicleHandover(Document):
    def before_insert(self):
        """Default the handover time to the moment the receipt is raised.

        Two handovers of the same vehicle on the same day cannot be ordered by a date
        alone, and a receipt that states no time cannot say which one came second. The
        operator may overwrite it with the real clock time; left alone it carries the
        time the paper was raised, which is what a desk log would have written.
        """
        if not self.handover_time:
            self.handover_time = nowtime()

    def validate(self):
        """Validates the two drivers differ, the incoming rider is active, and the odometer only rises."""
        self.direction = self.direction or "Transfer"
        if self.direction == "Receipt":
            self.from_driver = None
            if not self.to_driver:
                frappe.throw(_("To Driver is required for a receipt."))
        elif self.direction == "Transfer":
            if not self.from_driver or not self.to_driver:
                frappe.throw(
                    _("From Driver and To Driver are required for a transfer.")
                )
        elif self.direction == "Return":
            self.to_driver = None
            if not self.from_driver:
                frappe.throw(_("From Driver is required for a return."))
        else:
            frappe.throw(_("Invalid handover direction."))

        self._validate_assignment_event()
        self._validate_native_checklist()
        self._derive_discrepancy()

        if self.from_driver and self.to_driver and self.from_driver == self.to_driver:
            frappe.throw(_("To Driver must differ from From Driver."))

        if self.to_driver:
            reason = rider_block_reason(self.to_driver, self.handover_date)
            if reason:
                frappe.throw(reason)

        if self.from_driver and rider_block_reason(
            self.from_driver, self.handover_date
        ):
            raise_rider_clearance_task(
                self.from_driver,
                vehicle=self.vehicle,
                source_doctype=self.doctype,
                source_name=self.name,
            )

        if self.vehicle and self.odometer_reading is not None:
            current = (
                frappe.db.get_value("Salis Vehicle", self.vehicle, "odometer") or 0
            )
            if self.odometer_reading < current:
                frappe.throw(
                    _(
                        "Odometer reading {0} cannot be lower than the vehicle's current {1}."
                    ).format(self.odometer_reading, current)
                )

    def _validate_native_checklist(self):
        """Require exact active native-template parity for receipts and returns."""
        if self.direction not in ("Receipt", "Return"):
            return
        if not self.checklist_template:
            frappe.throw(_("Select a handover checklist before saving."))

        template = frappe.get_doc(
            "Vehicle Handover Checklist Template", self.checklist_template
        )
        if not template.is_active:
            frappe.throw(
                _("Checklist template {0} is not active.").format(template.name)
            )
        vehicle_category = frappe.db.get_value(
            "Salis Vehicle", self.vehicle, "vehicle_category"
        )
        if template.vehicle_category and template.vehicle_category != vehicle_category:
            frappe.throw(
                _("Checklist template {0} does not apply to this vehicle.").format(
                    template.name
                )
            )

        expected = [row.check_item for row in template.items]
        actual = [row.check_item for row in (self.handover_check_items or [])]
        if not expected or actual != expected:
            frappe.throw(
                _("Handover checklist rows must exactly match the selected template.")
            )
        for row in self.handover_check_items:
            if not row.ok and not (row.remark or "").strip():
                frappe.throw(_("Explain the failed check: {0}.").format(row.check_item))

    def _derive_discrepancy(self):
        """Derive the receipt state from the native checklist; never trust a caller."""
        if self.direction not in ("Receipt", "Return"):
            return
        failed = [row for row in (self.handover_check_items or []) if not row.ok]
        self.discrepancy_status = "Discrepancy" if failed else "Clean"
        self.discrepancy_notes = (
            "; ".join(
                f"{row.check_item}: {(row.remark or '').strip()}" for row in failed
            )
            or None
        )

    def _validate_assignment_event(self):
        """Serialize one receipt and one return against the exact assignment."""
        if self.direction not in ("Receipt", "Return"):
            return None
        if not self.vehicle_assignment:
            frappe.throw(_("Vehicle Assignment is required for receipts and returns."))

        assignment = frappe.get_doc(
            "Vehicle Assignment", self.vehicle_assignment, for_update=True
        )
        duplicate = frappe.db.get_value(
            "Vehicle Handover",
            {
                "vehicle_assignment": assignment.name,
                "direction": self.direction,
                "docstatus": 1,
                "name": ["!=", getattr(self, "name", None) or ""],
            },
            "name",
        )
        if duplicate:
            frappe.throw(
                _("Assignment {0} already has a submitted {1} handover {2}.").format(
                    assignment.name, self.direction, duplicate
                )
            )
        if assignment.docstatus != 1 or assignment.status != "Active":
            frappe.throw(
                _("Vehicle Assignment {0} must be submitted and Active.").format(
                    assignment.name
                )
            )
        if assignment.vehicle != self.vehicle:
            frappe.throw(
                _("Vehicle Assignment {0} is for a different vehicle.").format(
                    assignment.name
                )
            )
        event_driver = (
            self.to_driver if self.direction == "Receipt" else self.from_driver
        )
        if assignment.driver != event_driver:
            frappe.throw(
                _("Vehicle Assignment {0} is for a different driver.").format(
                    assignment.name
                )
            )
        return assignment

    def before_submit(self):
        """Requires signed evidence, and discrepancy notes when a discrepancy is recorded."""
        self._validate_assignment_event()
        if not self.signed_evidence:
            frappe.throw(_("Signed handover evidence is required before submitting."))

        self._validate_native_checklist()
        self._derive_discrepancy()

        if self.discrepancy_status == "Discrepancy" and not self.discrepancy_notes:
            frappe.throw(
                _(
                    "Discrepancy notes are required when the discrepancy status is Discrepancy."
                )
            )

    def on_submit(self):
        """Moves the vehicle's current driver and odometer to the new driver and reading."""
        lock_vehicle(self.vehicle)

        set_current_driver(self.vehicle, self.to_driver, odometer=self.odometer_reading)

        if self.from_driver and (
            frappe.db.get_value("Salis Driver", self.from_driver, "current_vehicle")
            == self.vehicle
        ):
            frappe.db.set_value(
                "Salis Driver", self.from_driver, "current_vehicle", None
            )

        if self.to_driver:
            frappe.db.set_value(
                "Salis Driver", self.to_driver, "current_vehicle", self.vehicle
            )

        if self.direction == "Return":
            frappe.db.set_value(
                "Vehicle Assignment",
                self.vehicle_assignment,
                {"status": "Ended", "end_date": self.handover_date},
            )

        self.add_comment(
            "Comment",
            _("Vehicle {0} custody recorded as {1}.").format(
                self.vehicle, _(self.direction)
            ),
        )

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
        """Restore mirrors from the assignment that remains authoritative."""
        lock_vehicle(self.vehicle)

        active_receipt_assignment = None
        if self.direction == "Receipt" and self.vehicle_assignment:
            assignment = frappe.get_doc(
                "Vehicle Assignment",
                self.vehicle_assignment,
                for_update=True,
            )
            if (
                assignment.docstatus == 1
                and assignment.status == "Active"
                and assignment.vehicle == self.vehicle
                and assignment.driver
            ):
                active_receipt_assignment = assignment

        if active_receipt_assignment:
            set_current_driver(self.vehicle, active_receipt_assignment.driver)
            frappe.db.set_value(
                "Salis Driver",
                active_receipt_assignment.driver,
                "current_vehicle",
                self.vehicle,
            )
        elif (
            frappe.db.get_value("Salis Vehicle", self.vehicle, "current_driver")
            == self.to_driver
        ):
            set_current_driver(self.vehicle, self.from_driver)

            if self.to_driver and (
                frappe.db.get_value("Salis Driver", self.to_driver, "current_vehicle")
                == self.vehicle
            ):
                frappe.db.set_value(
                    "Salis Driver", self.to_driver, "current_vehicle", None
                )
            if self.from_driver:
                frappe.db.set_value(
                    "Salis Driver", self.from_driver, "current_vehicle", self.vehicle
                )

                if self.direction == "Return" and self.vehicle_assignment:
                    assignment = frappe.get_doc(
                        "Vehicle Assignment",
                        self.vehicle_assignment,
                        for_update=True,
                    )
                    active_pairing = frappe.db.exists(
                        "Vehicle Assignment",
                        {
                            "docstatus": 1,
                            "status": "Active",
                            "name": ["!=", assignment.name],
                            "vehicle": self.vehicle,
                        },
                    ) or frappe.db.exists(
                        "Vehicle Assignment",
                        {
                            "docstatus": 1,
                            "status": "Active",
                            "name": ["!=", assignment.name],
                            "driver": assignment.driver,
                        },
                    )
                    if (
                        assignment.docstatus == 1
                        and assignment.status == "Ended"
                        and assignment.end_date
                        and getdate(assignment.end_date) == getdate(self.handover_date)
                        and not active_pairing
                    ):
                        frappe.db.set_value(
                            "Vehicle Assignment",
                            assignment.name,
                            {"status": "Active", "end_date": None},
                        )

        add_timeline_note(
            "Salis Vehicle",
            self.vehicle,
            _("Handover {0} cancelled.").format(self.name),
        )
