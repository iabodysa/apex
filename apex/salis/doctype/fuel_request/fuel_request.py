# Copyright (c) 2026, afmcoltd
"""Fuel Request controller (unified).

A single submittable fuel request whose ``request_type`` selects one of three
behaviours, preserving the contract of the three former DocTypes verbatim:

* **Standard** — fuel-increase request against a Fuel Quota. Drives a
  Pending -> Approved -> Done flow (Failed / Cancelled exits) whose approval
  authority is owned by the native Fuel Request Workflow, and posts/reverses
  quota consumption idempotently on submit/cancel. The Fuel accrual engine later
  ledgers the Done request (``ledgered`` flag) into the Fuel Consumption Ledger.
* **Top-up** — fuel top-up. Temporary top-ups carry a revert-due date and are
  auto-reverted by the daily Salis scheduler once overdue; this controller only
  surfaces a warning for the overdue case and guards status transitions.
* **Chip** — request to issue / replace / cancel a vehicle fuel chip. Light
  validation plus an audit entry on submit; a cancellation requires inactivity
  evidence and owner acknowledgement.

No GL is written.

Status transitions are owned by the native **Fuel Request Workflow** (see
``salis/workflow/fuel_request_workflow/``), not by this controller. The workflow
enforces the role per transition, the Segregation-of-Duties gate on the
approval (``allow_self_approval=0`` + ``requested_by != session.user``), and the
type-aware availability of the terminal transitions (``Mark Failed`` only for a
Standard request, ``Revert`` only for a Top-up) via its transition
``condition``s. The document is submitted (docstatus 0 -> 1) by the ``Approve``
transition; ``Done`` / ``Failed`` / ``Reverted`` are then reachable post-submit
(the state field is ``allow_on_submit``).

This controller keeps only what the workflow cannot express: the per-type
required-field validation, the Chip evidence/acknowledgement gate, the
initial-status guard (a request must be created at Pending), the quota-allowance
gate (a Standard draw is refused when the allocation is spent OR when the draw
itself would overrun what is left — checked at Approve and again at the locked
consumption step), and the idempotent
quota side-effects — Standard quota
consumption is applied when the request reaches Done (on submit if it submits
straight into Done, or on the post-submit transition into Done) and reversed on
cancel, guarded by the ``quota_applied`` flag.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, nowdate

from apex.salis.utils import (
    add_timeline_note,
    lock_fuel_quota,
    lock_vehicle,
    rider_block_reason,
)

REQUEST_TYPES = ("Standard", "Top-up", "Chip")

VALID_STATUSES = ("Pending", "Approved", "Done", "Failed", "Reverted", "Cancelled")


class FuelRequest(Document):

    def before_insert(self):
        """Defaults the requester to the current session user when not already set."""
        if not self.requested_by:
            self.requested_by = frappe.session.user

    def validate(self):
        """Runs the per-type field checks and blocks a request from a rider who is inactive."""
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
        """Block a new fuel request for a rider who is on leave / inactive.

		Fuel is dispensed to the rider who holds the vehicle, so an offboarded /
		on-leave rider must not draw new fuel. When such a rider still holds a
		vehicle, also open a supervisor clearance task to recover it (idempotent;
		best-effort so it never blocks the rejection).

		The task is ENQUEUED, not called. ``frappe.throw`` on the next line aborts this
		request and the framework rolls the whole transaction back with it, so a ToDo
		inserted inline was discarded again the moment it was made — the follow-up this
		docstring promises never existed. The job runs in its own transaction. Its source
		document is deliberately not passed: this Fuel Request is about to cease to exist,
		and a timeline note on it would land on nothing. The ToDo references the Salis
		Driver, which survives."""
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
        """Blocks submission when a Standard draw exceeds the quota, or a Chip cancel lacks evidence."""
        if self.request_type == "Standard":
            self._guard_quota_allowance()
        elif self.request_type == "Chip":
            self._guard_chip_cancellation()

    def on_submit(self):
        """Posts quota consumption for a Standard request, or logs a vehicle timeline note for the rest."""
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
        """Fire the Done side-effect for a post-submit workflow transition.

		The Fuel Request Workflow submits at Approved (docstatus 0 -> 1) and then
		moves Approved -> Done as a post-submit transition (the state field is
		``allow_on_submit``). The Standard quota consumption must therefore post
		when the request *reaches* Done, not only at submit time. Idempotent via
		the ``quota_applied`` flag, so it is safe even if on_submit already ran."""
        if self.request_type == "Standard" and self.status == "Done":
            self._apply_quota_consumption()
        elif self.request_type == "Top-up":
            if self.status in ("Approved", "Done"):
                self._apply_topup()
            elif self.status in ("Reverted", "Cancelled"):
                self._reverse_topup()

    def on_cancel(self):
        """Reverses posted quota consumption and the request's fuel ledger entry."""
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

        from apex.salis.fuel_engine import reverse_fuel_ledger

        reverse_fuel_ledger("Fuel Request", self.name)


    def _validate_standard(self):
        """Requires the requested litres to be greater than zero."""
        if (self.requested_litres or 0) <= 0:
            frappe.throw(_("Requested Litres must be greater than zero."))

    def _validate_topup(self):
        """Requires positive top-up litres and a revert date for a temporary top-up."""
        if (self.topup_litres or 0) <= 0:
            frappe.throw(_("Top-up Litres must be greater than zero."))
        if not self.fuel_quota:
            frappe.throw(_("A Top-up request requires an active Fuel Quota."))
        if self.is_temporary and not self.revert_due_date:
            frappe.throw(_("A temporary top-up requires a revert due date."))
        self._warn_overdue_temporary()

    def _validate_chip(self):
        """Requires a chip action, and a chip number when replacing or cancelling a chip."""
        if not self.action:
            frappe.throw(_("A chip action (Issue / Replace / Cancel) is required."))
        if self.action in ("Replace", "Cancel") and not self.chip_number:
            frappe.throw(
                _("A chip number is required to {0} a fuel chip.").format(_(self.action))
            )


    def _guard_initial_status(self):
        """A new request must be created at the initial state (Pending). Later
		states are reached only through the Fuel Request Workflow, which the desk
		drives — this closes the insert-bypass the workflow itself cannot cover
		(a brand-new document inserted directly at a later/terminal status)."""
        if self.is_new() and self.status and self.status != "Pending":
            frappe.throw(
                _("A Fuel Request must be created with status Pending; {0} is reached through the workflow.").format(
                    _(self.status)
                )
            )

    def _stamp_approver(self):
        """Stamps the current user as approver when the status is set to Approved."""
        if self.status == "Approved" and not self.approved_by:
            self.approved_by = frappe.session.user


    def _warn_overdue_temporary(self):
        """Warns when a temporary top-up is past its revert due date and has not been reverted."""
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
        """Requires inactivity evidence and owner acknowledgement before a chip cancel submits."""
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
        """A Standard request draws down a monthly allocation, so the allocation
		must cover it — Top-up is the sanctioned way to add fuel beyond the
		allocation and stays exempt. Two refusals share this one enforcement point:

		* the quota has nothing left at all (status Exhausted, or consumption has
		  already reached the allocation), and
		* this draw alone would overrun what is left. An exhaustion test on its own
		  cannot see that: 15 L against a 10 L quota with 0 consumed satisfies
		  ``consumed < monthly``, so the oversized FIRST draw used to pass here and
		  push consumed_litres past the allocation at Done.

		Called once before submit for early desk feedback and again inside the
		consumption step, where the quota row is already locked and the read is
		authoritative — that second call is what catches two in-flight requests
		that each fit on their own but together overrun the allocation."""
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
        """Idempotently add requested_litres to the quota's consumed_litres."""
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
        """Reverse a previously applied quota consumption on cancel."""
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
        """Increase the linked monthly quota once when this request is approved."""
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
        """Remove an applied top-up once on revert or cancellation."""
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
