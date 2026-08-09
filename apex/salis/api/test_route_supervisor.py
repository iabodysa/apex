# Copyright (c) 2026, afmcoltd

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.api import route_supervisor


class TestRouteSupervisorPagination(FrappeTestCase):
    def setUp(self):
        frappe.set_user("route.supervisor@example.com")

    def tearDown(self):
        frappe.set_user("Administrator")

    @patch.object(route_supervisor, "_serialize_plans", side_effect=lambda rows: rows)
    @patch.object(
        route_supervisor,
        "_plan_counts",
        return_value={"total": 62, "pending": 61, "decided": 1},
    )
    @patch.object(route_supervisor, "_require_portal_role")
    @patch.object(route_supervisor.frappe, "get_all")
    def test_pending_pages_cover_more_than_fifty_without_duplicates(
        self, get_all, _require_role, _counts, _serialize
    ):
        rows = [{"name": f"RP-{index:03d}"} for index in range(61)]

        def page(*_args, **kwargs):
            start = kwargs["limit_start"]
            end = start + kwargs["limit_page_length"]
            return rows[start:end]

        get_all.side_effect = page

        first = route_supervisor.get_supervisor_plans(
            "pending", start=0, page_length=50
        )
        second = route_supervisor.get_supervisor_plans(
            "pending", start=50, page_length=50
        )

        self.assertEqual(len(first["plans"]), 50)
        self.assertEqual(len(second["plans"]), 11)
        self.assertTrue(first["has_more"])
        self.assertFalse(second["has_more"])
        self.assertEqual(
            {row["name"] for row in first["plans"]}
            & {row["name"] for row in second["plans"]},
            set(),
        )
        self.assertEqual(first["total"], 61)
        for call in get_all.call_args_list:
            self.assertEqual(
                call.kwargs["filters"]["route_supervisor"], frappe.session.user
            )
            self.assertEqual(
                call.kwargs["or_filters"],
                [
                    ["Route Plan", "supervisor_approval", "=", "Pending"],
                    ["Route Plan", "supervisor_approval", "is", "not set"],
                ],
            )

    @patch.object(route_supervisor, "_serialize_plans", side_effect=lambda rows: rows)
    @patch.object(
        route_supervisor,
        "_plan_counts",
        return_value={"total": 4, "pending": 3, "decided": 1},
    )
    @patch.object(route_supervisor, "_require_portal_role")
    @patch.object(route_supervisor.frappe, "get_all", return_value=[])
    def test_supervisor_scope_and_deterministic_order_reach_every_page_query(
        self, get_all, _require_role, _counts, _serialize
    ):
        route_supervisor.get_supervisor_plans("decided", start=2, page_length=2)

        kwargs = get_all.call_args.kwargs
        self.assertEqual(kwargs["filters"]["route_supervisor"], frappe.session.user)
        self.assertEqual(
            kwargs["filters"]["supervisor_approval"], ["in", ["Approved", "Rejected"]]
        )
        self.assertEqual(kwargs["limit_start"], 2)
        self.assertEqual(kwargs["limit_page_length"], 2)
        self.assertEqual(kwargs["order_by"], "modified desc, name desc")

    def test_page_bounds_are_explicit(self):
        for lane, start, size in (
            ("unknown", 0, 10),
            ("pending", -1, 10),
            ("pending", 0, 0),
            ("pending", 0, route_supervisor.PLAN_PAGE_LENGTH + 1),
        ):
            with self.subTest(lane=lane, start=start, size=size):
                with self.assertRaises(frappe.ValidationError):
                    route_supervisor._validate_page(lane, start, size)

    @patch.object(route_supervisor, "_terminal_approved_count", return_value=4)
    @patch.object(route_supervisor.frappe.db, "count", side_effect=[73, 12, 5])
    def test_counts_cover_full_scoped_set_without_loading_rows(
        self, count, terminal_approved
    ):
        result = route_supervisor._plan_counts()

        self.assertEqual(
            result,
            {
                "total": 73,
                "pending": 61,
                "decided": 12,
                "active": 3,
                "history": 9,
            },
        )
        total_filters = count.call_args_list[0].args[1]
        decided_filters = count.call_args_list[1].args[1]
        rejected_filters = count.call_args_list[2].args[1]
        self.assertEqual(total_filters["route_supervisor"], frappe.session.user)
        self.assertEqual(
            decided_filters["supervisor_approval"], ["in", ["Approved", "Rejected"]]
        )
        self.assertEqual(rejected_filters["supervisor_approval"], "Rejected")
        terminal_approved.assert_called_once_with(total_filters)

    @patch.object(route_supervisor.frappe.db, "sql", return_value=[{"count": 7}])
    def test_terminal_count_uses_one_scoped_aggregate_query(self, sql):
        result = route_supervisor._terminal_approved_count(
            {
                "docstatus": 1,
                "route_supervisor": frappe.session.user,
            }
        )

        self.assertEqual(result, 7)
        query = sql.call_args.args[0]
        values = sql.call_args.args[1]
        self.assertIn("COUNT(*)", query)
        self.assertIn("LIMIT 1", query)
        self.assertIn("rp.route_supervisor = %(route_supervisor)s", query)
        self.assertEqual(values["route_supervisor"], frappe.session.user)
        self.assertTrue(sql.call_args.kwargs["as_dict"])

    @patch.object(route_supervisor, "_serialize_plans", side_effect=lambda rows: rows)
    @patch.object(
        route_supervisor,
        "_plan_counts",
        return_value={"total": 73, "pending": 61, "decided": 12},
    )
    @patch.object(route_supervisor, "_require_portal_role")
    @patch.object(route_supervisor, "_page_rows")
    def test_context_counts_are_full_and_each_lane_remains_available(
        self, page_rows, _require_role, _counts, _serialize
    ):
        page_rows.side_effect = [
            [{"name": f"P-{index:03d}"} for index in range(50)],
            [{"name": f"D-{index:03d}"} for index in range(12)],
        ]

        result = route_supervisor.get_supervisor_context()

        self.assertEqual(result["counts"], {"total": 73, "pending": 61, "decided": 12})
        self.assertEqual(len(result["plans"]), 62)
        self.assertTrue(result["pages"]["pending"]["has_more"])
        self.assertFalse(result["pages"]["decided"]["has_more"])


