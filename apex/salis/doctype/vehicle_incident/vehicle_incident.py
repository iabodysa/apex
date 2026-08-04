# Copyright (c) 2026, AFMCO and contributors
"""Vehicle Incident controller.

Records a fleet incident event - an accident or a theft - against a vehicle.
This is the event of record (location, report number, fault, evidence); it is
distinct from a Vehicle Damage Write-Off (the disposition/authority gate) and a
Vehicle Suspension (the state change). A submitted Theft incident takes the vehicle out
of service and clears its driver, capturing the prior state so a cancel reverses
it cleanly. An Accident incident records the event only; stopping the vehicle, if
needed, is a separate Vehicle Suspension.

Cost recovery is native, no bespoke consent DocType: when the incident is flagged
``recover_from_driver`` it raises ONE HRMS Employee Advance on submit (the
receivable), and the wage installments run on Additional Salary rows linked to that
advance - see apex.apex_core.utils.employee_recovery. The worker's signed consent is
mandatory before that approval (KSA Labor Law), and one incident maps to at most one
advance.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, today

from apex.apex_core.utils.employee_recovery import raise_recovery_advance
from apex.salis.utils import add_timeline_note, lock_vehicle

_RECOVERY_INTAKE_RESET = {
    "recover_from_driver": 0,
    "recovery_employee": None,
    "recovery_amount": 0,
    "installment_amount": 0,
    "worker_signature": None,
    "signed_on": None,
    "recovery_advance": None,
}


class VehicleIncident(Document):
    def validate(self):
        if self.incident_date and getdate(self.incident_date) > getdate(today()):
            frappe.throw(_("Incident date cannot be in the future."))
        if flt(self.estimated_cost) < 0:
            frappe.throw(_("Estimated cost cannot be negative."))
        self._guard_public_intake()
        self._guard_cost_recovery()

    def _guard_cost_recovery(self):
        """Consent gate on the wage-recovery decision.

        The signature is the worker's written consent to the deduction, which KSA
        Labor Law requires before a wage may be touched; the incident cannot be
        approved (submitted) without it. A draft may still be saved unsigned so the
        signature can be collected after the case is opened.
        """
        if not self.recover_from_driver:
            for field in ("worker_signature", "signed_on"):
                self.set(field, None)
            return

        if self.worker_signature and not self.signed_on:
            self.signed_on = today()
        elif not self.worker_signature:
            self.signed_on = None

        if flt(self.recovery_amount) <= 0:
            frappe.throw(_("Amount to Recover must be greater than zero."))
        if flt(self.estimated_cost) > 0 and flt(self.recovery_amount) > flt(self.estimated_cost):
            frappe.throw(_("Amount to Recover cannot exceed the estimated cost."))
        if flt(self.installment_amount) > flt(self.recovery_amount):
            frappe.throw(_("Agreed Installment cannot exceed the Amount to Recover."))

        if self.docstatus == 1 and not self.worker_signature:
            frappe.throw(
                _("The worker's consent signature is required before a cost recovery can be approved.")
            )

    def _guard_public_intake(self):
        if self.is_new() and frappe.session.user == "Guest":
            self.status = "Open"
            for field in ("write_off_case", "previous_status", "previous_driver"):
                self.set(field, None)
            for field, blank in _RECOVERY_INTAKE_RESET.items():
                self.set(field, blank)

        for field, limit in (("description", 4000), ("location", 280), ("report_number", 140), ("reported_by", 140)):
            value = self.get(field)
            if value and len(value) > limit:
                frappe.throw(_("{0} is too long.").format(_(self.meta.get_label(field))))

    def on_submit(self):
        self._raise_recovery_advance()
        if self.incident_type != "Theft":
            return

        lock_vehicle(self.vehicle)

        prev_status, prev_driver = frappe.db.get_value(
            "Salis Vehicle", self.vehicle, ["status", "current_driver"]
        )
        self.db_set("previous_status", prev_status)
        self.db_set("previous_driver", prev_driver)

        frappe.db.set_value(
            "Salis Vehicle",
            self.vehicle,
            {"status": "Stopped", "current_driver": None},
        )
        if prev_driver:
            frappe.db.set_value("Salis Driver", prev_driver, "current_vehicle", None)

        self.add_comment("Comment", _("Vehicle {0} reported stolen.").format(self.vehicle))
        add_timeline_note(
            "Salis Vehicle",
            self.vehicle,
            _("Reported stolen via {0}.").format(self.name),
        )

    def _raise_recovery_advance(self):
        """Map this incident to its ONE Employee Advance.

        Idempotent on both sides: the stored link short-circuits a re-submit, and
        ``find_recovery_advance`` catches an amendment that arrives with a blank link.
        A site that cannot raise an advance yet (no Employee Advance account) logs and
        continues — the incident is still the event of record.
        """
        if not self.recover_from_driver or self.recovery_advance:
            return
        advance = raise_recovery_advance(
            source_doctype=self.doctype,
            source_name=self.name,
            employee=self.recovery_employee,
            amount=flt(self.recovery_amount),
            purpose=_("Vehicle damage recovery for incident {0} (vehicle {1}).").format(
                self.name, self.vehicle
            ),
            posting_date=self.incident_date,
        )
        if advance:
            self.db_set("recovery_advance", advance)

    def _live_recovery_advance(self):
        """The linked Employee Advance while it is still submitted, else None.

        One reader for both halves of the cancel: there is nothing to refuse and
        nothing to reverse when the incident raised no advance, or when the advance
        is already a draft or cancelled.
        """
        advance = self.recovery_advance
        if not advance:
            return None
        state = frappe.db.get_value(
            "Employee Advance",
            advance,
            ["name", "docstatus", "paid_amount", "return_amount"],
            as_dict=True,
        )
        return state if state and state.docstatus == 1 else None

    def before_cancel(self):
        """REFUSAL half of the cancel: once real money has moved - the company has
        paid, or an installment has been recovered - reversing is an accounting
        decision, so the cancel is refused instead of silently unwinding a posted
        balance.

        Here and not in on_cancel: Frappe dispatches before_cancel from
        run_before_save_methods() (frappe/model/document.py:414), writes the row with
        db_update() (:428) and only then dispatches on_cancel from
        run_post_save_methods() (:431). Thrown from on_cancel, this refusal leaves
        docstatus 2 already stamped in the open transaction, so everything reading
        the incident later in the request sees a refused cancel as cancelled and only
        the request-level rollback undoes it. This method only reads, so a throw
        leaves the incident AND the advance untouched.

        A Document method with no hooks.py entry: Frappe composes the class method
        ahead of the app-wide workflow_guard.before_cancel handler.
        """
        state = self._live_recovery_advance()
        if state and (flt(state.paid_amount) or flt(state.return_amount)):
            frappe.throw(
                _(
                    "Cannot cancel incident {0}: Employee Advance {1} already carries a paid or recovered amount. Reverse it in Accounts first."
                ).format(self.name, state.name)
            )

    def _release_recovery_advance(self):
        """RESTORATION half: reverse the receivable when the incident is cancelled.

        Cancelling the advance reverses the recovered balance natively (HRMS reverses
        each linked Additional Salary's contribution on its own cancel). The paid /
        recovered refusal is not re-checked here - before_cancel has already run and
        nothing between the two hooks can pay the advance.
        """
        state = self._live_recovery_advance()
        if state:
            frappe.get_doc("Employee Advance", state.name).cancel()

    def on_cancel(self):
        self._release_recovery_advance()
        if self.incident_type != "Theft":
            return

        lock_vehicle(self.vehicle)

        if self.previous_driver and not frappe.db.get_value(
            "Salis Vehicle", self.vehicle, "current_driver"
        ):
            frappe.db.set_value(
                "Salis Vehicle", self.vehicle, "current_driver", self.previous_driver
            )
            frappe.db.set_value(
                "Salis Driver", self.previous_driver, "current_vehicle", self.vehicle
            )

        another_stop_in_force = frappe.db.exists(
            "Vehicle Suspension", {"vehicle": self.vehicle, "docstatus": 1}
        )
        if (
            not another_stop_in_force
            and frappe.db.get_value("Salis Vehicle", self.vehicle, "status") == "Stopped"
        ):
            frappe.db.set_value(
                "Salis Vehicle",
                self.vehicle,
                "status",
                self.previous_status or "Active",
            )

        add_timeline_note(
            "Salis Vehicle",
            self.vehicle,
            _("Theft report {0} cancelled.").format(self.name),
        )
