from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from apex.apex_core.setup import salis_support
from apex.apex_core.setup.demo import DEMO_INVENTORY, DEMO_DOCTYPES
from apex.apex_core.utils.employee_recovery import bounded_installment


APP_ROOT = Path(__file__).resolve().parents[2]


class TestBackendBoardContract(unittest.TestCase):
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
        self.assertEqual(bounded_installment(100, 50, 60), 50.0)
        self.assertEqual(bounded_installment(100, 50, 0), 0.0)
        self.assertEqual(bounded_installment(100, 50, 60, agreed=25), 25.0)

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
