"""Custody Damage Assessment controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from apex_habitat.apex_core.utils.party_link import sync_party_employee


class CustodyDamageAssessment(Document):
    pass


@frappe.whitelist()
def get_deduction_status(assessment):
    """Live status of the deduction linked to a Custody Damage Assessment.

    Read-only and computed on demand so the manager sees the current state of
    the Additional Salary rather than a stale stored copy.
    """
    entry = frappe.db.get_value("Custody Damage Assessment", assessment, "deduction_entry")
    if not entry:
        return {"entry": None, "status": "Not Created"}

    docstatus = frappe.db.get_value("Additional Salary", entry, "docstatus")
    if docstatus == 2:
        return {"entry": entry, "status": "Cancelled"}
    if docstatus == 0:
        return {"entry": entry, "status": "Draft"}

    # docstatus 1: Paid once a submitted Salary Slip has consumed it
    paid = frappe.db.exists(
        "Salary Detail",
        {"additional_salary": entry, "parenttype": "Salary Slip", "docstatus": 1},
    )
    return {"entry": entry, "status": "Paid" if paid else "Submitted"}


def validate(doc, method=None):
    sync_party_employee(doc)
    if not doc.items:
        frappe.throw(_("At least one damaged item is required."))
    doc.total_estimated_replacement_cost_sar = sum(
        flt(row.estimated_replacement_cost_sar) for row in doc.items
    )


def on_submit(doc, method=None):
    settings = frappe.get_single("Habitat Settings")
    if getattr(settings, "enable_damage_deduction", 0) and doc.employee:
        logger = frappe.logger()

        # [#cgz16m]
        amount = flt(doc.total_estimated_replacement_cost_sar)
        max_deduction = flt(getattr(settings, "max_damage_deduction_per_checkout_sar", 500))
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

        salary_component = settings.damage_salary_component
        if not salary_component:
            logger.warning(
                f"custody_damage_assessment.on_submit: Habitat Settings > Damage Deduction Component "
                f"is not configured. Cannot auto-generate Additional Salary for assessment {doc.name}."
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

        # back-propagate the deduction onto the originating checkout so its
        # Financials tab reflects the posted Additional Salary
        if doc.source_checkout:
            frappe.db.set_value(
                "Accommodation Checkout",
                doc.source_checkout,
                {
                    "linked_additional_salary": add_sal.name,
                    "damage_deduction_amount": add_sal.amount,
                },
            )

        logger.info(
            f"custody_damage_assessment.on_submit: Draft Additional Salary {add_sal.name} "
            f"created for assessment {doc.name}."
        )


def before_cancel(doc, method=None):
    if doc.deduction_entry:
        frappe.throw(
            _("Cannot cancel Custody Damage Assessment {0} because Additional Salary Deduction Entry {1} is already linked.").format(
                doc.name, doc.deduction_entry
            )
        )

