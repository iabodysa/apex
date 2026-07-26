# Copyright (c) 2026, AFMCO and contributors
"""Custody Damage Assessment controller.

A-218 -- why Finance Manager holds a permlevel-1 row here and NO permlevel-0 row.
It is a deliberate field overlay, not an omission: the role may read the money
(``total_estimated_replacement_cost``) on a document another role opens, and may not
open, create, submit or cancel it. Document access is resolved from permlevel-0 rows
only, field access is resolved separately and unions every permlevel across the user's
roles, so the two are independent grants. Live today: the shipped ``Habitat Finance
Reviewer`` profile is Finance Manager + Internal Auditor, and Internal Auditor's
permlevel-0 read is what opens this document for it. Proof and the framework citations
are in ``test_finance_manager_field_overlay.py`` beside this file.
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
    # [#2kf8j7]
    frappe.has_permission("Custody Damage Assessment", "read", doc=assessment, throw=True)
    entry = frappe.db.get_value("Custody Damage Assessment", assessment, "deduction_entry")
    if not entry:
        return {"entry": None, "status": "Not Created"}

    docstatus = frappe.db.get_value("Additional Salary", entry, "docstatus")
    if docstatus == 2:
        return {"entry": entry, "status": "Cancelled"}
    if docstatus == 0:
        return {"entry": entry, "status": "Draft"}

    # [#pm40n2]
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
    # [#o53dvg]
    if doc.deduction_entry:
        return
    # [#1we8qc]
    rule = get_damage_rule()
    if rule and doc.employee:
        logger = frappe.logger()

        # [#cgz16m]
        amount = flt(doc.total_estimated_replacement_cost)
        max_deduction = flt(rule.cap_amount_per_event)
        if max_deduction > 0 and amount > max_deduction:
            amount = max_deduction

        if amount <= 0:
            logger.info(
                f"custody_damage_assessment.on_submit: Assessment {doc.name} has zero or negative cost. Skipping deduction."
            )
            return

        # [#m8u7fg]
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

        # [#kfnh9k]
        component_type = frappe.db.get_value("Salary Component", salary_component, "type")
        if component_type != "Deduction":
            frappe.throw(_("Salary component {0} must be of type Deduction for damage assessments.").format(salary_component))

        # [#s89pd2]
        add_sal = frappe.get_doc({
            "doctype": "Additional Salary",
            "employee": doc.employee,
            "salary_component": salary_component,
            "amount": amount,
            "payroll_date": doc.assessment_date,
            "company": company,
            "remarks": f"Deduction for custody damage assessment {doc.name}"
        })
        # [#555m5p]
        add_sal.insert(ignore_permissions=True)

        # [#rbyvmi]
        frappe.db.set_value("Custody Damage Assessment", doc.name, "deduction_entry", add_sal.name)

        # [#jyym7r]
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
    # [#kep3uf]
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

