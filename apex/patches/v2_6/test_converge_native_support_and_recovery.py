import importlib
from pathlib import Path
from unittest.mock import patch

from frappe.tests.utils import FrappeTestCase

from apex.patches.v2_6 import converge_native_support_and_recovery as convergence


APP_ROOT = Path(__file__).resolve().parents[2]


class TestNativeSupportAndRecoveryConvergence(FrappeTestCase):
    def test_untouched_legacy_utility_card_merges_into_canonical_card(self):
        retire = getattr(convergence, "_retire_untouched_legacy_utility_card", None)
        self.assertIsNotNone(retire)

        legacy = {
            "label": "Disputed Utility Bills",
            "document_type": "Utility Bill Entry",
            "function": "Count",
            "is_public": 1,
            "show_percentage_stats": 1,
            "stats_time_interval": "Daily",
            "type": "Document Type",
            "module": "Habitat",
            "filters_json": '[["Utility Bill Entry", "status", "=", "Disputed"]]',
            "is_standard": 1,
        }

        with (
            patch.object(convergence.frappe.db, "exists", side_effect=[True, True]),
            patch.object(convergence.frappe.db, "get_value", return_value=legacy),
            patch.object(convergence.frappe, "rename_doc") as rename_doc,
        ):
            retire()

        rename_doc.assert_called_once_with(
            "Number Card",
            "Disputed Utility Bills",
            "Rejected Utility Bills",
            force=True,
            merge=True,
            ignore_permissions=True,
            show_alert=False,
        )

    def test_customized_legacy_utility_card_is_preserved(self):
        retire = getattr(convergence, "_retire_untouched_legacy_utility_card", None)
        self.assertIsNotNone(retire)

        with (
            patch.object(convergence.frappe.db, "exists", return_value=True),
            patch.object(
                convergence.frappe.db,
                "get_value",
                return_value={"label": "My Utility Exceptions"},
            ),
            patch.object(convergence.frappe, "rename_doc") as rename_doc,
        ):
            retire()

        rename_doc.assert_not_called()

    def test_renamed_legacy_utility_card_receives_canonical_values(self):
        legacy = dict(convergence._LEGACY_UTILITY_CARD_VALUES)

        with (
            patch.object(convergence.frappe.db, "exists", side_effect=[True, False]),
            patch.object(convergence.frappe.db, "get_value", return_value=legacy),
            patch.object(convergence.frappe, "rename_doc") as rename_doc,
            patch.object(convergence.frappe.db, "set_value") as set_value,
        ):
            convergence._retire_untouched_legacy_utility_card()

        rename_doc.assert_called_once_with(
            "Number Card",
            "Disputed Utility Bills",
            "Rejected Utility Bills",
            force=True,
            merge=False,
            ignore_permissions=True,
            show_alert=False,
        )
        set_value.assert_called_once_with(
            "Number Card",
            "Rejected Utility Bills",
            {
                "label": "Rejected Utility Bills",
                "filters_json": '[["Utility Bill Entry", "status", "=", "Rejected"]]',
            },
            update_modified=False,
        )

    def test_legacy_utility_card_repair_has_its_own_registered_patch(self):
        patch_path = "apex.patches.v2_6.repair_legacy_utility_number_card"
        registered = (APP_ROOT / "patches.txt").read_text(encoding="utf-8")
        self.assertIn(patch_path, registered.splitlines())

        repair = importlib.import_module(patch_path)
        with patch.object(repair, "_retire_untouched_legacy_utility_card") as retire:
            repair.execute()
        retire.assert_called_once_with()
