"""Custody Damage Assessment controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class CustodyDamageAssessment(Document):
    def before_save(self):
        # Validate document properties
        if self.doctype != "Custody Damage Assessment":
            frappe.throw("DocType mismatch")


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

        # Use ONLY an explicitly damage-named Deduction component. The previous
        # fallback to "any Deduction component" was unsafe — it could deduct
        # under an unrelated payroll component. If no damage component exists,
        # skip creation rather than guessing.
        salary_component = frappe.db.get_value(
            "Salary Component",
            {"type": "Deduction", "name": ["like", "%damage%"]},
            "name"
        )

        if not salary_component:
            logger.warning(
                f"custody_damage_assessment.on_submit: No damage-specific Deduction Salary Component found. "
                f"Cannot auto-generate Additional Salary deduction entry for assessment {doc.name}. "
                f"Create a Deduction component whose name contains 'damage' first."
            )
            return

        try:
            # Create a Draft Additional Salary record
            add_sal = frappe.get_doc({
                "doctype": "Additional Salary",
                "employee": doc.employee,
                "salary_component": salary_component,
                "type": "Deduction",
                "amount": amount,
                "payroll_date": doc.assessment_date,
                "company": company,
                "remarks": f"Deduction for custody damage assessment {doc.name}"
            })
            add_sal.insert(ignore_permissions=True)

            # Link it back to this document
            frappe.db.set_value("Custody Damage Assessment", doc.name, "deduction_entry", add_sal.name)

            logger.info(
                f"custody_damage_assessment.on_submit: Draft Additional Salary {add_sal.name} "
                f"created for assessment {doc.name}."
            )
        except Exception as e:
            print(f"CUSTODY DAMAGE ON_SUBMIT EXCEPTION: {e}")
            import traceback
            traceback.print_exc()
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

