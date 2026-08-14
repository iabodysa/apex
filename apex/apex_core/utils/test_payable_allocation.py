# Copyright (c) 2026, afmcoltd

from unittest.mock import patch

from frappe.tests.utils import FrappeTestCase

from apex.apex_core.utils import payable_allocation


class TestPayableAllocation(FrappeTestCase):
    def test_list_payables_uses_permission_aware_query(self):
        rows = [{"name": "PINV-1"}]

        with (
            patch.object(payable_allocation.frappe.db, "exists", return_value=True),
            patch.object(payable_allocation.frappe, "has_permission"),
            patch.object(payable_allocation.frappe, "get_list", return_value=rows) as get_list,
            patch.object(
                payable_allocation.frappe,
                "get_all",
                side_effect=AssertionError("permission-bypassing query"),
            ),
        ):
            result = payable_allocation.list_payables("Apex Co", "Supplier A", limit=25)

        self.assertEqual(result, rows)
        get_list.assert_called_once_with(
            "Purchase Invoice",
            filters=payable_allocation.payable_filters("Apex Co", "Supplier A"),
            fields=[
                "name",
                "bill_no",
                "posting_date",
                "grand_total",
                "outstanding_amount",
                "currency",
            ],
            order_by="posting_date asc",
            limit_page_length=25,
        )

    def test_payable_count_uses_permission_aware_aggregate(self):
        with (
            patch.object(payable_allocation.frappe.db, "exists", return_value=True),
            patch.object(payable_allocation.frappe, "has_permission", return_value=True),
            patch.object(
                payable_allocation.frappe,
                "get_list",
                return_value=[{"count": 3}],
            ) as get_list,
            patch.object(
                payable_allocation.frappe.db,
                "count",
                side_effect=AssertionError("permission-bypassing count"),
            ),
        ):
            result = payable_allocation.payable_count("Apex Co", "Supplier A")

        self.assertEqual(result, 3)
        get_list.assert_called_once_with(
            "Purchase Invoice",
            filters=payable_allocation.payable_filters("Apex Co", "Supplier A"),
            fields=["count(name) as count"],
            limit_page_length=1,
        )
