# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.workflow import apply_workflow
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
        if self.incident_date and getdate(self.incident_date) > getdate(today()):
            frappe.throw(_("Incident date cannot be in the future."))
        if flt(self.estimated_cost) < 0:
            frappe.throw(_("Estimated cost cannot be negative."))
        self._guard_public_intake()
        self._guard_cost_recovery()
        self._sync_third_party()

    def _sync_third_party(self):
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
        if not self.recover_from_driver:
            for field in ("worker_signature", "signed_on"):
                self.set(field, None)
            return

        if "lending" not in frappe.get_installed_apps():
            frappe.throw(
                _(
                    "Recovering this cost from the driver needs the Lending app, which is not installed on this site. Install it first, or clear Recover From Driver."
                )
            )

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
        if self.get("website_field"):
            frappe.throw(_("Invalid submission."), frappe.PermissionError)

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
    resolution = str(resolution or "").strip()
    if not resolution:
        frappe.throw(_("A resolution is required to close a Vehicle Incident."))

    doc = frappe.get_doc("Vehicle Incident", name, for_update=True)
    if check_permission:
        doc.check_permission("write")
    if doc.docstatus != 1:
        frappe.throw(_("Only submitted Vehicle Incidents can be closed."))

    frappe.db.savepoint(_TRANSITION_SAVEPOINT)
    try:
        apply_workflow(doc, "Close")
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
    return {"name": doc.name, "status": doc.status}


@frappe.whitelist(methods=["POST"])
def close_incident(name: str, resolution: str) -> dict:
    return close_incident_internal(name, resolution)
