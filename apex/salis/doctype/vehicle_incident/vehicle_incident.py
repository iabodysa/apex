# Copyright (c) 2026, afmcoltd
"""Vehicle Incident controller.

Records a fleet incident event - an accident or a theft - against a vehicle.
This is the event of record (location, report number, fault, evidence); it is
distinct from a Vehicle Damage Write-Off (the disposition/authority gate) and a
Vehicle Suspension (the state change). A submitted Theft incident takes the vehicle out
of service and clears its driver, capturing the prior state so a cancel reverses
it cleanly. An Accident incident records the event only; stopping the vehicle, if
needed, is a separate Vehicle Suspension.

Cost recovery is native, no bespoke consent DocType: when the incident is flagged
``recover_from_driver`` it raises ONE native Loan on submit, with Repay From Salary
set - see apex.apex_core.utils.employee_loan_recovery. HRMS itself runs the wage
installment and the outstanding balance from the Loan's own repayment schedule; this
controller neither computes nor stores either. The worker's signed consent is
mandatory before that approval (KSA Labor Law), and one incident maps to at most one
loan. ``recovery_advance`` is legacy: incidents raised before this change may still
carry an open Employee Advance, which is left to run out rather than migrated (see
apex.apex_core.utils.employee_recovery); no incident writes that field anymore.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, today

from apex.apex_core.utils.employee_loan_recovery import raise_recovery_loan
from apex.salis.utils import add_timeline_note, lock_vehicle, set_current_driver

_RECOVERY_INTAKE_RESET = {
    "recover_from_driver": 0,
    "recovery_employee": None,
    "recovery_amount": 0,
    "installment_amount": 0,
    "worker_signature": None,
    "signed_on": None,
    "recovery_advance": None,
    "recovery_loan": None,
}
_TRANSITION_SAVEPOINT = "vehicle_incident_transition"


class VehicleIncident(Document):
    def validate(self):
        """Validates the incident date and cost, and enforces public-intake and cost-recovery guards."""
        self._guard_status()
        if self.incident_date and getdate(self.incident_date) > getdate(today()):
            frappe.throw(_("Incident date cannot be in the future."))
        if flt(self.estimated_cost) < 0:
            frappe.throw(_("Estimated cost cannot be negative."))
        self._guard_public_intake()
        self._guard_cost_recovery()
        self._sync_third_party()

    def _guard_status(self):
        """Keep lifecycle status under controller-owned transitions."""
        if self.is_new():
            self.status = "Open"
            return
        if self.has_value_changed("status"):
            frappe.throw(
                _("Use the incident actions to change Status."),
                frappe.PermissionError,
            )

    def _sync_third_party(self):
        """Keep the third-party block and its flag telling the same story.

        The statement goes to an insurer, so a plate or a policy left over from a
        correction would name a party who was never in the accident. The flag is the
        switch: while it is on the four fields stand, and the moment it comes off they
        are emptied, so the printed block appears only while the record actually holds
        a third party.
        """
        if self.third_party_involved:
            return
        for field in (
            "third_party_plate",
            "third_party_driver",
            "third_party_insurer",
            "third_party_policy",
        ):
            self.set(field, None)

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
        """Resets privileged fields on a new guest-submitted incident and caps free-text field lengths."""
        if self.is_new() and frappe.session.user == "Guest":
            self.status = "Open"
            for field in ("write_off_case", "previous_status", "previous_driver"):
                self.set(field, None)
            for field, blank in _RECOVERY_INTAKE_RESET.items():
                self.set(field, blank)

        for field, limit in (
            ("description", 4000),
            ("location", 280),
            ("report_number", 140),
            ("reported_by", 140),
            ("injury_details", 1000),
            ("policy_number", 140),
            ("insurance_claim_number", 140),
            ("third_party_plate", 40),
            ("third_party_driver", 140),
            ("third_party_insurer", 140),
            ("third_party_policy", 140),
        ):
            value = self.get(field)
            if value and len(value) > limit:
                frappe.throw(_("{0} is too long.").format(_(self.meta.get_label(field))))

    def on_submit(self):
        """Raises the recovery loan and, for a theft, stops the vehicle and clears its driver."""
        self.db_set("status", "Under Review")
        self._raise_recovery_loan()
        if self.incident_type != "Theft":
            return

        lock_vehicle(self.vehicle)

        prev_status, prev_driver = frappe.db.get_value(
            "Salis Vehicle", self.vehicle, ["status", "current_driver"]
        )
        self.db_set("previous_status", prev_status)
        self.db_set("previous_driver", prev_driver)

        set_current_driver(self.vehicle, None, status="Stopped")
        if prev_driver:
            frappe.db.set_value("Salis Driver", prev_driver, "current_vehicle", None)

        self.add_comment("Comment", _("Vehicle {0} reported stolen.").format(self.vehicle))
        add_timeline_note(
            "Salis Vehicle",
            self.vehicle,
            _("Reported stolen via {0}.").format(self.name),
        )

    def _raise_recovery_loan(self):
        """Map this incident to its ONE Loan.

        Idempotent within this document's lifecycle: the stored link short-circuits a
        re-submit. A site that cannot yet size the installment (no company, no Loan
        Product accounts, no active Salary Structure Assignment for the employee) logs
        and continues — the incident is still the event of record.
        """
        if not self.recover_from_driver or self.recovery_loan:
            return
        loan = raise_recovery_loan(
            source_doctype=self.doctype,
            source_name=self.name,
            employee=self.recovery_employee,
            amount=flt(self.recovery_amount),
            purpose=_("Vehicle damage recovery for incident {0} (vehicle {1}).").format(
                self.name, self.vehicle
            ),
            posting_date=self.incident_date,
            agreed_installment=flt(self.installment_amount),
        )
        if loan:
            self.db_set("recovery_loan", loan)

    def _live_recovery_loan(self):
        """The linked Loan while it is still submitted and untouched by payroll, else None.

        One reader for both halves of the cancel: there is nothing to refuse and
        nothing to reverse when the incident raised no loan, when the loan is already
        cancelled, or (defensively; ``before_cancel`` already checked this) once a Loan
        Repayment has been posted against it.
        """
        loan = self.recovery_loan
        if not loan:
            return None
        state = frappe.db.get_value(
            "Loan",
            loan,
            ["name", "docstatus", "total_principal_paid"],
            as_dict=True,
            for_update=True,
        )
        return state if state and state.docstatus == 1 else None

    def _live_recovery_advance(self):
        """The legacy linked Employee Advance while it is still submitted, else None.

        Only a pre-migration incident carries ``recovery_advance``; kept so cancelling
        one of those still refuses and reverses correctly.
        """
        advance = self.recovery_advance
        if not advance:
            return None
        state = frappe.db.get_value(
            "Employee Advance",
            advance,
            ["name", "docstatus", "paid_amount", "return_amount"],
            as_dict=True,
            for_update=True,
        )
        return state if state and state.docstatus == 1 else None

    def before_cancel(self):
        """REFUSAL half of the cancel: once real money has moved - the company has
        paid, an installment has been recovered, or a Loan Repayment has posted -
        reversing is an accounting decision, so the cancel is refused instead of
        silently unwinding a posted balance.

        A Document method with no hooks.py entry: Frappe composes the class method
        ahead of the app-wide workflow_guard.before_cancel handler.

        """
        loan_state = self._live_recovery_loan()
        if loan_state and (
            flt(loan_state.total_principal_paid)
            or frappe.db.exists(
                "Loan Repayment", {"against_loan": loan_state.name, "docstatus": 1}
            )
        ):
            frappe.throw(
                _(
                    "Cannot cancel incident {0}: Loan {1} already carries a recovered amount. Reverse it in Accounts first."
                ).format(self.name, loan_state.name)
            )

        advance_state = self._live_recovery_advance()
        if advance_state and (flt(advance_state.paid_amount) or flt(advance_state.return_amount)):
            frappe.throw(
                _(
                    "Cannot cancel incident {0}: Employee Advance {1} already carries a paid or recovered amount. Reverse it in Accounts first."
                ).format(self.name, advance_state.name)
            )

    def _release_recovery_loan(self):
        """RESTORATION half: cancel the Loan (and its Disbursement) when the incident
        is cancelled.

        The Disbursement is cancelled first: it is what activated the Loan's
        repayment schedule (see apex.apex_core.utils.employee_loan_recovery), and a
        submitted Loan Disbursement still linking the Loan would refuse the Loan's own
        cancel (Loan.on_cancel only ignores GL Entry / Payment Ledger Entry links,
        lending/loan_management/doctype/loan/loan.py:118). Cancelling the Loan itself
        then reverses its draft repayment schedule natively (loan.py:115-118). The
        paid refusal is not re-checked here: ``before_cancel`` already locked the loan
        row for this transaction, so nothing between the two hooks can pay it.
        """
        state = self._live_recovery_loan()
        if state:
            for disbursement in frappe.get_all(
                "Loan Disbursement",
                filters={"against_loan": state.name, "docstatus": 1},
                pluck="name",
            ):
                frappe.get_doc("Loan Disbursement", disbursement).cancel()
            frappe.get_doc("Loan", state.name).cancel()

    def _release_recovery_advance(self):
        """RESTORATION half: reverse the legacy receivable when the incident is cancelled.

        Cancelling the advance reverses the recovered balance natively (HRMS reverses
        each linked Additional Salary's contribution on its own cancel). The paid /
        recovered refusal is not re-checked here: ``before_cancel`` already locked
        the advance row for this transaction, so nothing between the two hooks can
        pay it.
        """
        state = self._live_recovery_advance()
        if state:
            for installment in frappe.get_all(
                "Additional Salary",
                filters={
                    "ref_doctype": "Employee Advance",
                    "ref_docname": state.name,
                    "docstatus": 0,
                },
                pluck="name",
            ):
                frappe.db.set_value(
                    "Additional Salary",
                    installment,
                    "disabled",
                    1,
                    update_modified=False,
                )
            frappe.get_doc("Employee Advance", state.name).cancel()

    def on_cancel(self):
        """Reverses the recovery loan (or, for a pre-migration incident, the legacy
        advance) and, for a theft, restores the vehicle's prior driver and status."""
        self.db_set("status", "Closed")
        self._release_recovery_loan()
        self._release_recovery_advance()
        if self.incident_type != "Theft":
            return

        lock_vehicle(self.vehicle)

        if self.previous_driver and not frappe.db.get_value(
            "Salis Vehicle", self.vehicle, "current_driver"
        ):
            set_current_driver(self.vehicle, self.previous_driver)
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


def close_incident_internal(
    name: str,
    resolution: str,
    *,
    check_permission: bool = True,
) -> dict:
    """Close one submitted incident through the canonical transition.

    ``frappe.db.savepoint`` / ``rollback`` (frappe/database/database.py:1203, :1186)
    wrap the close, because it moves the incident AND writes the vehicle back to
    service. The one thing a plain try/except cannot do is undo the first write when
    the second refuses, which would leave a closed incident on a vehicle still marked
    stopped.
    """
    resolution = str(resolution or "").strip()
    if not resolution:
        frappe.throw(_("A resolution is required to close a Vehicle Incident."))

    doc = frappe.get_doc("Vehicle Incident", name, for_update=True)
    if check_permission:
        doc.check_permission("write")
    if doc.docstatus != 1:
        frappe.throw(_("Only submitted Vehicle Incidents can be closed."))
    if doc.status != "Under Review":
        frappe.throw(_("Only an incident under review can be closed."))

    frappe.db.savepoint(_TRANSITION_SAVEPOINT)
    try:
        doc.db_set("status", "Closed")
        doc.add_comment(
            "Comment",
            _("Incident closed: {0}").format(resolution),
        )
        add_timeline_note(
            "Salis Vehicle",
            doc.vehicle,
            _("Incident {0} closed: {1}").format(doc.name, resolution),
        )
    except Exception:
        frappe.db.rollback(save_point=_TRANSITION_SAVEPOINT)
        raise
    return {"name": doc.name, "status": "Closed"}


@frappe.whitelist(methods=["POST"])
def close_incident(name: str, resolution: str) -> dict:
    """Permission-checked incident close action for Desk and portal clients."""
    return close_incident_internal(name, resolution)
