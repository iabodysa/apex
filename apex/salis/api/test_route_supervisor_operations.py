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
    def test_assignment_list_uses_native_permission_query(self, get_list, _role):
        operations.get_route_assignments()

        self.assertEqual(get_list.call_args.args[0], "Route Assignment")
        self.assertNotIn("route_supervisor", get_list.call_args.kwargs.get("filters", {}))
        self.assertIn("assignment_name", get_list.call_args.kwargs["fields"])
        self.assertIn("status", get_list.call_args.kwargs["fields"])

    @patch.object(operations, "_permission_checked_doc")
    @patch.object(operations, "_require_portal_role")
    def test_assignment_detail_checks_native_document_permission(
        self, _role, permission_checked_doc
    ):
        permission_checked_doc.return_value.as_dict.return_value = {"name": "RA-1"}

        result = operations.get_route_assignment("RA-1")

        permission_checked_doc.assert_called_once_with("Route Assignment", "RA-1")
        self.assertEqual(result, {"name": "RA-1"})

    @patch.object(operations, "_require_portal_role")
    @patch.object(operations.frappe, "get_list", return_value=[])
    def test_dispatch_trip_list_uses_direct_actual_trip_fields(self, get_list, _role):
        operations.get_dispatch_trips()

        self.assertEqual(get_list.call_args.args[0], "Dispatch Trip")
        fields = get_list.call_args.kwargs["fields"]
        self.assertIn("trip_title", fields)
        self.assertIn("route_assignment", fields)
        self.assertIn("project", fields)
        self.assertNotIn("route_plan.route_name as route_name", fields)
        self.assertNotIn("filters", get_list.call_args.kwargs)
        self.assertEqual(
            get_list.call_args.kwargs["order_by"],
            "`tabDispatch Trip`.trip_date desc, "
            "`tabDispatch Trip`.modified desc, "
            "`tabDispatch Trip`.name desc",
        )

    @patch.object(operations, "_require_portal_role")
    @patch.object(operations.frappe, "get_list", return_value=[])
    def test_movement_history_uses_status_plus_native_permission_scope(
        self, get_list, _role
    ):
        operations.get_movement_history()

        self.assertEqual(
            get_list.call_args.kwargs["filters"],
            {"status": ["in", ["Completed", "Cancelled"]]},
        )
        self.assertEqual(
            get_list.call_args.kwargs["order_by"],
            "`tabDispatch Trip`.trip_date desc, "
            "`tabDispatch Trip`.modified desc, "
            "`tabDispatch Trip`.name desc",
        )

    @patch.object(operations, "_require_portal_role")
    @patch.object(operations, "_permission_checked_doc")
    def test_dispatch_trip_detail_checks_native_document_permission(
        self, permission_checked_doc, _role
    ):
        permission_checked_doc.return_value.as_dict.return_value = {"name": "DT-1"}

        operations.get_dispatch_trip("DT-1")

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
    @patch.object(operations.frappe, "get_doc")
    @patch("frappe.model.workflow.apply_workflow")
    def test_assignment_approval_delegates_to_native_workflow(
        self, apply_workflow, get_doc, _role
    ):
        doc = MagicMock(name="route-assignment")
        doc.name = "RA-1"
        doc.status = "Approved"
        doc.docstatus = 1
        get_doc.return_value = doc
        apply_workflow.return_value = doc

        result = operations.apply_route_assignment_action("RA-1", "Approve")

        doc.check_permission.assert_called_once_with("write")
        apply_workflow.assert_called_once_with(doc, "Approve")
        self.assertEqual(result["status"], "Approved")

    @patch.object(operations, "_require_portal_role")
    @patch.object(operations.frappe, "get_doc")
    @patch("frappe.model.workflow.apply_workflow")
    def test_trip_completion_remains_native_role_gated(
        self, apply_workflow, get_doc, _role
    ):
        doc = MagicMock(name="dispatch-trip")
        doc.name = "DT-1"
        doc.status = "Completed"
        doc.as_dict.return_value = {"name": "DT-1", "status": "Completed"}
        get_doc.return_value = doc
        apply_workflow.return_value = doc

        operations.apply_dispatch_trip_action("DT-1", "Complete")

        doc.check_permission.assert_called_once_with("write")
        apply_workflow.assert_called_once_with(doc, "Complete")
