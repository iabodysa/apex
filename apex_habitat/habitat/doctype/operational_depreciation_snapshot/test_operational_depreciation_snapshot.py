# Copyright (c) 2026, AFMCO and contributors
import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import MagicMock, patch

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


class TestNonFinancialDepreciationSnapshot(FrappeTestCase):

    def test_create_valid_snapshot(self):
        doc = frappe.get_doc({
            "doctype": "Operational Depreciation Snapshot",
            "naming_series": "DEP-SNAP-.YYYY.-.####",
            "snapshot_date": "2026-06-30",
            "building": "QA-BLDG",
            "items": [{"doctype": "Depreciation Snapshot Item",
                        "article": "QA-ART", "original_cost_sar": 200}],
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertIsNotNone(doc.name)
        frappe.delete_doc("Operational Depreciation Snapshot", doc.name, force=True, ignore_permissions=True)

    def test_missing_snapshot_date_raises(self):
        doc = frappe.get_doc({
            "doctype": "Operational Depreciation Snapshot",
            "naming_series": "DEP-SNAP-.YYYY.-.####",
            "building": "QA-BLDG",
        })
        with self.assertRaises(frappe.exceptions.ValidationError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_empty_items_raises(self):
        from apex_habitat.habitat.doctype.operational_depreciation_snapshot.operational_depreciation_snapshot import validate

        doc = frappe.get_doc({
            "doctype": "Operational Depreciation Snapshot",
            "snapshot_date": "2026-06-30",
            "building": "QA-BLDG",
            "items": [],
        })
        with self.assertRaises(frappe.ValidationError):
            validate(doc)

    def test_validate_uses_single_bulk_policy_fetch(self):
        """RED→GREEN: _compute_book_values must fetch each distinct policy once,
        not once-per-row (N+1 guard).  Three rows sharing the same policy name
        must trigger exactly one frappe.get_doc call, not three."""
        from apex_habitat.habitat.doctype.operational_depreciation_snapshot.operational_depreciation_snapshot import validate

        # Build a fake policy object that satisfies the computation path.
        fake_policy = MagicMock()
        fake_policy.useful_life_years = 10
        fake_policy.residual_value_pct = 10
        fake_policy.depreciation_method = "Straight Line"

        doc = frappe.get_doc({
            "doctype": "Operational Depreciation Snapshot",
            "snapshot_date": "2026-06-30",
            "building": "QA-BLDG",
            "items": [
                {"doctype": "Depreciation Snapshot Item",
                 "article": "QA-ART-1", "original_cost_sar": 1000,
                 "age_years": 2, "policy": "POLICY-QA-001"},
                {"doctype": "Depreciation Snapshot Item",
                 "article": "QA-ART-2", "original_cost_sar": 2000,
                 "age_years": 3, "policy": "POLICY-QA-001"},
                {"doctype": "Depreciation Snapshot Item",
                 "article": "QA-ART-3", "original_cost_sar": 3000,
                 "age_years": 4, "policy": "POLICY-QA-001"},
            ],
        })

        module_path = (
            "apex_habitat.habitat.doctype"
            ".operational_depreciation_snapshot"
            ".operational_depreciation_snapshot.frappe.get_doc"
        )
        with patch(module_path, return_value=fake_policy) as mock_get_doc:
            validate(doc)

        # All three rows share one policy name — the cache must collapse them
        # into a single get_doc call, proving the N+1 bug is fixed.
        self.assertEqual(
            mock_get_doc.call_count,
            1,
            f"Expected exactly 1 frappe.get_doc call for 3 rows sharing the same "
            f"policy, but got {mock_get_doc.call_count} — N+1 bug still present.",
        )
