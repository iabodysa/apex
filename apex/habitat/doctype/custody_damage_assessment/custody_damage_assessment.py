# Copyright (c) 2026, AFMCO and contributors
"""Custody Damage Assessment controller.

Why Finance Manager holds TWO rows here. The permlevel-1 row is a field overlay: it
unlocks the money (``total_estimated_replacement_cost``) wherever the role can already
open the document, because document access resolves from permlevel-0 rows only while
field access is resolved separately and unions every permlevel across the user's roles.
The permlevel-0 ``read`` beside it is a separate grant, so a Finance Manager holding no
other role can open the record the ``Custody Damage Assessment Created`` notification
emails them. It is unscoped, so it reaches every building.

That row also carries ``report``, so the solo Finance Manager can reach the list's
report view that totals assessments, not only the one opened from a notification.
``report`` is the narrowest right that does it -- it gates only the report surface
(``frappe/desk/query_report.py:47``) and carries no row and no field with it. That
surface reads exactly two things: permlevel-0 columns the read already opened, and
``total_estimated_replacement_cost``, which is permlevel 1 and so is already this role's
own overlay field. Habitat oversight is unscoped (``HOUSING_UNSCOPED_ROLES``,
``habitat/permissions.py``), so building scoping returns the same rows to this role
either way. Nothing on that surface is a datum the role could not already reach on the
form, which is why it is a surface grant and not an access widening. Every other flag on
the row is still an explicit 0: no write, no export, no share.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from apex.apex_core.doctype.salary_deduction_policy.salary_deduction_policy import (
    get_damage_rule,
    get_policy,
)
from apex.apex_core.utils.party_link import sync_party_employee


class CustodyDamageAssessment(Document):
    pass


@frappe.whitelist()
def get_deduction_status(assessment):
    """Live status of the deduction linked to a Custody Damage Assessment.

    Read-only and computed on demand so the manager sees the current state of
    the Additional Salary rather than a stale stored copy.
    """
    frappe.has_permission("Custody Damage Assessment", "read", doc=assessment, throw=True)
    entry = frappe.db.get_value("Custody Damage Assessment", assessment, "deduction_entry")
    if not entry:
        return {"entry": None, "status": "Not Created"}

    docstatus = frappe.db.get_value("Additional Salary", entry, "docstatus")
    if docstatus == 2:
        return {"entry": entry, "status": "Cancelled"}
    if docstatus == 0:
        return {"entry": entry, "status": "Draft"}

    paid = frappe.db.exists(
        "Salary Detail",
        {"additional_salary": entry, "parenttype": "Salary Slip", "docstatus": 1},
    )
    return {"entry": entry, "status": "Paid" if paid else "Submitted"}


def validate(doc, method=None):
    sync_party_employee(doc)
    if not doc.items:
        frappe.throw(_("At least one damaged item is required."))
    doc.total_estimated_replacement_cost = sum(
        flt(row.estimated_replacement_cost) for row in doc.items
    )


def on_submit(doc, method=None):
    if doc.deduction_entry:
        return
    rule = get_damage_rule()
    if rule and doc.employee:
        logger = frappe.logger()

        amount = flt(doc.total_estimated_replacement_cost)
        max_deduction = flt(rule.cap_amount_per_event)
        if max_deduction > 0 and amount > max_deduction:
            amount = max_deduction

        if amount <= 0:
            logger.info(
                f"custody_damage_assessment.on_submit: Assessment {doc.name} has zero or negative cost. Skipping deduction."
            )
            return

        company = frappe.db.get_value("Employee", doc.employee, "company")
        if not company:
            logger.warning(
                f"custody_damage_assessment.on_submit: Employee {doc.employee} has no company linked. "
                f"Cannot create Additional Salary entry for assessment {doc.name}. Entry remains manual."
            )
            return

        salary_component = rule.salary_component or get_policy().default_salary_component
        if not salary_component:
            logger.warning(
                f"custody_damage_assessment.on_submit: Salary Deduction Policy > Damage rule has no "
                f"Salary Component (and no default). Cannot auto-generate Additional Salary for assessment {doc.name}."
            )
            return

        component_type = frappe.db.get_value("Salary Component", salary_component, "type")
        if component_type != "Deduction":
            frappe.throw(_("Salary component {0} must be of type Deduction for damage assessments.").format(salary_component))

        add_sal = frappe.get_doc({
            "doctype": "Additional Salary",
            "employee": doc.employee,
            "salary_component": salary_component,
            "amount": amount,
            "payroll_date": doc.assessment_date,
            "company": company,
            "remarks": f"Deduction for custody damage assessment {doc.name}"
        })
        add_sal.insert(ignore_permissions=True)

        frappe.db.set_value("Custody Damage Assessment", doc.name, "deduction_entry", add_sal.name)

        if doc.source_checkout:
            frappe.db.set_value(
                "Housing Checkout",
                doc.source_checkout,
                {
                    "additional_salary_deduction": add_sal.name,
                    "damage_deduction_amount": add_sal.amount,
                },
            )

        logger.info(
            f"custody_damage_assessment.on_submit: Draft Additional Salary {add_sal.name} "
            f"created for assessment {doc.name}."
        )


def before_cancel(doc, method=None):
    if doc.deduction_entry:
        deduction_docstatus = frappe.db.get_value(
            "Additional Salary", doc.deduction_entry, "docstatus"
        )
        if deduction_docstatus == 1:
            frappe.throw(
                _("Cannot cancel Custody Damage Assessment {0} because Additional Salary Deduction Entry {1} is submitted.").format(
                    doc.name, doc.deduction_entry
                )
            )


def on_cancel(doc, method=None):
    """Undo what on_submit created: the draft deduction and the two fields it
    wrote onto the source checkout.

    before_cancel has already refused the submitted-deduction case, so anything
    reaching here holds a deduction that was never paid. A draft Additional
    Salary cannot be cancelled — docstatus 0 has no cancel — so it is deleted,
    which is also what leaves the employee with no trace of a deduction that was
    withdrawn before it ever ran."""
    if not doc.deduction_entry:
        return

    if frappe.db.get_value("Additional Salary", doc.deduction_entry, "docstatus") == 0:
        entry = doc.deduction_entry
        frappe.delete_doc("Additional Salary", entry, force=True, ignore_permissions=True)  # audit-ok: undoes the entry on_submit created under the same bypass; the caller already holds cancel on this assessment

    if doc.source_checkout:
        frappe.db.set_value(
            "Housing Checkout",
            doc.source_checkout,
            {"additional_salary_deduction": None, "damage_deduction_amount": 0},
        )

    frappe.db.set_value(
        "Custody Damage Assessment", doc.name, "deduction_entry", None
    )

