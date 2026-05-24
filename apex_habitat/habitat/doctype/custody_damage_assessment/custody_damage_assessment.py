"""Custody Damage Assessment controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class CustodyDamageAssessment(Document):
    pass


def validate(doc, method=None):
    if not doc.items:
        frappe.throw(_("At least one damaged item is required."))
    doc.total_estimated_replacement_cost_sar = sum(
        flt(row.estimated_replacement_cost_sar) for row in doc.items
    )


def on_submit(doc, method=None):
    settings = frappe.get_single("Habitat Settings")
    if getattr(settings, "enable_damage_deduction", 0) and doc.employee:
        logger = frappe.logger()

        # Calculate deduction amount, capped by settings limit if defined
        amount = flt(doc.total_estimated_replacement_cost_sar)
        max_deduction = flt(getattr(settings, "max_damage_deduction_per_checkout_sar", 500))
        if max_deduction > 0 and amount > max_deduction:
            amount = max_deduction

        if amount <= 0:
            logger.info(
                f"custody_damage_assessment.on_submit: Assessment {doc.name} has zero or negative cost. Skipping deduction."
            )
            return

        # Fetch company from the employee record
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

        # Validate that the configured salary component is a Deduction type
        component_type = frappe.db.get_value("Salary Component", salary_component, "type")
        if component_type != "Deduction":
            frappe.throw(_("Salary component {0} must be of type Deduction for damage assessments.").format(salary_component))

        try:
            # Create a Draft Additional Salary record
            add_sal = frappe.get_doc({
                "doctype": "Additional Salary",
                "employee": doc.employee,
                "salary_component": salary_component,
                "amount": amount,
                "payroll_date": doc.assessment_date,
                "company": company,
                "remarks": f"Deduction for custody damage assessment {doc.name}"
            })
            add_sal.insert(ignore_permissions=False)

            # Link it back to this document
            frappe.db.set_value("Custody Damage Assessment", doc.name, "deduction_entry", add_sal.name)

            logger.info(
                f"custody_damage_assessment.on_submit: Draft Additional Salary {add_sal.name} "
                f"created for assessment {doc.name}."
            )
        except Exception as e:
            frappe.db.rollback()
            frappe.log_error(
                title="Custody Damage Assessment on_submit error",
                message=frappe.get_traceback(),
            )
            logger.error(
                f"custody_damage_assessment.on_submit: Failed to create Additional Salary for assessment {doc.name}: {e}"
            )


def before_cancel(doc, method=None):
    if doc.deduction_entry:
        frappe.throw(
            _("Cannot cancel Custody Damage Assessment {0} because Additional Salary Deduction Entry {1} is already linked.").format(
                doc.name, doc.deduction_entry
            )
        )

