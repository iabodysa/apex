from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.api import fleet_employee, fleet_employee_services, fleet_os
from apex.salis.doctype.fuel_request.fuel_request import FuelRequest
from apex.salis.utils import reassign_vehicle_driver


class FleetEmployeePortalTest(FrappeTestCase):
    @patch.object(fleet_employee, "bound_vehicle", return_value="VEH-1")
    @patch.object(fleet_employee, "get_driver_for_session_user", return_value="DRV-1")
    @patch.object(
        fleet_employee_services,
        "_active_assignment_for_driver",
        return_value=SimpleNamespace(name="VA-1", vehicle="VEH-1"),
    )
    @patch.object(fleet_employee_services, "_handover_checklist_template")
    def test_handover_checklist_is_loaded_from_native_template(
        self, checklist_template, _assignment, _driver, _vehicle
    ):
        checklist_template.return_value = SimpleNamespace(
            name="Daily Inspection",
            items=[
                SimpleNamespace(check_item="Tyres", remark=""),
                SimpleNamespace(check_item="Lights", remark="Check all lamps"),
            ],
        )

        result = fleet_employee.get_handover_checklist("Return")

        checklist_template.assert_called_once_with("VEH-1")
        self.assertEqual(result["direction"], "Return")
        self.assertIn("assignment", result)
        self.assertEqual(result["template"], "Daily Inspection")
        self.assertEqual(
            result["items"],
            [
                {"check_item": "Tyres", "default_remark": ""},
                {"check_item": "Lights", "default_remark": "Check all lamps"},
            ],
        )

    @patch.object(
        fleet_employee_services.base, "_session_vehicle", return_value="VEH-1"
    )
    @patch.object(fleet_employee_services.base, "_session_driver", return_value="DRV-1")
    @patch.object(fleet_employee_services, "_active_assignment_for_driver", create=True)
    @patch.object(fleet_employee_services, "_handover_checklist_template")
    def test_handover_checklist_returns_stable_assignment_identity(
        self, checklist_template, active_assignment, _driver, _vehicle
    ):
        active_assignment.return_value = SimpleNamespace(
            name="VA-1", vehicle="VEH-1", driver="DRV-1", status="Active", docstatus=1
        )
        checklist_template.return_value = SimpleNamespace(
            name="Daily Inspection",
            items=[SimpleNamespace(check_item="Tyres", remark="")],
        )

        result = fleet_employee_services.get_handover_checklist("Receipt")

        self.assertEqual(result["assignment"], "VA-1")
        self.assertEqual(result["vehicle"], "VEH-1")

    @patch.object(fleet_employee_services.base, "_session_driver", return_value="DRV-1")
    @patch.object(
        fleet_employee_services.base, "_session_vehicle", return_value="VEH-1"
    )
    @patch.object(fleet_employee_services, "_locked_session_assignment", create=True)
    @patch.object(fleet_employee_services, "_owned_evidence_file")
    @patch.object(
        fleet_employee_services.frappe.db, "get_value", return_value="GV-RETURN"
    )
    def test_return_retry_dedupes_by_assignment_before_evidence_validation(
        self, _duplicate, owned_evidence, locked_assignment, _vehicle, _driver
    ):
        locked_assignment.return_value = SimpleNamespace(
            name="VA-1",
            vehicle="VEH-1",
            driver="DRV-1",
            status="Ended",
            docstatus=1,
        )

        result = fleet_employee_services.return_vehicle(
            assignment="VA-1",
            odometer=150,
            signed_evidence=None,
            inspection_rows=None,
        )

        self.assertEqual(result, {"name": "GV-RETURN", "status": "Submitted"})
        owned_evidence.assert_not_called()

    @patch.object(fleet_employee_services.base, "_session_driver", return_value="DRV-1")
    @patch.object(
        fleet_employee_services.base, "_session_vehicle", return_value="VEH-1"
    )
    @patch.object(fleet_employee_services, "_locked_session_assignment", create=True)
    @patch.object(fleet_employee_services.frappe.db, "get_value", return_value=None)
    @patch.object(fleet_employee_services.frappe, "get_doc")
    def test_failed_checklist_derives_discrepancy_and_binds_assignment(
        self, get_doc, _duplicate, locked_assignment, _vehicle, _driver
    ):
        locked_assignment.return_value = SimpleNamespace(
            name="VA-1",
            vehicle="VEH-1",
            driver="DRV-1",
            status="Active",
            docstatus=1,
            end_date=None,
        )
        template = SimpleNamespace(
            name="Daily Inspection",
            items=[
                SimpleNamespace(check_item="Tyres", remark=""),
                SimpleNamespace(check_item="Lights", remark=""),
            ],
        )
        evidence = SimpleNamespace(
            name="FILE-1", attached_to_doctype=None, attached_to_name=None
        )
        handover = MagicMock(name="handover")
        handover.name = "GV-1"
        get_doc.return_value = handover
        with (
            patch(
                "apex.salis.api.fleet_employee_services.frappe.utils.today",
                return_value="2026-08-14",
            ),
            patch.object(
                fleet_employee_services,
                "_handover_checklist_template",
                return_value=template,
            ),
            patch.object(
                fleet_employee_services,
                "_owned_evidence_file",
                return_value=evidence,
            ),
            patch.object(fleet_employee_services, "lock_vehicle"),
        ):
            fleet_employee_services.return_vehicle(
                assignment="VA-1",
                odometer=150,
                signed_evidence="/private/files/return.pdf",
                inspection_rows=[
                    {"check_item": "Tyres", "ok": 1, "remark": ""},
                    {"check_item": "Lights", "ok": 0, "remark": "Cracked"},
                ],
            )

        payload = get_doc.call_args.args[0]
        self.assertEqual(payload["vehicle_assignment"], "VA-1")
        self.assertEqual(payload["discrepancy_status"], "Discrepancy")
        self.assertEqual(payload["discrepancy_notes"], "Lights: Cracked")

    @patch.object(fleet_employee_services, "_", side_effect=lambda message: message)
    @patch.object(
        fleet_employee_services.frappe,
        "throw",
        side_effect=frappe.PermissionError,
    )
    @patch.object(fleet_employee_services.frappe, "get_doc")
    def test_assignment_must_belong_to_session_driver(
        self, get_doc, _throw, _translate
    ):
        handler = getattr(fleet_employee_services, "_locked_session_assignment", None)
        self.assertIsNotNone(handler)
        get_doc.return_value = SimpleNamespace(
            name="VA-OTHER",
            vehicle="VEH-2",
            driver="DRV-OTHER",
            status="Active",
            docstatus=1,
        )

        with self.assertRaises(frappe.PermissionError):
            handler("VA-OTHER", "DRV-1")

        get_doc.assert_called_once_with(
            "Vehicle Assignment", "VA-OTHER", for_update=True
        )

    @patch.object(fleet_employee, "get_driver_for_session_user", return_value=None)
    def test_context_returns_typed_unlinked_state(self, _driver):
        self.assertEqual(
            fleet_employee.get_context(),
            {"state": "unlinked", "driver": None, "vehicle": None, "capabilities": {}},
        )

    @patch.object(fleet_employee, "bound_vehicle", return_value="VEH-1")
    @patch.object(fleet_employee, "get_driver_for_session_user", return_value="DRV-1")
    @patch(
        "apex.salis.api.fleet_employee_services.frappe.utils.today",
        return_value="2026-08-12",
    )
    @patch.object(fleet_employee.frappe.db, "get_value", return_value=None)
    @patch.object(fleet_employee.frappe, "get_doc")
    def test_receipt_binds_vehicle_and_driver_to_session(
        self, get_doc, _duplicate, _today, _driver, _vehicle
    ):
        doc = MagicMock(name="handover")
        doc.name = "GV-1"
        doc.status = "Submitted"
        get_doc.return_value = doc

        template = SimpleNamespace(
            name="Daily Inspection",
            items=[SimpleNamespace(check_item="Tyres", remark="")],
        )
        evidence = SimpleNamespace(
            name="FILE-1", attached_to_doctype=None, attached_to_name=None
        )
        with (
            patch.object(
                fleet_employee_services,
                "_locked_session_assignment",
                return_value=SimpleNamespace(
                    name="VA-1",
                    vehicle="VEH-1",
                    driver="DRV-1",
                    status="Active",
                    docstatus=1,
                ),
            ),
            patch.object(fleet_employee_services, "lock_vehicle"),
            patch.object(
                fleet_employee_services.frappe.db, "set_value"
            ) as attach_evidence,
            patch.object(
                fleet_employee_services,
                "_handover_checklist_template",
                return_value=template,
            ),
            patch.object(
                fleet_employee_services,
                "_owned_evidence_file",
                return_value=evidence,
            ),
        ):
            result = fleet_employee.receive_vehicle(
                odometer=120,
                assignment="VA-1",
                fuel_level="Half",
                signed_evidence="/private/files/receipt.pdf",
                inspection_rows=[{"check_item": "Tyres", "ok": 1}],
            )

        payload = get_doc.call_args.args[0]
        self.assertEqual(payload["direction"], "Receipt")
        self.assertEqual(payload["vehicle"], "VEH-1")
        self.assertIsNone(payload["from_driver"])
        self.assertEqual(payload["to_driver"], "DRV-1")
        self.assertEqual(payload["checklist_template"], "Daily Inspection")
        doc.insert.assert_called_once_with()
        doc.submit.assert_called_once_with()
        attach_evidence.assert_called_once_with(
            "File",
            "FILE-1",
            {
                "attached_to_doctype": "Vehicle Handover",
                "attached_to_name": "GV-1",
                "attached_to_field": "signed_evidence",
            },
        )
        self.assertEqual(result["name"], "GV-1")

    @patch.object(fleet_employee, "bound_vehicle", return_value="VEH-1")
    @patch.object(fleet_employee, "get_driver_for_session_user", return_value="DRV-1")
    @patch(
        "apex.salis.api.fleet_employee_services.frappe.utils.today",
        return_value="2026-08-12",
    )
    @patch.object(fleet_employee.frappe.db, "get_value", return_value=None)
    @patch.object(fleet_employee.frappe, "get_doc")
    def test_return_uses_pool_direction_without_fake_driver(
        self, get_doc, _duplicate, _today, _driver, _vehicle
    ):
        doc = MagicMock(name="handover")
        doc.name = "GV-2"
        get_doc.return_value = doc

        template = SimpleNamespace(
            name="Daily Inspection",
            items=[SimpleNamespace(check_item="Tyres", remark="")],
        )
        evidence = SimpleNamespace(
            name="FILE-2", attached_to_doctype=None, attached_to_name=None
        )
        with (
            patch.object(
                fleet_employee_services,
                "_locked_session_assignment",
                return_value=SimpleNamespace(
                    name="VA-1",
                    vehicle="VEH-1",
                    driver="DRV-1",
                    status="Active",
                    docstatus=1,
                ),
            ),
            patch.object(fleet_employee_services, "lock_vehicle"),
            patch.object(
                fleet_employee_services,
                "_handover_checklist_template",
                return_value=template,
            ),
            patch.object(
                fleet_employee_services,
                "_owned_evidence_file",
                return_value=evidence,
            ),
        ):
            fleet_employee.return_vehicle(
                odometer=150,
                assignment="VA-1",
                fuel_level="Quarter",
                signed_evidence="/private/files/return.pdf",
                inspection_rows=[{"check_item": "Tyres", "ok": 1}],
            )

        payload = get_doc.call_args.args[0]
        self.assertEqual(payload["direction"], "Return")
        self.assertEqual(payload["from_driver"], "DRV-1")
        self.assertIsNone(payload["to_driver"])

    @patch.object(fleet_employee, "bound_vehicle", return_value="VEH-1")
    @patch.object(fleet_employee, "get_driver_for_session_user", return_value="DRV-1")
    @patch(
        "apex.salis.api.fleet_employee_services.frappe.utils.today",
        return_value="2026-08-12",
    )
    @patch.object(fleet_employee.frappe.db, "get_value", return_value=None)
    @patch.object(fleet_employee_services, "_handover_checklist_template")
    @patch.object(fleet_employee.frappe, "get_doc")
    def test_return_saves_native_template_answers_before_submit(
        self, get_doc, checklist_template, _duplicate, _today, _driver, _vehicle
    ):
        checklist_template.return_value = SimpleNamespace(
            name="Daily Inspection",
            items=[
                SimpleNamespace(check_item="Tyres", remark=""),
                SimpleNamespace(check_item="Lights", remark=""),
            ],
        )
        doc = MagicMock(name="handover")
        doc.name = "GV-3"
        get_doc.return_value = doc

        evidence = SimpleNamespace(
            name="FILE-3", attached_to_doctype=None, attached_to_name=None
        )
        with (
            patch.object(
                fleet_employee_services,
                "_locked_session_assignment",
                return_value=SimpleNamespace(
                    name="VA-1",
                    vehicle="VEH-1",
                    driver="DRV-1",
                    status="Active",
                    docstatus=1,
                ),
            ),
            patch.object(fleet_employee_services, "lock_vehicle"),
            patch.object(
                fleet_employee_services,
                "_owned_evidence_file",
                return_value=evidence,
            ),
        ):
            fleet_employee.return_vehicle(
                odometer=150,
                assignment="VA-1",
                signed_evidence="/private/files/return.pdf",
                checklist_template="Daily Inspection",
                inspection_rows=[
                    {"check_item": "Tyres", "ok": 1, "remark": ""},
                    {"check_item": "Lights", "ok": 0, "remark": "Left lamp cracked"},
                ],
            )

        checklist_template.assert_called_once_with("VEH-1", "Daily Inspection")
        payload = get_doc.call_args.args[0]
        self.assertEqual(payload["checklist_template"], "Daily Inspection")
        self.assertEqual(
            payload["handover_check_items"],
            [
                {"check_item": "Tyres", "ok": 1, "remark": ""},
                {"check_item": "Lights", "ok": 0, "remark": "Left lamp cracked"},
            ],
        )
        doc.insert.assert_called_once_with()
        doc.submit.assert_called_once_with()

    @patch.object(fleet_employee, "bound_vehicle", return_value="VEH-1")
    @patch.object(fleet_employee, "get_driver_for_session_user", return_value="DRV-1")
    @patch(
        "apex.salis.api.fleet_employee_services.frappe.utils.today",
        return_value="2026-08-12",
    )
    @patch.object(fleet_employee.frappe.db, "get_value", return_value=None)
    @patch.object(
        fleet_employee_services.frappe, "throw", side_effect=frappe.ValidationError
    )
    @patch.object(fleet_employee_services, "_", side_effect=lambda message: message)
    @patch.object(fleet_employee_services, "_handover_checklist_template")
    def test_handover_rejects_missing_native_template_answers(
        self,
        checklist_template,
        _translate,
        _throw,
        _duplicate,
        _today,
        _driver,
        _vehicle,
    ):
        checklist_template.return_value = SimpleNamespace(
            name="Daily Inspection",
            items=[
                SimpleNamespace(check_item="Tyres", remark=""),
                SimpleNamespace(check_item="Lights", remark=""),
            ],
        )

        evidence = SimpleNamespace(
            name="FILE-4", attached_to_doctype=None, attached_to_name=None
        )
        with (
            patch.object(
                fleet_employee_services,
                "_locked_session_assignment",
                return_value=SimpleNamespace(
                    name="VA-1",
                    vehicle="VEH-1",
                    driver="DRV-1",
                    status="Active",
                    docstatus=1,
                ),
            ),
            patch.object(fleet_employee_services, "lock_vehicle"),
            patch.object(
                fleet_employee_services,
                "_owned_evidence_file",
                return_value=evidence,
            ),
            self.assertRaises(frappe.ValidationError),
        ):
            fleet_employee.return_vehicle(
                odometer=150,
                assignment="VA-1",
                signed_evidence="/private/files/return.pdf",
                checklist_template="Daily Inspection",
                inspection_rows=[{"check_item": "Tyres", "ok": 1}],
            )

    @patch.object(fleet_employee_services.frappe.db, "get_value", return_value=None)
    @patch.object(
        fleet_employee_services.frappe,
        "throw",
        side_effect=frappe.PermissionError,
    )
    @patch.object(fleet_employee_services, "_", side_effect=lambda message: message)
    def test_handover_evidence_must_be_owned_private_file(
        self, _translate, _throw, get_value
    ):
        with self.assertRaises(frappe.PermissionError):
            fleet_employee_services._owned_evidence_file(
                "/private/files/not-mine.pdf"
            )

        filters = get_value.call_args.args[1]
        self.assertEqual(filters["owner"], frappe.session.user)
        self.assertEqual(filters["is_private"], 1)
        self.assertTrue(get_value.call_args.kwargs["for_update"])

    @patch.object(fleet_employee, "bound_vehicle", return_value="VEH-1")
    @patch.object(fleet_employee, "get_driver_for_session_user", return_value="DRV-1")
    @patch(
        "apex.salis.api.fleet_employee_services.frappe.utils.today",
        return_value="2026-08-12",
    )
    @patch.object(fleet_employee.frappe.db, "get_value", return_value=None)
    @patch.object(fleet_employee.frappe, "get_doc")
    def test_receipt_rejects_omitted_checklist_answers(
        self, get_doc, _duplicate, _today, _driver, _vehicle
    ):
        template = SimpleNamespace(
            name="Daily Inspection",
            items=[SimpleNamespace(check_item="Tyres", remark="")],
        )
        evidence = SimpleNamespace(
            name="FILE-5", attached_to_doctype=None, attached_to_name=None
        )
        with (
            patch.object(
                fleet_employee_services,
                "_locked_session_assignment",
                return_value=SimpleNamespace(
                    name="VA-1",
                    vehicle="VEH-1",
                    driver="DRV-1",
                    status="Active",
                    docstatus=1,
                ),
            ),
            patch.object(fleet_employee_services, "lock_vehicle"),
            patch.object(
                fleet_employee_services,
                "_handover_checklist_template",
                return_value=template,
            ),
            patch.object(
                fleet_employee_services,
                "_owned_evidence_file",
                return_value=evidence,
            ),
            patch.object(
                fleet_employee_services,
                "_",
                side_effect=lambda message: message,
            ),
            patch.object(
                fleet_employee_services.frappe,
                "throw",
                side_effect=frappe.ValidationError,
            ),
            self.assertRaises(frappe.ValidationError),
        ):
            fleet_employee.receive_vehicle(
                odometer=120,
                assignment="VA-1",
                signed_evidence="/private/files/receipt.pdf",
            )

        get_doc.assert_not_called()

    @patch.object(fleet_employee, "bound_vehicle", return_value="VEH-1")
    @patch.object(fleet_employee, "get_driver_for_session_user", return_value="DRV-1")
    @patch.object(
        fleet_employee_services.frappe.db, "get_value", return_value="GV-EXISTING"
    )
    @patch.object(fleet_employee_services.frappe, "get_doc")
    def test_retried_handover_returns_submitted_document_before_evidence(
        self, get_doc, _duplicate, _driver, _vehicle
    ):
        template = SimpleNamespace(
            name="Daily Inspection",
            items=[SimpleNamespace(check_item="Tyres", remark="")],
        )
        evidence = SimpleNamespace(
            name="FILE-6", attached_to_doctype=None, attached_to_name=None
        )
        with (
            patch.object(
                fleet_employee_services,
                "_locked_session_assignment",
                return_value=SimpleNamespace(
                    name="VA-1",
                    vehicle="VEH-1",
                    driver="DRV-1",
                    status="Ended",
                    docstatus=1,
                ),
            ),
            patch.object(fleet_employee_services, "lock_vehicle") as lock_vehicle,
            patch.object(
                fleet_employee_services,
                "_handover_checklist_template",
                return_value=template,
            ),
            patch.object(
                fleet_employee_services,
                "_owned_evidence_file",
                return_value=evidence,
            ) as owned_evidence,
        ):
            result = fleet_employee.return_vehicle(
                odometer=150,
                assignment="VA-1",
                signed_evidence="/private/files/return.pdf",
                inspection_rows=[{"check_item": "Tyres", "ok": 1}],
            )

        lock_vehicle.assert_not_called()
        owned_evidence.assert_not_called()
        get_doc.assert_not_called()
        self.assertEqual(result, {"name": "GV-EXISTING", "status": "Submitted"})

    @patch.object(fleet_employee, "bound_vehicle", return_value="VEH-1")
    @patch.object(fleet_employee, "get_driver_for_session_user", return_value="DRV-1")
    @patch.object(fleet_employee.frappe, "get_doc")
    def test_incident_intake_excludes_staff_disposition_fields(self, get_doc, _driver, _vehicle):
        doc = MagicMock(name="incident")
        doc.name = "VI-1"
        doc.status = "Open"
        get_doc.return_value = doc

        fleet_employee.report_incident(
            incident_type="Accident",
            incident_date="2026-08-12",
            description="Rear bumper damaged",
            location="Riyadh",
        )

        payload = get_doc.call_args.args[0]
        self.assertEqual(payload["driver"], "DRV-1")
        self.assertEqual(payload["vehicle"], "VEH-1")
        for forbidden in ("estimated_cost", "fault", "recover_from_driver", "write_off_case"):
            self.assertNotIn(forbidden, payload)

    @patch.object(fleet_employee, "get_driver_for_session_user", return_value="DRV-1")
    @patch.object(fleet_employee.frappe.db, "get_value", return_value="PROJ-1")
    @patch.object(fleet_employee.frappe, "get_doc")
    def test_complaint_reuses_issue_and_session_project(self, get_doc, _project, _driver):
        doc = MagicMock(name="issue")
        doc.name = "ISS-1"
        doc.status = "Open"
        get_doc.return_value = doc

        fleet_employee.create_complaint("High", "Late handover", "Vehicle was unavailable")

        payload = get_doc.call_args.args[0]
        self.assertEqual(payload["doctype"], "Issue")
        self.assertEqual(payload["issue_type"], "Complaint")
        self.assertEqual(payload["custom_driver"], "DRV-1")
        self.assertEqual(payload["project"], "PROJ-1")
        self.assertEqual(payload["via_customer_portal"], 1)
        doc.insert.assert_called_once_with(ignore_permissions=True)

    @patch.object(fleet_employee_services.frappe, "get_all")
    @patch.object(fleet_employee_services, "_my_issue")
    def test_complaint_messages_follow_a_validated_owned_issue(self, my_issue, get_all):
        my_issue.return_value = [{"name": "ISS-1", "status": "Open"}]
        get_all.return_value = [{"name": "COMM-1", "content": "<p>Received</p>"}]

        result = fleet_employee.get_complaint("ISS-1")

        my_issue.assert_called_once_with("ISS-1")
        self.assertEqual(get_all.call_args.kwargs["filters"]["reference_name"], "ISS-1")
        self.assertEqual(result["communications"][0]["content"], "Received")

    @patch.object(fleet_employee_services.frappe.db, "set_value")
    @patch.object(fleet_employee_services.frappe, "get_doc")
    @patch.object(fleet_employee_services, "_my_issue")
    def test_reply_reopens_the_owned_complaint(self, my_issue, get_doc, set_value):
        my_issue.return_value = [SimpleNamespace(name="ISS-1", status="Closed")]
        communication = MagicMock(name="communication")
        communication.name = "COMM-1"
        get_doc.return_value = communication

        result = fleet_employee.reply_to_complaint("ISS-1", "Please review again")

        payload = get_doc.call_args.args[0]
        self.assertEqual(payload["reference_doctype"], "Issue")
        self.assertEqual(payload["reference_name"], "ISS-1")
        communication.insert.assert_called_once_with(ignore_permissions=True)
        set_value.assert_called_once_with("Issue", "ISS-1", "status", "Open")
        self.assertEqual(result["status"], "Open")


