from unittest import TestCase
from unittest.mock import MagicMock, patch

from apex.salis.api import route_supervisor_operations as operations


class TestRouteSupervisorOperations(TestCase):
    def test_transport_request_title_prefers_route_then_business_service(self):
        self.assertEqual(
            operations._transport_request_title(
                {"from_location": "السكن", "to_location": "المشروع", "service_line": "Site Transport"}
            ),
            "السكن إلى المشروع",
        )
        self.assertEqual(
            operations._transport_request_title({"service_line": "Site Transport"}),
            "نقل العاملين",
        )

    @patch.object(operations, "_require_portal_role")
    @patch.object(operations.frappe, "get_list", return_value=[])
    def test_transport_request_list_uses_permission_aware_query(self, get_list, _role):
        operations.get_transport_requests()

        get_list.assert_called_once()
        self.assertEqual(get_list.call_args.args[0], "Transport Request")
        self.assertEqual(
            get_list.call_args.kwargs["order_by"],
            "`tabTransport Request`.modified desc, `tabTransport Request`.name desc",
        )
        self.assertNotIn("get_all", operations.get_transport_requests.__doc__ or "")

    @patch.object(operations, "_require_portal_role")
    @patch.object(operations.frappe, "get_list", return_value=[])
    @patch.object(operations.frappe, "session", MagicMock(user="supervisor@example.com"))
    def test_route_plan_list_is_limited_to_assigned_supervisor(self, get_list, _role):
        operations.get_route_plans()
        self.assertEqual(get_list.call_args.args[0], "Route Plan")
        self.assertEqual(
            get_list.call_args.kwargs.get("filters"),
            {"route_supervisor": "supervisor@example.com"},
        )

    @patch.object(operations, "_require_portal_role")
    @patch.object(operations.frappe, "get_list", return_value=[])
    @patch.object(operations.frappe, "session", MagicMock(user="Administrator"))
    def test_administrator_route_plan_list_keeps_oversight_scope(self, get_list, _role):
        operations.get_route_plans()

        self.assertNotIn("filters", get_list.call_args.kwargs)

    @patch.object(operations, "_owned_plan", create=True)
    @patch.object(operations, "_permission_checked_doc")
    def test_route_plan_detail_checks_assignment_before_loading_document(
        self, permission_checked_doc, owned_plan
    ):
        permission_checked_doc.return_value.as_dict.return_value = {"name": "RP-1"}

        operations.get_route_plan("RP-1")

        owned_plan.assert_called_once_with("RP-1")
        permission_checked_doc.assert_called_once_with("Route Plan", "RP-1")

    @patch.object(operations, "_require_portal_role")
    @patch.object(
        operations, "_owned_plan_names", return_value=["RP-OWN"], create=True
    )
    @patch.object(operations.frappe, "get_list", return_value=[])
    def test_dispatch_trip_lists_are_limited_to_owned_plans(
        self, get_list, owned_plan_names, _role
    ):
        operations.get_dispatch_trips()

        owned_plan_names.assert_called_once_with()
        self.assertEqual(
            get_list.call_args.kwargs["filters"],
            {"route_plan": ["in", ["RP-OWN"]]},
        )

    @patch.object(operations, "_require_portal_role")
    @patch.object(
        operations, "_owned_plan_names", return_value=["RP-OWN"], create=True
    )
    @patch.object(operations.frappe, "get_list", return_value=[])
    def test_movement_history_combines_status_with_owned_plan_scope(
        self, get_list, _owned_plan_names, _role
    ):
        operations.get_movement_history()

        self.assertEqual(
            get_list.call_args.kwargs["filters"],
            {
                "status": ["in", ["Completed", "Cancelled"]],
                "route_plan": ["in", ["RP-OWN"]],
            },
        )

    @patch.object(operations, "_owned_trip", create=True)
    @patch.object(operations, "_permission_checked_doc")
    def test_dispatch_trip_detail_checks_assignment_before_loading_document(
        self, permission_checked_doc, owned_trip
    ):
        permission_checked_doc.return_value.as_dict.return_value = {"name": "DT-1"}

        operations.get_dispatch_trip("DT-1")

        owned_trip.assert_called_once_with("DT-1")
        permission_checked_doc.assert_called_once_with("Dispatch Trip", "DT-1")

    @patch.object(operations, "_require_portal_role")
    @patch.object(operations.frappe, "get_doc")
    @patch("frappe.model.workflow.apply_workflow")
    def test_request_action_delegates_to_native_workflow(
        self, apply_workflow, get_doc, _role
    ):
        doc = MagicMock(name="transport-request")
        doc.name = "TR-1"
        doc.status = "Validated"
        doc.as_dict.return_value = {"name": "TR-1", "status": "Validated"}
        get_doc.return_value = doc
        apply_workflow.return_value = doc

        result = operations.apply_transport_request_action("TR-1", "Validate")

        doc.check_permission.assert_called_once_with("write")
        apply_workflow.assert_called_once_with(doc, "Validate")
        self.assertEqual(result["status"], "Validated")

    @patch.object(operations, "_require_portal_role")
    @patch.object(operations, "_owned_trip", create=True)
    @patch.object(operations.frappe, "get_doc")
    @patch("frappe.model.workflow.apply_workflow")
    def test_trip_completion_remains_native_role_gated(
        self, apply_workflow, get_doc, owned_trip, _role
    ):
        doc = MagicMock(name="dispatch-trip")
        doc.name = "DT-1"
        doc.status = "Completed"
        doc.as_dict.return_value = {"name": "DT-1", "status": "Completed"}
        get_doc.return_value = doc
        apply_workflow.return_value = doc

        operations.apply_dispatch_trip_action("DT-1", "Complete")

        owned_trip.assert_called_once_with("DT-1")
        doc.check_permission.assert_called_once_with("write")
        apply_workflow.assert_called_once_with(doc, "Complete")
