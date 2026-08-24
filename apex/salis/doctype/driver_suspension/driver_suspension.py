# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from apex.salis.utils import add_timeline_note, lock_vehicle, lock_driver, set_current_driver
from apex.salis.utils.driver_availability import (
    dispatched_trips_for_driver,
    validate_driver_has_no_planned_trips,
)


class DriverSuspension(Document):
    def validate(self):
        validate_driver_has_no_planned_trips(self.driver)
        if self.release_vehicle and not self.related_vehicle:
            frappe.throw(_("Select the vehicle to release."))

    def before_submit(self):
        if self.stop_reason in ("Violation", "Termination") and not self.evidence:
            frappe.throw(
                _("Evidence is required to submit a stop with reason {0}.").format(_(self.stop_reason))
            )

    def on_submit(self):
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
