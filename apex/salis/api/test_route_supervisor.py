from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.api import route_supervisor


class TestRouteSupervisorScope(FrappeTestCase):
    @patch.object(route_supervisor.frappe, "get_roles", return_value=["Employee"])
    def test_portal_rejects_users_without_supervisor_role(self, _roles):
        with patch.object(
            route_supervisor.frappe,
            "session",
            MagicMock(user="worker@example.com"),
        ):
            with self.assertRaises(frappe.PermissionError):
                route_supervisor._require_portal_role()

    def test_page_bounds_are_explicit(self):
        for start, size in ((-1, 10), (0, 0), (0, 51)):
            with self.subTest(start=start, size=size):
                with self.assertRaises(frappe.ValidationError):
                    route_supervisor._validate_page(start, size)

    def test_the_module_serves_no_driver_position(self):
        """``get_trip_driver_position`` and the helpers under it are gone with the
        feature: nothing writes ``Dispatch Trip.driver_lat`` / ``driver_lng`` any more,
        and a Float column Frappe emits NOT NULL DEFAULT 0 reports 0,0 as a real fix."""
        for name in (
            "get_trip_driver_position",
            "_permission_checked_trip",
            "_position_age",
        ):
            with self.subTest(name=name):
                self.assertFalse(
                    hasattr(route_supervisor, name),
                    f"{name} reads a position column no writer fills",
                )


class TestActiveTripMap(FrappeTestCase):
    @patch.object(route_supervisor, "road_path", return_value=[[24.1, 46.1]])
    @patch.object(route_supervisor, "is_cached", return_value=True)
    @patch.object(route_supervisor, "_label_map")
    @patch.object(route_supervisor.frappe, "get_all")
    @patch.object(route_supervisor.frappe, "get_list")
    @patch.object(route_supervisor, "_require_portal_role")
    def test_map_pages_actual_trips_and_reads_copied_trip_stops(
        self, _role, get_list, get_all, label_map, _cached, _road_path
    ):
        get_list.return_value = [
            frappe._dict(
                name="DT-1",
                trip_title="السكن إلى المشروع",
                route_assignment="RA-1",
                project="PROJ-1",
                project_label="مشروع المطار",
                status="Dispatched",
                driver="DRV-1",
                vehicle="VEH-1",
            )
        ]
        get_all.return_value = [
            frappe._dict(
                parent="DT-1",
                stop_name="السكن",
                latitude=24.1,
                longitude=46.1,
                idx=1,
            )
        ]
        label_map.side_effect = [
            {"DRV-1": "السائق أحمد"},
            {"VEH-1": "أ ب ج 1234"},
        ]

        result = route_supervisor.get_active_driver_positions()

        self.assertEqual(get_list.call_args.args[0], "Dispatch Trip")
        self.assertEqual(
            get_list.call_args.kwargs["filters"]["status"],
            ["in", ["Planned", "Dispatched"]],
        )
        self.assertEqual(get_list.call_args.kwargs["limit_page_length"], 51)
        self.assertEqual(
            get_all.call_args.kwargs["filters"]["parenttype"], "Dispatch Trip"
        )
        self.assertEqual(result["positions"][0]["route_name"], "السكن إلى المشروع")
        self.assertEqual(result["positions"][0]["route_assignment"], "RA-1")
        self.assertEqual(result["positions"][0]["project"], "PROJ-1")
        self.assertEqual(result["positions"][0]["project_label"], "مشروع المطار")
        self.assertEqual(result["positions"][0]["driver_name"], "السائق أحمد")
        self.assertIn(
            "project.project_name as project_label",
            get_list.call_args.kwargs["fields"],
        )
        self.assertFalse(result["has_more"])

    @patch.object(route_supervisor, "_label_map", return_value={})
    @patch.object(route_supervisor.frappe, "get_all", return_value=[])
    @patch.object(route_supervisor.frappe, "get_list")
    @patch.object(route_supervisor, "_require_portal_role")
    def test_map_uses_one_extra_row_for_has_more(
        self, _role, get_list, _get_all, _labels
    ):
        get_list.return_value = [
            frappe._dict(
                name=f"DT-{index}",
                trip_title=f"رحلة {index}",
                route_assignment="RA-1",
                project="PROJ-1",
                status="Planned",
                driver=None,
                vehicle=None,
            )
            for index in range(3)
        ]

        result = route_supervisor.get_active_driver_positions(
            start=0, page_length=2
        )

        self.assertEqual(len(result["positions"]), 2)
        self.assertTrue(result["has_more"])
        self.assertEqual(result["returned"], 2)
