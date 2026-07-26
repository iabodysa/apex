# Copyright (c) 2026, AFMCO and contributors
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
                        "damage_description": "cracked", "estimated_replacement_cost": 150}],
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
        from apex.habitat.doctype.custody_damage_assessment.custody_damage_assessment import validate

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
        from apex.habitat.doctype.custody_damage_assessment.custody_damage_assessment import (
            get_deduction_status,
        )

        doc = frappe.get_doc({
            "doctype": "Custody Damage Assessment",
            "naming_series": "CUST-DMG-.YYYY.-.####",
            "assessment_date": "2026-07-10",
            "building": "QA-BLDG",
            "items": [{"doctype": "Custody Damage Item", "article": "QA-ART",
                        "damage_description": "cracked", "estimated_replacement_cost": 150}],
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        result = get_deduction_status(doc.name)
        self.assertIsNone(result["entry"])
        self.assertEqual(result["status"], "Not Created")
        frappe.delete_doc("Custody Damage Assessment", doc.name, force=True, ignore_permissions=True)

    def test_deduction_status_reflects_additional_salary_docstatus(self):
        """A linked draft Additional Salary reports 'Draft'; the indicator
        reflects the linked record's live docstatus, not a stored copy."""
        from apex.habitat.doctype.custody_damage_assessment.custody_damage_assessment import (
            get_deduction_status,
        )

        company = frappe.db.get_value("Company", {}, "name") or "_Test Company"
        component = "QA-DMG-" + frappe.generate_hash(length=12)
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
        # [#q21w72]
        add_sal.flags.ignore_validate = True
        add_sal.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)

        doc = frappe.get_doc({
            "doctype": "Custody Damage Assessment",
            "naming_series": "CUST-DMG-.YYYY.-.####",
            "assessment_date": "2026-07-10",
            "building": "QA-BLDG",
            "deduction_entry": add_sal.name,
            "items": [{"doctype": "Custody Damage Item", "article": "QA-ART",
                        "damage_description": "cracked", "estimated_replacement_cost": 150}],
        })
        doc.insert(ignore_permissions=True, ignore_links=True)

        result = get_deduction_status(doc.name)
        self.assertEqual(result["entry"], add_sal.name)
        self.assertEqual(result["status"], "Draft")

        frappe.delete_doc("Custody Damage Assessment", doc.name, force=True, ignore_permissions=True)
        frappe.delete_doc("Additional Salary", add_sal.name, force=True, ignore_permissions=True)

    def test_additional_salary_insert_ignores_permissions(self):
        """Regression (bug #3): a non-HR submitter (e.g. a Housing Supervisor) has no
        Additional Salary create right, so a permission-checked insert would abort the
        whole submit atomically. The system-generated deduction must post anyway, and
        stay auditable — drafted, logged, and linked back via deduction_entry.

        Asserted as an OUTCOME rather than as a keyword in the source: on_submit runs
        against a frappe whose insert REFUSES any permission-checked write, so the
        test passes only if the deduction still lands and still gets linked back.
        Reformatting or relocating the insert stays green; making it permission-
        checked — the actual regression — does not.
        """
        from unittest.mock import MagicMock, patch
        from apex.habitat.doctype.custody_damage_assessment import (
            custody_damage_assessment as mod,
        )
        posted, linked = [], []
        add_sal = MagicMock()
        add_sal.name = "QA-ADD-SAL"
        add_sal.amount = 150

        def refuse_unless_bypassed(**kwargs):
            if not kwargs.get("ignore_permissions"):
                raise frappe.PermissionError("submitter holds no Additional Salary create right")
            posted.append(kwargs)
        add_sal.insert.side_effect = refuse_unless_bypassed

        lookups = {"Employee": "QA Company", "Salary Component": "Deduction"}
        stub = MagicMock()
        stub.get_doc.return_value = add_sal
        stub.db.get_value.side_effect = lambda doctype, _name, _field: lookups[doctype]
        stub.db.set_value.side_effect = lambda *args: linked.append(args)
        rule = frappe._dict(cap_amount_per_event=0, salary_component="QA-DMG-COMPONENT")
        doc = frappe._dict(name="QA-CDA", employee="QA-EMP", deduction_entry=None,
                           assessment_date="2026-07-10", source_checkout=None,
                           total_estimated_replacement_cost=150)

        with patch.object(mod, "frappe", stub), \
                patch.object(mod, "get_damage_rule", lambda: rule):
            mod.on_submit(doc)

        self.assertTrue(posted, "the deduction must post despite the submitter's missing rights")
        self.assertIn(
            ("Custody Damage Assessment", "QA-CDA", "deduction_entry", "QA-ADD-SAL"), linked,
            "the posted deduction must stay auditable — linked back via deduction_entry",
        )

    def test_get_deduction_status_denied_without_cda_read(self):
        """IDOR: the whitelisted get_deduction_status must gate per-doc
        read. A user with none of the CDA-read roles raises PermissionError so
        they cannot probe another worker's deduction status; a manager (here
        Administrator, who short-circuits has_permission) still gets the dict."""
        from apex.habitat.doctype.custody_damage_assessment.custody_damage_assessment import (
            get_deduction_status,
        )

        doc = frappe.get_doc({
            "doctype": "Custody Damage Assessment",
            "naming_series": "CUST-DMG-.YYYY.-.####",
            "assessment_date": "2026-07-10",
            "building": "QA-BLDG",
            "items": [{"doctype": "Custody Damage Item", "article": "QA-ART",
                        "damage_description": "cracked", "estimated_replacement_cost": 150}],
        })
        doc.insert(ignore_permissions=True, ignore_links=True)

        # [#8i5bel]
        email = "qa-cda-noread-" + frappe.generate_hash(length=12) + "@example.com"
        no_read_user = frappe.get_doc({
            "doctype": "User",
            "email": email,
            "first_name": "QA NoRead",
            "send_welcome_email": 0,
            "roles": [],
        }).insert(ignore_permissions=True)

        try:
            frappe.set_user(no_read_user.name)
            with self.assertRaises(frappe.PermissionError):
                get_deduction_status(doc.name)
        finally:
            frappe.set_user("Administrator")

        # [#dq2kjr]
        result = get_deduction_status(doc.name)
        self.assertEqual(result["status"], "Not Created")

        frappe.delete_doc("Custody Damage Assessment", doc.name, force=True, ignore_permissions=True)
        frappe.delete_doc("User", no_read_user.name, force=True, ignore_permissions=True)

    def test_on_submit_is_idempotent_single_additional_salary(self):
        """A re-fired on_submit must not post a second Additional Salary.
        Calling the side-effect twice creates exactly one for the assessment;
        the second call returns early on the populated deduction_entry."""
        from apex.habitat.doctype.custody_damage_assessment.custody_damage_assessment import (
            on_submit,
        )

        company = frappe.db.get_value("Company", {}, "name") or "_Test Company"
        component = "QA-DMG-" + frappe.generate_hash(length=12)
        salary_component = frappe.get_doc({
            "doctype": "Salary Component",
            "salary_component": component,
            "type": "Deduction",
        }).insert(ignore_permissions=True, ignore_if_duplicate=True)

        # [#lxzelf]
        policy = frappe.get_single("Salary Deduction Policy")
        prev_enabled = policy.enable_salary_deductions
        damage = next((r for r in policy.type_rules or [] if r.deduction_type == "Damage"), None)
        if damage is None:
            damage = policy.append("type_rules", {"deduction_type": "Damage"})
        prev_component = damage.salary_component
        policy.enable_salary_deductions = 1
        policy.global_max_percent_of_salary = 50
        damage.enabled = 1
        damage.salary_component = salary_component.name
        policy.save(ignore_permissions=True)

        # [#qiwt5g]
        emp = frappe.get_doc({
            "doctype": "Employee",
            "first_name": "QA Custody " + frappe.generate_hash(length=12),
            "company": company,
            "gender": "Male",
            "date_of_birth": "1990-01-01",
            "date_of_joining": "2020-01-01",
            "status": "Active",
        })
        emp.insert(ignore_permissions=True, ignore_links=True)

        # [#qx9yid]
        earn_component = "QA-DMG-Earn-" + frappe.generate_hash(length=12)
        frappe.get_doc({
            "doctype": "Salary Component",
            "salary_component": earn_component,
            "type": "Earning",
        }).insert(ignore_permissions=True, ignore_if_duplicate=True)
        struct_name = "QA-DMG-Struct-" + frappe.generate_hash(length=12)
        struct = frappe.get_doc({
            "doctype": "Salary Structure",
            "name": struct_name,
            "salary_structure_name": struct_name,
            "company": company,
            "currency": "SAR",
            "is_active": "Yes",
            "payroll_frequency": "Monthly",
            "earnings": [{"salary_component": earn_component, "amount": 1000.0}],
        })
        struct.insert(ignore_permissions=True)
        struct.submit()
        assignment = frappe.get_doc({
            "doctype": "Salary Structure Assignment",
            "employee": emp.name,
            "salary_structure": struct.name,
            "from_date": "2026-01-01",
            "company": company,
            "currency": "SAR",
            "base": 1000.0,
        })
        assignment.insert(ignore_permissions=True)
        assignment.submit()

        doc = frappe.get_doc({
            "doctype": "Custody Damage Assessment",
            "naming_series": "CUST-DMG-.YYYY.-.####",
            "assessment_date": "2026-07-10",
            "building": "QA-BLDG",
            "employee": emp.name,
            "items": [{"doctype": "Custody Damage Item", "article": "QA-ART",
                        "damage_description": "cracked", "estimated_replacement_cost": 150}],
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        # [#5wi15n]
        doc.total_estimated_replacement_cost = 150

        # [#d8kcf9]
        as_filters = {
            "employee": emp.name,
            "salary_component": salary_component.name,
            "payroll_date": doc.assessment_date,
        }
        try:
            on_submit(doc)
            # [#55e5jo]
            doc.reload()
            self.assertTrue(doc.deduction_entry, "first on_submit must post one Additional Salary")
            on_submit(doc)

            self.assertEqual(
                frappe.db.count("Additional Salary", as_filters), 1,
                "a re-fired on_submit must not post a second Additional Salary",
            )
        finally:
            for row in frappe.get_all("Additional Salary", filters=as_filters):
                frappe.delete_doc("Additional Salary", row.name, force=True, ignore_permissions=True)
            frappe.delete_doc("Custody Damage Assessment", doc.name, force=True, ignore_permissions=True)
            # [#m1ayrq]
            frappe.get_doc("Salary Structure Assignment", assignment.name).cancel()
            frappe.delete_doc("Salary Structure Assignment", assignment.name, force=True, ignore_permissions=True)
            frappe.get_doc("Salary Structure", struct.name).cancel()
            frappe.delete_doc("Salary Structure", struct.name, force=True, ignore_permissions=True)
            frappe.delete_doc("Employee", emp.name, force=True, ignore_permissions=True)
            policy = frappe.get_single("Salary Deduction Policy")
            policy.enable_salary_deductions = prev_enabled
            damage = next((r for r in policy.type_rules or [] if r.deduction_type == "Damage"), None)
            if damage is not None:
                damage.enabled = prev_enabled
                damage.salary_component = prev_component
            policy.flags.ignore_validate = True
            policy.save(ignore_permissions=True)