class FleetOperationsScopeTest(FrappeTestCase):
    @patch.object(fleet_os, "_permitted_projects", return_value=(False, ["PROJ-1"]))
    @patch.object(fleet_os.frappe, "get_list", return_value=[])
    @patch.object(fleet_os.frappe, "has_permission", return_value=True)
    def test_assignment_queue_uses_permission_aware_project_filter(self, _permission, get_list, _scope):
        fleet_os.get_assignment_queue(project="PROJ-1")
        self.assertEqual(get_list.call_args.kwargs["filters"]["project"], ["in", ["PROJ-1"]])

    @patch.object(fleet_os, "_permitted_projects", return_value=(False, ["PROJ-1"]))
    @patch.object(fleet_os.frappe, "get_list")
    @patch.object(fleet_os.frappe, "has_permission", return_value=True)
    def test_out_of_scope_project_cannot_widen_queue(self, _permission, get_list, _scope):
        self.assertEqual(fleet_os.get_incident_queue(project="PROJ-2"), [])
        get_list.assert_not_called()


class FuelTopupLifecycleTest(FrappeTestCase):
    @patch("apex.salis.doctype.fuel_request.fuel_request.add_timeline_note")
    @patch("apex.salis.doctype.fuel_request.fuel_request.lock_fuel_quota")
    @patch("apex.salis.doctype.fuel_request.fuel_request.frappe.db.set_value")
    @patch("apex.salis.doctype.fuel_request.fuel_request.frappe.db.get_value")
    def test_topup_is_applied_once_and_reversed_once(self, get_value, set_value, _lock, _timeline):
        """The idempotence flag is the controller's to write, so the flag write is what
        is graded. The test used to set ``topup_applied`` by hand between the two calls,
        which left the one line that makes the guard work — ``db_set("topup_applied", 1)``
        — covered by nothing: deleting it kept the test green. Here the mock writes the
        attribute back the way ``db_set`` does, so a controller that stopped setting the
        flag would top the quota up twice and fail on the second call."""
        get_value.return_value = SimpleNamespace(monthly_litres=100.0, status="Active")
        doc = SimpleNamespace(
            name="FR-1",
            fuel_quota="FQ-1",
            topup_litres=20.0,
            topup_applied=0,
        )
        doc.db_set = MagicMock(
            side_effect=lambda fieldname, value: setattr(doc, fieldname, value)
        )

        FuelRequest._apply_topup(doc)
        self.assertEqual(set_value.call_args.args[2]["monthly_litres"], 120.0)
        doc.db_set.assert_called_once_with("topup_applied", 1)
        self.assertEqual(doc.topup_applied, 1, "the controller did not record the top-up")

        FuelRequest._apply_topup(doc)
        self.assertEqual(set_value.call_count, 1, "the quota was topped up twice")

        get_value.return_value = SimpleNamespace(monthly_litres=120.0, status="Active")
        FuelRequest._reverse_topup(doc)
        self.assertEqual(set_value.call_args.args[2]["monthly_litres"], 100.0)
        self.assertEqual(doc.topup_applied, 0, "the controller did not clear the flag")

        FuelRequest._reverse_topup(doc)
        self.assertEqual(set_value.call_count, 2, "the reversal ran twice")


class VehicleAssignmentLifecycleTest(FrappeTestCase):
    @patch("apex.salis.utils.lock_driver")
    @patch("apex.salis.utils.lock_vehicle")
    @patch("apex.salis.utils.frappe.get_doc")
    @patch("apex.salis.utils.frappe.get_all")
    @patch("apex.salis.utils.frappe.db.set_value")
    @patch("apex.salis.utils.frappe.db.get_value")
    def test_reassignment_clears_the_outgoing_driver_mirror(
        self, get_value, set_value, get_all, get_doc, _lock_vehicle, _lock_driver
    ):
        get_all.return_value = [SimpleNamespace(name="VA-OLD", driver="DRV-OLD")]
        get_value.side_effect = lambda doctype, name, field: (
            "VEH-1" if doctype == "Salis Driver" else "PROJ-1"
        )
        assignment = MagicMock(name="assignment")
        assignment.name = "VA-NEW"
        get_doc.return_value = assignment

        reassign_vehicle_driver("VEH-1", "DRV-NEW", "2026-08-12")

        set_value.assert_any_call("Salis Driver", "DRV-OLD", "current_vehicle", None)
        assignment.insert.assert_called_once_with()
        assignment.submit.assert_called_once_with()
