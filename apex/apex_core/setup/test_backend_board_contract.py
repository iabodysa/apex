from __future__ import annotations

import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import frappe as frappe_framework
from frappe.modules import import_file as frappe_import_file

from apex.apex_core.setup import employee_advance_recovery, salis_support, setup_wizard
from apex.apex_core.setup.demo import DEMO_INVENTORY, DEMO_DOCTYPES
from apex.apex_core.utils import employee_recovery
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
            "apex_salis_support_holiday_from_date",
            "apex_salis_support_holiday_to_date",
            "apex_salis_support_weekly_off",
            "apex_salis_support_country",
            "apex_salis_support_subdivision",
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
    @patch("apex.apex_core.setup.salis_support.ensure_support_holiday_list")
    def test_setup_wizard_creates_native_calendar_before_opt_in_sla(
        self, ensure_holiday_list, configure_support_sla
    ):
        sequence = []
        ensure_holiday_list.side_effect = lambda **kwargs: (
            sequence.append("calendar") or "Saudi Support"
        )
        configure_support_sla.side_effect = lambda **kwargs: sequence.append("sla")
        setup_wizard._apply_salis_support(
            frappe_framework._dict(
                apex_enable_salis_support_sla=1,
                apex_salis_support_holiday_list="Saudi Support",
                apex_salis_support_holiday_from_date="2026-01-01",
                apex_salis_support_holiday_to_date="2026-12-31",
                apex_salis_support_weekly_off="Friday",
                apex_salis_support_country="SA",
                apex_salis_support_subdivision="01",
                apex_salis_support_workdays=["Sunday", "Monday"],
                apex_salis_support_start_time="08:00:00",
                apex_salis_support_end_time="17:00:00",
            )
        )

        ensure_holiday_list.assert_called_once_with(
            name="Saudi Support",
            from_date="2026-01-01",
            to_date="2026-12-31",
            weekly_off="Friday",
            country="SA",
            subdivision="01",
        )
        configure_support_sla.assert_called_once_with(
            enabled=True,
            holiday_list="Saudi Support",
            workdays=["Sunday", "Monday"],
            start_time="08:00:00",
            end_time="17:00:00",
        )
        self.assertEqual(sequence, ["calendar", "sla"])

    @patch.object(salis_support, "frappe")
    def test_fresh_setup_builds_native_holiday_list_with_native_generators(
        self, frappe
    ):
        handler = getattr(salis_support, "ensure_support_holiday_list", None)
        self.assertIsNotNone(handler)
        frappe.db.exists.return_value = None
        holiday_list = MagicMock(name="holiday_list")
        holiday_list.name = "Saudi Support"
        frappe.new_doc.return_value = holiday_list

        result = handler(
            name="Saudi Support",
            from_date="2026-01-01",
            to_date="2026-12-31",
            weekly_off="Friday",
            country="SA",
            subdivision="01",
        )

        self.assertEqual(result, "Saudi Support")
        self.assertEqual(holiday_list.holiday_list_name, "Saudi Support")
        self.assertEqual(holiday_list.from_date, "2026-01-01")
        self.assertEqual(holiday_list.to_date, "2026-12-31")
        self.assertEqual(holiday_list.weekly_off, "Friday")
        self.assertEqual(holiday_list.country, "SA")
        self.assertEqual(holiday_list.subdivision, "01")
        holiday_list.get_weekly_off_dates.assert_called_once_with()
        holiday_list.get_local_holidays.assert_called_once_with()
        holiday_list.insert.assert_called_once_with(ignore_permissions=True)

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

    @patch.object(employee_recovery, "frappe")
    def test_upgrade_backfills_blank_advance_snapshots_without_overwrite(self, frappe):
        handler = getattr(employee_recovery, "backfill_recovery_snapshots", None)
        self.assertIsNotNone(handler)
        frappe.get_meta.return_value.has_field.return_value = True
        frappe.get_all.return_value = [
            frappe_framework._dict(
                name="ADV-BLANK",
                custom_source_document="VI-1",
                custom_signed_evidence=None,
                custom_agreed_installment=0,
            ),
            frappe_framework._dict(
                name="ADV-POPULATED",
                custom_source_document="VI-2",
                custom_signed_evidence="SIGNED-OLD",
                custom_agreed_installment=75,
            ),
        ]
        frappe.db.get_value.return_value = frappe_framework._dict(
            worker_signature="SIGNED-1", installment_amount=125
        )

        handler()

        frappe.db.set_value.assert_called_once_with(
            "Employee Advance",
            "ADV-BLANK",
            {
                "custom_signed_evidence": "SIGNED-1",
                "custom_agreed_installment": 125.0,
            },
            update_modified=False,
        )
        self.assertIn(
            "apex.apex_core.utils.employee_recovery.backfill_recovery_snapshots",
            (APP_ROOT / "hooks.py").read_text(encoding="utf-8"),
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

    @patch.object(salis_support, "frappe")
    def test_support_switch_is_enabled_when_native_sla_already_exists(self, frappe):
        existing = SimpleNamespace(
            name="SLA-EXISTING",
            service_level=salis_support.SLA_NAME,
            enabled=1,
            document_type="Issue",
            default_service_level_agreement=1,
            apply_sla_for_resolution=1,
            default_priority="Medium",
            holiday_list="Saudi Holidays",
            priorities=[
                SimpleNamespace(
                    priority=priority,
                    response_time=response,
                    resolution_time=resolution,
                    default_priority=is_default,
                )
                for priority, response, resolution, is_default in salis_support.SLA_PRIORITIES
            ],
            support_and_resolution=[
                SimpleNamespace(
                    workday="Sunday", start_time="08:00:00", end_time="17:00:00"
                )
            ],
            sla_fulfilled_on=[
                SimpleNamespace(status="Resolved"),
                SimpleNamespace(status="Closed"),
            ],
        )
        frappe.db.exists.side_effect = [True, "SLA-EXISTING"]
        frappe.get_doc.return_value = existing

        result = salis_support.configure_support_sla(
            enabled=True,
            holiday_list="Saudi Holidays",
            workdays=["Sunday"],
            start_time="08:00:00",
            end_time="17:00:00",
        )

        self.assertEqual(result, "SLA-EXISTING")
        frappe.db.set_single_value.assert_called_once_with(
            "Support Settings", "track_service_level_agreement", 1
        )
        frappe.new_doc.assert_not_called()

    @patch.object(salis_support, "_", side_effect=lambda message: message)
    @patch.object(salis_support, "frappe")
    def test_named_sla_collision_fails_closed_without_overwrite(
        self, frappe, _translate
    ):
        frappe.throw.side_effect = frappe_framework.ValidationError
        frappe.db.exists.side_effect = [True, "SLA-EXISTING"]
        frappe.get_doc.return_value = SimpleNamespace(
            name="SLA-EXISTING",
            service_level=salis_support.SLA_NAME,
            enabled=0,
            document_type="Issue",
            default_service_level_agreement=1,
            apply_sla_for_resolution=1,
            default_priority="Medium",
            holiday_list="Different Calendar",
            priorities=[],
            support_and_resolution=[],
            sla_fulfilled_on=[],
        )

        with self.assertRaises(frappe_framework.ValidationError):
            salis_support.configure_support_sla(
                enabled=True,
                holiday_list="Saudi Holidays",
                workdays=["Sunday"],
                start_time="08:00:00",
                end_time="17:00:00",
            )

        frappe.db.set_single_value.assert_not_called()
        frappe.db.set_value.assert_not_called()
        frappe.new_doc.assert_not_called()

    @patch.object(salis_support, "_", side_effect=lambda message: message)
    @patch.object(salis_support, "frappe")
    def test_fresh_sla_fails_closed_when_a_required_priority_is_missing(
        self, frappe, _translate
    ):
        frappe.throw.side_effect = frappe_framework.ValidationError

        def exists(doctype, name_or_filters=None):
            if doctype == "Holiday List":
                return True
            if doctype == "Service Level Agreement":
                return False
            if doctype == "Issue Priority":
                return name_or_filters != "Urgent"
            return False

        frappe.db.exists.side_effect = exists

        with self.assertRaises(frappe_framework.ValidationError):
            salis_support.configure_support_sla(
                enabled=True,
                holiday_list="Support Calendar",
                workdays=["Sunday"],
                start_time="08:00:00",
                end_time="17:00:00",
            )

        frappe.new_doc.assert_not_called()
        frappe.db.set_single_value.assert_not_called()

    @patch.object(converge_patch, "frappe")
    def test_referenced_legacy_sla_is_disabled_and_retained(self, frappe):
        legacy = SimpleNamespace(
            name=salis_support.SLA_NAME,
            holiday_list="Apex Support 24x7",
            priorities=[
                SimpleNamespace(
                    priority=priority,
                    response_time=response,
                    resolution_time=resolution,
                    default_priority=is_default,
                )
                for priority, response, resolution, is_default in salis_support.SLA_PRIORITIES
            ],
            support_and_resolution=[
                SimpleNamespace(workday=day, start_time="00:00:00", end_time="23:59:59")
                for day in converge_patch._LEGACY_DAYS
            ],
            sla_fulfilled_on=[
                SimpleNamespace(status="Resolved"),
                SimpleNamespace(status="Closed"),
            ],
        )
        frappe.db.get_value.return_value = salis_support.SLA_NAME
        frappe.get_doc.return_value = legacy
        frappe.db.exists.return_value = "ISS-1"

        converge_patch._retire_untouched_legacy_sla()

        frappe.db.set_value.assert_called_once_with(
            "Service Level Agreement",
            salis_support.SLA_NAME,
            "enabled",
            0,
            update_modified=False,
        )
        frappe.delete_doc.assert_not_called()

    @patch.object(converge_patch, "_delete_unused_legacy_holiday_list")
    @patch.object(converge_patch, "frappe")
    def test_non_issue_link_disables_and_retains_legacy_sla(
        self, frappe, delete_legacy_holiday_list
    ):
        legacy = SimpleNamespace(
            name=salis_support.SLA_NAME,
            holiday_list="Apex Support 24x7",
            priorities=[
                SimpleNamespace(
                    priority=priority,
                    response_time=response,
                    resolution_time=resolution,
                    default_priority=is_default,
                )
                for priority, response, resolution, is_default in salis_support.SLA_PRIORITIES
            ],
            support_and_resolution=[
                SimpleNamespace(
                    workday=day,
                    start_time="00:00:00",
                    end_time="23:59:59",
                )
                for day in converge_patch._LEGACY_DAYS
            ],
            sla_fulfilled_on=[
                SimpleNamespace(status="Resolved"),
                SimpleNamespace(status="Closed"),
            ],
        )
        frappe.LinkExistsError = frappe_framework.LinkExistsError
        frappe.db.get_value.return_value = salis_support.SLA_NAME
        frappe.get_doc.return_value = legacy
        frappe.db.exists.return_value = None
        frappe.delete_doc.side_effect = frappe_framework.LinkExistsError(
            "linked from a non-Issue document"
        )

        converge_patch._retire_untouched_legacy_sla()

        frappe.delete_doc.assert_called_once_with(
            "Service Level Agreement",
            salis_support.SLA_NAME,
            ignore_permissions=True,
        )
        frappe.db.set_value.assert_called_once_with(
            "Service Level Agreement",
            salis_support.SLA_NAME,
            "enabled",
            0,
            update_modified=False,
        )
        delete_legacy_holiday_list.assert_not_called()

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
        self.assertTrue(all(row["modified"].startswith("2000-") for row in issue_types))
        self.assertTrue(all(row["modified"].startswith("2000-") for row in priorities))

    def test_native_fixture_timestamp_preserves_older_operator_edit_and_seeds_fresh(
        self,
    ):
        fixture = APP_ROOT / "fixtures" / "issue_type.json"
        with (
            patch.object(frappe_import_file, "frappe") as frappe,
            patch.object(frappe_import_file, "import_doc") as import_doc,
            patch.object(frappe_import_file, "update_modified"),
        ):
            frappe.db.get_value.return_value = "2026-08-13 00:00:00.000000"
            frappe_import_file.import_file_by_path(str(fixture))
            import_doc.assert_not_called()

            frappe.db.get_value.return_value = None
            frappe_import_file.import_file_by_path(str(fixture))
            self.assertEqual(import_doc.call_count, 6)

    @patch.object(converge_patch, "frappe")
    def test_residue_repair_only_normalizes_blank_bed_status(self, frappe):
        frappe.db.table_exists.return_value = True

        def get_all(doctype, filters=None, **kwargs):
            if doctype == "Bed" and filters == {"status": ["is", "not set"]}:
                return ["BED-BLANK"]
            if doctype == "Bed":
                return ["BED-INVALID"]
            return []

        frappe.get_all.side_effect = get_all
        frappe.db.exists.return_value = None

        converge_patch._repair_demo_import_residue()

        self.assertEqual(
            frappe.db.set_value.call_args_list,
            [
                call(
                    "Dispatch Trip",
                    {"naming_series": "TRIP-DEMO-.##"},
                    "naming_series",
                    "DT-.######",
                    update_modified=False,
                ),
                call(
                    "Bed",
                    "BED-BLANK",
                    "status",
                    "Available",
                    update_modified=False,
                ),
            ],
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
                "custom_signed_evidence",
                "custom_agreed_installment",
            },
        )
        by_name = {row["fieldname"]: row for row in customization["custom_fields"]}
        for fieldname in ("custom_signed_evidence", "custom_agreed_installment"):
            self.assertEqual(by_name[fieldname]["read_only"], 1)
            self.assertEqual(by_name[fieldname]["no_copy"], 1)

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
