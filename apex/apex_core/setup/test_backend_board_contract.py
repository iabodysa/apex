from __future__ import annotations

import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import frappe as frappe_framework

from apex.apex_core.setup import employee_advance_recovery, salis_support, setup_wizard
from apex.apex_core.setup.demo import DEMO_INVENTORY, DEMO_DOCTYPES
from apex.apex_core.utils.employee_recovery import bounded_installment
from apex.patches.v2_6 import converge_native_support_and_recovery as converge_patch


APP_ROOT = Path(__file__).resolve().parents[2]


class TestBackendBoardContract(unittest.TestCase):
    def test_setup_wizard_exposes_native_recovery_and_opt_in_sla(self):
        wizard = (APP_ROOT / "public" / "js" / "apex_setup_wizard.js").read_text(
            encoding="utf-8"
        )
        for fieldname in (
            "apex_enable_employee_advance_recovery",
            "apex_employee_advance_recovery_component",
            "apex_employee_advance_recovery_max_percent",
            "apex_enable_salis_support_sla",
            "apex_salis_support_holiday_list",
            "apex_salis_support_workdays",
            "apex_salis_support_start_time",
            "apex_salis_support_end_time",
        ):
            self.assertIn(fieldname, wizard)
        self.assertNotIn("apex_deduct_housing_allowance", wizard)
        self.assertNotIn("apex_deduct_damage", wizard)
        self.assertNotIn("Salary Deduction Policy", wizard)

    @patch("apex.apex_core.setup.employee_advance_recovery.configure_recovery")
    def test_setup_wizard_sends_native_recovery_answers(self, configure_recovery):
        setup_wizard._apply_employee_advance_recovery(
            frappe_framework._dict(
                apex_enable_employee_advance_recovery=1,
                apex_employee_advance_recovery_component="Recovery",
                apex_employee_advance_recovery_max_percent=40,
            ),
            "Company A",
        )

        configure_recovery.assert_called_once_with(
            enabled=True,
            company="Company A",
            salary_component="Recovery",
            max_percent=40,
        )

    @patch("apex.apex_core.setup.salis_support.configure_support_sla")
    def test_setup_wizard_sends_opt_in_support_schedule(self, configure_support_sla):
        setup_wizard._apply_salis_support(
            frappe_framework._dict(
                apex_enable_salis_support_sla=1,
                apex_salis_support_holiday_list="Saudi Holidays",
                apex_salis_support_workdays=["Sunday", "Monday"],
                apex_salis_support_start_time="08:00:00",
                apex_salis_support_end_time="17:00:00",
            )
        )

        configure_support_sla.assert_called_once_with(
            enabled=True,
            holiday_list="Saudi Holidays",
            workdays=["Sunday", "Monday"],
            start_time="08:00:00",
            end_time="17:00:00",
        )

    @patch.object(employee_advance_recovery, "_", side_effect=lambda message: message)
    @patch.object(employee_advance_recovery, "frappe")
    def test_recovery_configuration_rejects_zero_and_more_than_fifty_percent(
        self, frappe, _translate
    ):
        frappe.throw.side_effect = frappe_framework.ValidationError

        for value in (0, 50.01):
            with self.subTest(value=value), self.assertRaises(
                frappe_framework.ValidationError
            ):
                employee_advance_recovery.configure_recovery(max_percent=value)

    @patch.object(converge_patch, "configure_recovery")
    @patch.object(converge_patch, "frappe")
    def test_failed_recovery_conversion_preserves_legacy_policy(
        self, frappe, configure_recovery
    ):
        frappe.db.table_exists.return_value = True
        frappe.db.get_single_value.side_effect = [1, 40, None, "Company A"]
        frappe.db.get_value.return_value = SimpleNamespace(
            enabled=1, salary_component="Recovery"
        )
        configure_recovery.side_effect = RuntimeError("invalid account")

        with self.assertRaises(RuntimeError):
            converge_patch._migrate_deduction_policy()

        frappe.delete_doc.assert_not_called()

    @patch.object(converge_patch, "frappe")
    def test_upgrade_removes_only_redundant_employee_advance_fields(self, frappe):
        frappe.db.get_value.side_effect = ["CF-EVIDENCE", "CF-INSTALLMENT"]

        converge_patch._remove_redundant_employee_advance_fields()

        self.assertEqual(
            frappe.delete_doc.call_args_list,
            [
                call(
                    "Custom Field",
                    "CF-EVIDENCE",
                    ignore_permissions=True,
                    force=True,
                ),
                call(
                    "Custom Field",
                    "CF-INSTALLMENT",
                    ignore_permissions=True,
                    force=True,
                ),
            ],
        )

    @patch.object(converge_patch, "frappe")
    def test_select_audit_includes_single_values(self, frappe):
        field = SimpleNamespace(fieldname="mode", options="Good\nBad")
        meta = SimpleNamespace(
            issingle=True,
            get=lambda key, filters=None: [field] if key == "fields" else None,
        )
        frappe.get_all.return_value = ["Salis Settings"]
        frappe.get_meta.return_value = meta
        frappe.db.get_single_value.return_value = "Broken"
        frappe.throw.side_effect = frappe_framework.ValidationError

        with self.assertRaises(frappe_framework.ValidationError):
            converge_patch._assert_select_consistency()

        self.assertIn("Salis Settings.mode='Broken'", frappe.throw.call_args.args[0])

    @patch.object(converge_patch, "frappe")
    def test_select_audit_includes_child_table_values(self, frappe):
        field = SimpleNamespace(fieldname="result", options="Pass\nFail")
        meta = SimpleNamespace(
            issingle=False,
            istable=True,
            get=lambda key, filters=None: [field] if key == "fields" else None,
        )
        frappe.get_all.side_effect = [
            ["Inspection Row"],
            [{"result": "Unknown"}],
        ]
        frappe.get_meta.return_value = meta
        frappe.throw.side_effect = frappe_framework.ValidationError

        with self.assertRaises(frappe_framework.ValidationError):
            converge_patch._assert_select_consistency()

        self.assertIn("Inspection Row.result='Unknown'", frappe.throw.call_args.args[0])

    @patch.object(salis_support, "frappe")
    def test_support_switch_is_enabled_before_native_sla_validation(self, frappe):
        sequence = []
        frappe.db.exists.side_effect = lambda doctype, _filters=None: (
            doctype in {"Holiday List", "Issue Priority"}
        )
        frappe.db.set_single_value.side_effect = lambda *args: sequence.append("switch")
        sla = MagicMock(name="sla")
        sla.name = "Salis Support SLA"
        sla.insert.side_effect = lambda **kwargs: sequence.append("insert")
        frappe.new_doc.return_value = sla

        salis_support.configure_support_sla(
            enabled=True,
            holiday_list="Saudi Holidays",
            workdays=["Sunday"],
            start_time="08:00:00",
            end_time="17:00:00",
        )

        self.assertEqual(sequence, ["switch", "insert"])
        sla.insert.assert_called_once_with(ignore_permissions=True)

    def test_salis_issue_masters_are_native_fixtures(self):
        hooks = (APP_ROOT / "hooks.py").read_text(encoding="utf-8")
        self.assertIn('"dt": "Issue Type"', hooks)
        self.assertIn('"dt": "Issue Priority"', hooks)
        self.assertNotIn("seeders.salis_issue_seed", hooks)

        issue_types = json.loads(
            (APP_ROOT / "fixtures" / "issue_type.json").read_text(encoding="utf-8")
        )
        priorities = json.loads(
            (APP_ROOT / "fixtures" / "issue_priority.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            {row["name"] for row in issue_types},
            {"Vehicle", "Fuel", "Attendance", "Salary", "Complaint", "Other"},
        )
        self.assertEqual(
            {row["name"] for row in priorities}, {"Low", "Medium", "High", "Urgent"}
        )

    def test_demo_inventory_exactly_covers_every_cleanup_doctype(self):
        self.assertEqual(
            set(DEMO_INVENTORY),
            set(DEMO_DOCTYPES) | {"User", "Contact", "User Permission"},
        )
        for doctype, contract in DEMO_INVENTORY.items():
            self.assertEqual(contract["target_scenarios"], 3, doctype)
            self.assertGreaterEqual(contract["observed_scenarios"], 1, doctype)
            if contract["observed_scenarios"] < contract["target_scenarios"]:
                self.assertTrue(contract.get("gap"), doctype)

    def test_employee_recovery_uses_currency_precision_without_site_defaults(self):
        self.assertEqual(bounded_installment(100, 50), 50.0)
        self.assertEqual(bounded_installment(100, 0), 0.0)
        self.assertEqual(bounded_installment(100, 50, agreed=25), 25.0)

    def test_employee_advance_customization_is_the_minimum_owned_contract(self):
        customization = json.loads(
            (APP_ROOT / "apex_core" / "custom" / "employee_advance.json").read_text(
                encoding="utf-8"
            )
        )
        data_fields = {
            row["fieldname"]
            for row in customization["custom_fields"]
            if row["fieldtype"] not in {"Section Break", "Column Break"}
        }
        self.assertEqual(
            data_fields,
            {
                "custom_source_doctype",
                "custom_source_document",
            },
        )

    def test_no_demo_data_import_mode_or_bespoke_policy_runtime(self):
        python_sources = "\n".join(
            path.read_text(encoding="utf-8")
            for path in APP_ROOT.rglob("*.py")
            if "test_backend_board_contract.py" not in str(path)
            and "/patches/" not in str(path)
        )
        self.assertNotIn("flags.in_import", python_sources)
        self.assertNotIn("Salary Deduction Policy", python_sources)
        self.assertFalse(
            list((APP_ROOT / "apex_core" / "doctype" / "salary_deduction_policy").glob("*.*"))
        )
        self.assertFalse(
            list((APP_ROOT / "apex_core" / "doctype" / "salary_deduction_type_rule").glob("*.*"))
        )


if __name__ == "__main__":
    unittest.main()
