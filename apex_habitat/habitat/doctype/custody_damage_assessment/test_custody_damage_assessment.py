import frappe
from frappe.tests.utils import FrappeTestCase

# [#8evoal]
test_ignore = [
    "Additional Salary",
    "Asset",
    "Asset Movement",
    "Company",
    "Cost Center",
    "Currency",
    "Employee",
    "Item",
    "Payment Entry",
    "Project",
    "Purchase Invoice",
    "Role",
    "Salary Component",
    "Supplier",
    "User",
]


class TestCustodyDamageAssessment(FrappeTestCase):

    def test_create_valid_assessment(self):
        doc = frappe.get_doc({
            "doctype": "Custody Damage Assessment",
            "naming_series": "CUST-DMG-.YYYY.-.####",
            "assessment_date": "2026-07-10",
            "building": "QA-BLDG",
            "items": [{"doctype": "Custody Damage Item", "article": "QA-ART",
                        "damage_description": "cracked", "estimated_replacement_cost_sar": 150}],
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertIsNotNone(doc.name)
        frappe.delete_doc("Custody Damage Assessment", doc.name, force=True, ignore_permissions=True)

    def test_missing_assessment_date_raises(self):
        doc = frappe.get_doc({
            "doctype": "Custody Damage Assessment",
            "naming_series": "CUST-DMG-.YYYY.-.####",
            "building": "QA-BLDG",
        })
        with self.assertRaises(frappe.exceptions.ValidationError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_empty_items_raises(self):
        from apex_habitat.habitat.doctype.custody_damage_assessment.custody_damage_assessment import validate

        doc = frappe.get_doc({
            "doctype": "Custody Damage Assessment",
            "assessment_date": "2026-07-10",
            "building": "QA-BLDG",
            "items": [],
        })
        with self.assertRaises(frappe.ValidationError):
            validate(doc)

    def test_deduction_status_not_created_when_no_entry(self):
        """No linked Additional Salary -> 'Not Created' so the manager can tell
        the deduction never flowed (disabled / below threshold)."""
        from apex_habitat.habitat.doctype.custody_damage_assessment.custody_damage_assessment import (
            get_deduction_status,
        )

        doc = frappe.get_doc({
            "doctype": "Custody Damage Assessment",
            "naming_series": "CUST-DMG-.YYYY.-.####",
            "assessment_date": "2026-07-10",
            "building": "QA-BLDG",
            "items": [{"doctype": "Custody Damage Item", "article": "QA-ART",
                        "damage_description": "cracked", "estimated_replacement_cost_sar": 150}],
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        result = get_deduction_status(doc.name)
        self.assertIsNone(result["entry"])
        self.assertEqual(result["status"], "Not Created")
        frappe.delete_doc("Custody Damage Assessment", doc.name, force=True, ignore_permissions=True)

    def test_deduction_status_reflects_additional_salary_docstatus(self):
        """A linked draft Additional Salary reports 'Draft'; the indicator
        reflects the linked record's live docstatus, not a stored copy."""
        from apex_habitat.habitat.doctype.custody_damage_assessment.custody_damage_assessment import (
            get_deduction_status,
        )

        company = frappe.db.get_value("Company", {}, "name") or "_Test Company"
        component = "QA-DMG-" + frappe.generate_hash(length=8)
        salary_component = frappe.get_doc({
            "doctype": "Salary Component",
            "salary_component": component,
            "type": "Deduction",
        }).insert(ignore_permissions=True, ignore_if_duplicate=True)

        add_sal = frappe.get_doc({
            "doctype": "Additional Salary",
            "employee": "QA-EMP",
            "salary_component": salary_component.name,
            "amount": 150,
            "payroll_date": "2026-07-10",
            "company": company,
            "currency": "SAR",
        })
        # ignore_validate skips the HRMS date/joining checks (no Employee chain
        # provisioned); keeps a real linked record to read docstatus from.
        add_sal.flags.ignore_validate = True
        add_sal.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)

        doc = frappe.get_doc({
            "doctype": "Custody Damage Assessment",
            "naming_series": "CUST-DMG-.YYYY.-.####",
            "assessment_date": "2026-07-10",
            "building": "QA-BLDG",
            "deduction_entry": add_sal.name,
            "items": [{"doctype": "Custody Damage Item", "article": "QA-ART",
                        "damage_description": "cracked", "estimated_replacement_cost_sar": 150}],
        })
        doc.insert(ignore_permissions=True, ignore_links=True)

        result = get_deduction_status(doc.name)
        self.assertEqual(result["entry"], add_sal.name)
        self.assertEqual(result["status"], "Draft")

        frappe.delete_doc("Custody Damage Assessment", doc.name, force=True, ignore_permissions=True)
        frappe.delete_doc("Additional Salary", add_sal.name, force=True, ignore_permissions=True)

    def test_additional_salary_insert_ignores_permissions(self):
        """Regression (bug #3): the system-generated Additional Salary deduction
        must insert with ignore_permissions=True so a non-HR submitter (e.g. a
        Housing Supervisor) is not blocked by lacking Additional Salary create
        rights — the whole submit would otherwise abort atomically. It stays
        auditable: drafted, logged, and linked back via deduction_entry."""
        import inspect
        from apex_habitat.habitat.doctype.custody_damage_assessment import (
            custody_damage_assessment as mod,
        )
        source = inspect.getsource(mod.on_submit)
        self.assertIn("ignore_permissions=True", source)
        self.assertNotIn("ignore_permissions=False", source)
