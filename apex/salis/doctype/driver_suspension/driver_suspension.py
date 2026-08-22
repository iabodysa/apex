# Copyright (c) 2026, afmcoltd
"""Driver Suspension controller.

Stops a driver, optionally releasing the linked vehicle. Prior driver status is
captured into previous_status for a reliable revert on cancel.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from apex.salis.utils import add_timeline_note, lock_vehicle, lock_driver, set_current_driver
from apex.salis.utils.driver_availability import (
    dispatched_trips_for_driver,
    refuse_to_stop_a_driver_who_still_holds_planned_trips,
)


class DriverSuspension(Document):
    def validate(self):
        """Requires a vehicle to release, and a driver whose planned trips are handed over.

        The trip check runs here rather than on submit so the operator is told while
        he is still filling the form, not after he has asked for the stop to take effect.
        """
        refuse_to_stop_a_driver_who_still_holds_planned_trips(self.driver)
        if self.release_vehicle and not self.related_vehicle:
            frappe.throw(_("Select the vehicle to release."))

    def before_submit(self):
        """Requires evidence before a stop for Violation or Termination can be submitted."""
        if self.stop_reason in ("Violation", "Termination") and not self.evidence:
            frappe.throw(
                _("Evidence is required to submit a stop with reason {0}.").format(_(self.stop_reason))
            )

    def on_submit(self):
        """Stops the driver, records their prior status, and releases the vehicle when requested."""
        lock_driver(self.driver)

        self.db_set("previous_status", frappe.db.get_value("Salis Driver", self.driver, "status"))

        frappe.db.set_value("Salis Driver", self.driver, "status", "Stopped")

        if self.release_vehicle and self.related_vehicle:
            lock_vehicle(self.related_vehicle)
            set_current_driver(self.related_vehicle, None, status="Released")
            if frappe.db.get_value("Salis Driver", self.driver, "current_vehicle") == self.related_vehicle:
                frappe.db.set_value("Salis Driver", self.driver, "current_vehicle", None)

        self.add_comment("Comment", _("Driver {0} stopped: {1}.").format(self.driver, self.stop_reason))
        add_timeline_note(
            "Salis Driver",
            self.driver,
            _("Stopped via {0}: {1}.").format(self.name, _(self.stop_reason)),
        )
        self._report_any_trip_he_is_still_running()

    def _report_any_trip_he_is_still_running(self):
        """Name the trips already on the road, which a stop does not and cannot recall.

        A planned trip refuses the stop; a dispatched one is a vehicle in motion, and
        an accident cannot wait for it to finish. The supervisor is told instead.
        """
        running = dispatched_trips_for_driver(self.driver)
        if not running:
            return
        self.add_comment(
            "Comment",
            _("Still on the road at the time of the stop: {0}. Recall or close each one.").format(
                ", ".join(running)
            ),
        )

    def on_cancel(self):
        """Restores the driver's prior status and re-links the released vehicle if it is still free."""
        lock_driver(self.driver)

        another_stop_in_force = frappe.db.exists(
            "Driver Suspension",
            {"driver": self.driver, "docstatus": 1, "name": ["!=", self.name]},
        )
        if (
            not another_stop_in_force
            and frappe.db.get_value("Salis Driver", self.driver, "status") == "Stopped"
        ):
            restore = self.previous_status or "Active"
            frappe.db.set_value("Salis Driver", self.driver, "status", restore)

        if self.release_vehicle and self.related_vehicle:
            lock_vehicle(self.related_vehicle)
            current_driver = frappe.db.get_value("Salis Vehicle", self.related_vehicle, "current_driver")
            if (
                frappe.db.get_value("Salis Vehicle", self.related_vehicle, "status") == "Released"
                and not current_driver
            ):
                set_current_driver(self.related_vehicle, self.driver, status="Active")
                frappe.db.set_value(
                    "Salis Driver", self.driver, "current_vehicle", self.related_vehicle
                )
            else:
                self.add_comment(
                    "Comment",
                    _("Vehicle {0} was not re-linked on cancel; it is no longer free.").format(
                        self.related_vehicle
                    ),
                )

        add_timeline_note(
            "Salis Driver",
            self.driver,
            _("Stop {0} cancelled.").format(self.name),
        )