class TestRouteSupervisorTargetedReads(FrappeTestCase):
    @patch.object(route_supervisor.frappe, "get_all")
    @patch.object(
        route_supervisor.frappe.db,
        "sql",
        return_value=[
            {"name": "DT-2", "route_plan": "RP-2", "status": "Dispatched"},
            {"name": "DT-1", "route_plan": "RP-1", "status": "Completed"},
        ],
    )
    def test_active_trip_selection_returns_one_bounded_row_per_plan(self, sql, get_all):
        result = route_supervisor._active_trips_by_plan(["RP-2", "RP-1", "RP-2"])

        self.assertEqual(set(result), {"RP-1", "RP-2"})
        query = sql.call_args.args[0]
        values = sql.call_args.args[1]
        self.assertIn("ROW_NUMBER() OVER", query)
        self.assertIn("trip_rank = 1", query)
        self.assertEqual(values["plan_names"], ("RP-1", "RP-2"))
        get_all.assert_not_called()

    @patch.object(route_supervisor, "_require_portal_role")
    @patch.object(route_supervisor, "_serialize_plans")
    @patch.object(route_supervisor, "_owned_plan")
    def test_single_plan_reader_returns_list_hydrated_shape(
        self, owned_plan, serialize_plans, _require_role
    ):
        owned = {
            "name": "RP-0099",
            "docstatus": 1,
            "route_supervisor": "route.supervisor@example.com",
        }
        hydrated = {"name": "RP-0099", "approval": "Approved", "trip": None}
        owned_plan.return_value = owned
        serialize_plans.return_value = [hydrated]

        result = route_supervisor.get_supervisor_plan("RP-0099")

        self.assertEqual(result, {"plan": hydrated})
        owned_plan.assert_called_once_with("RP-0099")
        serialize_plans.assert_called_once_with([owned])

    @patch.object(route_supervisor, "_require_portal_role")
    @patch.object(
        route_supervisor,
        "_owned_plan",
        side_effect=frappe.PermissionError("out of scope"),
    )
    def test_single_plan_reader_propagates_row_scope_rejection(
        self, owned_plan, _require_role
    ):
        with self.assertRaises(frappe.PermissionError):
            route_supervisor.get_supervisor_plan("RP-OTHER")
        owned_plan.assert_called_once_with("RP-OTHER")


class TestRouteSupervisorPositionPagination(FrappeTestCase):
    def setUp(self):
        frappe.set_user("route.supervisor@example.com")

    def tearDown(self):
        frappe.set_user("Administrator")

    @patch.object(route_supervisor, "_active_trips_by_plan", return_value={})
    @patch.object(route_supervisor, "_require_portal_role")
    @patch.object(route_supervisor.frappe.db, "count", return_value=61)
    @patch.object(route_supervisor.frappe, "get_all")
    def test_position_pages_expose_scope_and_stable_page_metadata(
        self, get_all, count, _require_role, _trips
    ):
        get_all.return_value = [{"name": f"RP-{index:03d}"} for index in range(50, 61)]

        result = route_supervisor.get_active_driver_positions(start=50, page_length=50)

        self.assertEqual(result["positions"], [])
        self.assertEqual(result["start"], 50)
        self.assertEqual(result["page_length"], 50)
        self.assertEqual(result["returned"], 0)
        self.assertEqual(result["total"], 61)
        self.assertFalse(result["has_more"])
        filters = get_all.call_args.kwargs["filters"]
        self.assertEqual(filters["route_supervisor"], frappe.session.user)
        self.assertEqual(get_all.call_args.kwargs["limit_start"], 50)
        self.assertEqual(get_all.call_args.kwargs["limit_page_length"], 50)
        self.assertEqual(get_all.call_args.kwargs["order_by"], "modified desc, name desc")
        count.assert_called_once_with("Route Plan", filters)

    def test_position_page_bounds_are_explicit(self):
        for start, size in ((-1, 10), (0, 0), (0, 51)):
            with self.subTest(start=start, size=size):
                with self.assertRaises(frappe.ValidationError):
                    route_supervisor._validate_position_page(start, size)
