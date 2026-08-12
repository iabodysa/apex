from unittest import TestCase
from unittest.mock import MagicMock, patch

from apex.salis.api import route_supervisor_operations as operations


class TestRouteSupervisorOperations(TestCase):
    @patch.object(operations, "_require_portal_role")
    @patch.object(operations.frappe, "get_list", return_value=[])
    def test_transport_request_list_uses_permission_aware_query(self, get_list, _role):
        operations.get_transport_requests()

        get_list.assert_called_once()
        self.assertEqual(get_list.call_args.args[0], "Transport Request")
        self.assertNotIn("get_all", operations.get_transport_requests.__doc__ or "")

    @patch.object(operations, "_require_portal_role")
    @patch.object(operations.frappe, "get_list", return_value=[])
    def test_route_plan_list_uses_project_user_permissions(self, get_list, _role):
        operations.get_route_plans()
        self.assertEqual(get_list.call_args.args[0], "Route Plan")

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
