# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, nowdate

from apex.salis.fuel_engine import reverse_fuel_ledger
from apex.salis.utils import (
    add_timeline_note,
    lock_fuel_quota,
    lock_vehicle,
    rider_block_reason,
)

REQUEST_TYPES = ("Standard", "Top-up", "Chip")

VALID_STATUSES = ("Pending", "Approved", "Done", "Failed", "Reverted", "Cancelled")


class FuelRequest(Document):

    def validate(self):
        if self.request_type not in REQUEST_TYPES:
            frappe.throw(_("Invalid Request Type: {0}").format(self.request_type))

        if self.status and self.status not in VALID_STATUSES:
            frappe.throw(_("Invalid status: {0}").format(self.status))
        if not self.requested_by:
            self.requested_by = frappe.session.user

        if self.request_type == "Standard":
            self._validate_standard()
        elif self.request_type == "Top-up":
            self._validate_topup()
        elif self.request_type == "Chip":
            self._validate_chip()

        self._enforce_rider_active()
        self._guard_initial_status()
        self._stamp_approver()

    def _enforce_rider_active(self):
        if not self.driver:
            return
        reason = rider_block_reason(self.driver, self.request_date)
        if reason:
            frappe.enqueue(
                "apex.salis.utils.raise_rider_clearance_task",
                driver=self.driver,
                vehicle=self.vehicle,
            )
            frappe.throw(reason)

    def before_submit(self):
        if self.request_type == "Standard":
            self._guard_quota_allowance()
        elif self.request_type == "Chip":
            self._guard_chip_cancellation()

    def on_submit(self):
        if self.request_type == "Standard":
            if self.status == "Done":
                self._apply_quota_consumption()
        elif self.request_type == "Top-up":
            if self.status in ("Approved", "Done"):
                self._apply_topup()
            add_timeline_note(
                "Salis Vehicle",
                self.vehicle,
                _("Fuel top-up {0}: {1} L{2}.").format(
                    self.name,
                    self.topup_litres,
                    _(" (temporary)") if self.is_temporary else "",
                ),
            )
        elif self.request_type == "Chip":
            add_timeline_note(
                "Salis Vehicle",
                self.vehicle,
                _("Fuel chip {0} via request {1} (chip {2}).").format(
                    _(self.action), self.name, self.chip_number or _("n/a")
                ),
            )

    def on_update_after_submit(self):
        if self.request_type == "Standard" and self.status == "Done":
            self._apply_quota_consumption()
        elif self.request_type == "Top-up":
            if self.status in ("Approved", "Done"):
                self._apply_topup()
            elif self.status in ("Reverted", "Cancelled"):
                self._reverse_topup()

    def on_cancel(self):
        if self.request_type == "Standard":
            self._reverse_quota_consumption()
        elif self.request_type == "Top-up":
            self._reverse_topup()
            add_timeline_note(
                "Salis Vehicle",
                self.vehicle,
                _("Fuel top-up {0} cancelled ({1} L).").format(
                    self.name, self.topup_litres
                ),
            )

        reverse_fuel_ledger("Fuel Request", self.name)


    def _validate_standard(self):
        if (self.requested_litres or 0) <= 0:
            frappe.throw(_("Requested Litres must be greater than zero."))

    def _validate_topup(self):
        if (self.topup_litres or 0) <= 0:
            frappe.throw(_("Top-up Litres must be greater than zero."))
        if not self.fuel_quota:
            frappe.throw(_("A Top-up request requires an active Fuel Quota."))
        if self.is_temporary and not self.revert_due_date:
            frappe.throw(_("A temporary top-up requires a revert due date."))
        self._warn_overdue_temporary()

    def _validate_chip(self):
        if not self.action:
            frappe.throw(_("A chip action (Issue / Replace / Cancel) is required."))
        if self.action in ("Replace", "Cancel") and not self.chip_number:
            frappe.throw(
                _("A chip number is required to {0} a fuel chip.").format(_(self.action))
            )


    def _guard_initial_status(self):
        if self.is_new() and self.status and self.status != "Pending":
            frappe.throw(
                _("A Fuel Request must be created with status Pending; {0} is reached through the workflow.").format(
                    _(self.status)
                )
            )

    def _stamp_approver(self):
        if self.status == "Approved" and not self.approved_by:
            self.approved_by = frappe.session.user


    def _warn_overdue_temporary(self):
        if not self.is_temporary or self.reverted:
            return
        if self.revert_due_date and getdate(self.revert_due_date) < getdate(nowdate()):
            frappe.msgprint(
                _(
                    "This temporary top-up is past its revert due date ({0}) and has not been reverted."
                ).format(self.revert_due_date),
                indicator="red",
                title=_("Temporary Top-up Not Reverted"),
            )


    def _guard_chip_cancellation(self):
        if self.action == "Cancel":
            if not self.inactivity_evidence:
                frappe.throw(
                    _("Inactivity evidence is required to submit a fuel chip cancellation.")
                )
            if not self.owner_acknowledged:
                frappe.throw(
                    _("Owner acknowledgement is required to submit a fuel chip cancellation.")
                )


    def _guard_quota_allowance(self, quota=None):
        if not self.fuel_quota:
            return
        if quota is None:
            quota = frappe.db.get_value(
                "Fuel Quota",
                self.fuel_quota,
                ["consumed_litres", "monthly_litres", "status"],
                as_dict=True,
            )
        if not quota:
            return
        monthly = flt(quota.monthly_litres)
        consumed = flt(quota.consumed_litres)
        if quota.status == "Exhausted" or (monthly and consumed >= monthly):
            frappe.throw(
                _(
                    "Fuel Quota {0} is exhausted ({1} of {2} L already consumed). "
                    "Raise a Top-up request to dispense more fuel this period."
                ).format(self.fuel_quota, consumed, monthly)
            )
        requested = flt(self.requested_litres)
        if monthly and consumed + requested > monthly:
            frappe.throw(
                _(
                    "This request of {0} L exceeds the {1} L left on Fuel Quota {2} "
                    "({3} of {4} L already consumed). Reduce the request, or raise a "
                    "Top-up request to dispense more fuel this period."
                ).format(requested, monthly - consumed, self.fuel_quota, consumed, monthly)
            )

    def _apply_quota_consumption(self):
        if self.quota_applied or not self.fuel_quota:
            return

        lock_vehicle(self.vehicle)
        lock_fuel_quota(self.fuel_quota)

        quota = frappe.db.get_value(
            "Fuel Quota", self.fuel_quota, ["consumed_litres", "monthly_litres", "status"], as_dict=True
        )
        if not quota:
            return

        self._guard_quota_allowance(quota)

        new_consumed = (quota.consumed_litres or 0) + (self.requested_litres or 0)
        updates = {"consumed_litres": new_consumed}
        monthly = quota.monthly_litres or 0
        if monthly and new_consumed >= monthly and quota.status == "Active":
            updates["status"] = "Exhausted"
        frappe.db.set_value("Fuel Quota", self.fuel_quota, updates)

        self.db_set("quota_applied", 1)
        add_timeline_note(
            "Fuel Quota",
            self.fuel_quota,
            _("Consumed {0} L via Fuel Request {1}.").format(
                self.requested_litres, self.name
            ),
        )

    def _reverse_quota_consumption(self):
        if not self.quota_applied or not self.fuel_quota:
            return

        lock_vehicle(self.vehicle)
        lock_fuel_quota(self.fuel_quota)

        quota = frappe.db.get_value(
            "Fuel Quota", self.fuel_quota, ["consumed_litres", "monthly_litres", "status"], as_dict=True
        )
        if quota:
            new_consumed = max((quota.consumed_litres or 0) - (self.requested_litres or 0), 0)
            updates = {"consumed_litres": new_consumed}
            monthly = quota.monthly_litres or 0
            if quota.status == "Exhausted" and (not monthly or new_consumed < monthly):
                updates["status"] = "Active"
            frappe.db.set_value("Fuel Quota", self.fuel_quota, updates)

        self.db_set("quota_applied", 0)
        add_timeline_note(
            "Fuel Quota",
            self.fuel_quota,
            _("Reversed {0} L from Fuel Request {1}.").format(
                self.requested_litres, self.name
            ),
        )

    def _apply_topup(self):
        if self.topup_applied or not self.fuel_quota:
            return
        lock_fuel_quota(self.fuel_quota)
        quota = frappe.db.get_value(
            "Fuel Quota", self.fuel_quota, ["monthly_litres", "status"], as_dict=True
        )
        if not quota:
            return
        frappe.db.set_value(
            "Fuel Quota",
            self.fuel_quota,
            {"monthly_litres": flt(quota.monthly_litres) + flt(self.topup_litres), "status": "Active"},
        )
        self.db_set("topup_applied", 1)
        add_timeline_note(
            "Fuel Quota", self.fuel_quota,
            _("Added {0} L via Fuel Request {1}.").format(self.topup_litres, self.name),
        )

    def _reverse_topup(self):
        if not self.topup_applied or not self.fuel_quota:
            return
        lock_fuel_quota(self.fuel_quota)
        quota = frappe.db.get_value(
            "Fuel Quota", self.fuel_quota, ["monthly_litres", "status"], as_dict=True
        )
        if quota:
            frappe.db.set_value(
                "Fuel Quota",
                self.fuel_quota,
                {"monthly_litres": max(flt(quota.monthly_litres) - flt(self.topup_litres), 0)},
            )
        self.db_set("topup_applied", 0)
        add_timeline_note(
            "Fuel Quota", self.fuel_quota,
            _("Removed {0} L from reverted Fuel Request {1}.").format(self.topup_litres, self.name),
        )
