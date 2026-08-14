from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from apex.habitat.api import safety_map
from apex.habitat.doctype.maintenance_request import maintenance_request
from apex.habitat.doctype.maintenance_work_order import maintenance_work_order
from apex.habitat.report.maintenance_aging import maintenance_aging
from apex.apex_core.worklist.my_work_center import WORKLIST_REGISTRY


def _raising_frappe() -> MagicMock:
    fake = MagicMock()
    fake.PermissionError = frappe.PermissionError

    def throw(message, exc=None, **_kwargs):
        raise (exc or frappe.ValidationError)(message)

    fake.throw.side_effect = throw
    return fake


def _call(endpoint, *args, **kwargs):
    return getattr(endpoint, "__wrapped__", endpoint)(*args, **kwargs)


class TestMaintenanceRequestTransitions(TestCase):
    def test_validate_hook_covers_both_save_and_submit_lifecycles(self):
        hooks = __import__("apex.hooks", fromlist=["doc_events"])
        self.assertEqual(
            hooks.doc_events["Maintenance Request"],
            {
                "validate": "apex.habitat.doctype.maintenance_request.maintenance_request.validate"
            },
        )

    def test_status_is_server_owned_on_insert_and_direct_update(self):
        fake = _raising_frappe()
        new_doc = MagicMock(status="Closed")
        new_doc.is_new.return_value = True

        existing = MagicMock(status="Closed")
        existing.is_new.return_value = False
        existing.has_value_changed.return_value = True

        with (
            patch.object(maintenance_request, "frappe", fake),
            patch.object(maintenance_request, "_", side_effect=lambda message: message),
        ):
            maintenance_request._guard_status(new_doc)
            with self.assertRaises(frappe.PermissionError):
                maintenance_request._guard_status(existing)

        self.assertEqual(new_doc.status, "Open")

    def test_close_requires_write_permission_before_mutation(self):
        doc = MagicMock(docstatus=1, status="Resolved", name="MR-1")
        doc.name = "MR-1"
        doc.check_permission.side_effect = frappe.PermissionError("denied")
        fake = _raising_frappe()
        fake.get_doc.return_value = doc

        with patch.object(maintenance_request, "frappe", fake):
            with self.assertRaises(frappe.PermissionError):
                _call(maintenance_request.close_request, "MR-1")

        doc.db_set.assert_not_called()

    def test_close_moves_resolved_request_and_closes_native_assignments(self):
        doc = MagicMock(docstatus=1, status="Resolved", name="MR-1")
        doc.name = "MR-1"
        fake = _raising_frappe()
        fake.get_doc.return_value = doc

        with (
            patch.object(maintenance_request, "frappe", fake),
            patch.object(maintenance_request, "_", side_effect=lambda message: message),
            patch.object(
                maintenance_request, "close_all_assignments", create=True
            ) as close_assignments,
        ):
            result = _call(maintenance_request.close_request, "MR-1")

        fake.get_doc.assert_called_once_with(
            "Maintenance Request", "MR-1", for_update=True
        )
        doc.check_permission.assert_called_once_with("write")
        doc.db_set.assert_called_once_with("status", "Closed")
        close_assignments.assert_called_once_with("Maintenance Request", "MR-1")
        self.assertEqual(result, {"name": "MR-1", "status": "Closed"})

    def test_close_rolls_back_when_assignment_closure_fails(self):
        doc = MagicMock(docstatus=1, status="Resolved", name="MR-1")
        doc.name = "MR-1"
        fake = _raising_frappe()
        fake.get_doc.return_value = doc

        with (
            patch.object(maintenance_request, "frappe", fake),
            patch.object(maintenance_request, "_", side_effect=lambda message: message),
            patch.object(
                maintenance_request,
                "close_all_assignments",
                side_effect=RuntimeError("ToDo failure"),
                create=True,
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "ToDo failure"):
                _call(maintenance_request.close_request, "MR-1")

        fake.db.rollback.assert_called_once_with(
            save_point="maintenance_request_transition"
        )

    def test_reopen_requires_reason_and_only_reopens_resolved_or_closed(self):
        fake = _raising_frappe()
        doc = MagicMock(docstatus=1, status="Closed", name="MR-1")
        doc.name = "MR-1"
        fake.get_doc.return_value = doc

        with (
            patch.object(maintenance_request, "frappe", fake),
            patch.object(maintenance_request, "_", side_effect=lambda message: message),
        ):
            with self.assertRaises(frappe.ValidationError):
                _call(maintenance_request.reopen_request, "MR-1", "   ")

            result = _call(
                maintenance_request.reopen_request, "MR-1", "Repair failed again"
            )

        doc.db_set.assert_called_once_with("status", "Open")
        self.assertIn("Repair failed again", doc.add_comment.call_args.args[1])
        self.assertEqual(result, {"name": "MR-1", "status": "Open"})


class TestMaintenanceWorkOrderContract(TestCase):
    def _draft(self):
        return SimpleNamespace(
            planned_end_date=None,
            planned_start_date=None,
            actual_end_date=None,
            actual_start_date=None,
            maintenance_request="MR-1",
            name="MWO-NEW",
            procurement_items=[],
            total_procurement_cost=0,
            status="Draft",
            completion_photo=None,
        )

    def _completion_doc(self):
        doc = MagicMock(
            name="MWO-1",
            docstatus=1,
            status="In Progress",
            building="BLD-1",
            actual_start_date=date(2026, 8, 14),
            actual_end_date=None,
            completion_photo="/private/files/photo.jpg",
            completion_notes=None,
            total_procurement_cost=0,
            maintenance_request="MR-1",
        )
        doc.name = "MWO-1"
        return doc

    def _submit_for_request(self, work_order, request):
        fake = _raising_frappe()
        fake.db.exists.return_value = True
        fake.get_doc.return_value = request
        with (
            patch.object(maintenance_work_order, "frappe", fake),
            patch.object(maintenance_work_order, "_", side_effect=lambda text: text),
        ):
            maintenance_work_order.on_submit(work_order)

    def _complete_for_request(self, work_order, request):
        fake = _raising_frappe()
        fake.get_doc.side_effect = [work_order, request]
        fake.db.exists.side_effect = [True, False]
        with (
            patch.object(maintenance_work_order, "frappe", fake),
            patch.object(maintenance_work_order, "_", side_effect=lambda text: text),
            patch.object(maintenance_work_order, "today", return_value=date(2026, 8, 14)),
            patch.object(maintenance_work_order, "now", return_value="2026-08-14 10:00:00"),
            patch(
                "apex.habitat.doctype.housing_inventory.housing_inventory.reflect_completed_maintenance"
            ),
            patch("apex.habitat.maintenance_engine.post_maintenance_cost"),
        ):
            result = _call(
                maintenance_work_order.mark_completed,
                "MWO-1",
                completion_notes="Leak repaired",
            )
        return result

    def _cancel_for_request(self, work_order, request):
        fake = _raising_frappe()
        fake.db.exists.return_value = True
        fake.get_doc.return_value = request
        with (
            patch.object(maintenance_work_order, "frappe", fake),
            patch("apex.habitat.maintenance_engine.reverse_maintenance_cost"),
        ):
            maintenance_work_order.MaintenanceWorkOrder.on_cancel(work_order)

    def test_only_live_work_orders_block_a_new_order(self):
        fake = _raising_frappe()
        fake.db.exists.return_value = None
        doc = self._draft()

        with (
            patch.object(maintenance_work_order, "frappe", fake),
            patch.object(
                maintenance_work_order, "_", side_effect=lambda message: message
            ),
            patch.object(
                maintenance_work_order, "today", return_value=date(2026, 8, 14)
            ),
        ):
            maintenance_work_order.validate(doc)

        filters = fake.db.exists.call_args.args[1]
        self.assertEqual(filters["status"], ["in", ["Draft", "Planned", "In Progress"]])
        self.assertEqual(filters["docstatus"], ["!=", 2])

    def test_submit_starts_only_an_open_submitted_request(self):
        work_order = MagicMock(maintenance_request="MR-1")
        request = MagicMock(docstatus=1, status="Open", name="MR-1")
        self._submit_for_request(work_order, request)

        work_order.db_set.assert_called_once_with("status", "Planned")
        request.db_set.assert_called_once_with("status", "In Progress")

    def test_submit_rejects_unsubmitted_or_terminal_request_before_mutation(self):
        for docstatus, status in (
            (0, "Open"),
            (2, "Open"),
            (1, "Resolved"),
            (1, "Closed"),
        ):
            with self.subTest(docstatus=docstatus, status=status):
                work_order = MagicMock(maintenance_request="MR-1")
                request = MagicMock(docstatus=docstatus, status=status)

                with self.assertRaises(frappe.ValidationError):
                    self._submit_for_request(work_order, request)

                work_order.db_set.assert_not_called()
                request.db_set.assert_not_called()

    def test_completion_requires_notes(self):
        doc = MagicMock(
            name="MWO-1",
            docstatus=1,
            status="In Progress",
            building="BLD-1",
            actual_start_date=date(2026, 8, 14),
            actual_end_date=None,
            completion_photo="/private/files/photo.jpg",
            completion_notes=None,
            total_procurement_cost=0,
            maintenance_request="MR-1",
        )
        doc.name = "MWO-1"
        fake = _raising_frappe()
        fake.get_doc.return_value = doc

        with (
            patch.object(maintenance_work_order, "frappe", fake),
            patch.object(
                maintenance_work_order, "_", side_effect=lambda message: message
            ),
            patch.object(
                maintenance_work_order, "today", return_value=date(2026, 8, 14)
            ),
            patch.object(
                maintenance_work_order, "now", return_value="2026-08-14 10:00:00"
            ),
        ):
            with self.assertRaises(frappe.ValidationError):
                _call(maintenance_work_order.mark_completed, "MWO-1")

        doc.db_set.assert_not_called()

    def test_completion_resolves_request_with_same_notes(self):
        doc = self._completion_doc()
        request = MagicMock(docstatus=1, status="In Progress", name="MR-1")
        result = self._complete_for_request(doc, request)

        request.db_set.assert_called_once_with(
            {"status": "Resolved", "resolution_notes": "Leak repaired"},
        )
        self.assertEqual(result["status"], "Completed")

    def test_completion_rejects_unsubmitted_or_terminal_request_before_mutation(self):
        for docstatus, status in (
            (0, "In Progress"),
            (2, "In Progress"),
            (1, "Open"),
            (1, "Closed"),
        ):
            with self.subTest(docstatus=docstatus, status=status):
                work_order = self._completion_doc()
                request = MagicMock(docstatus=docstatus, status=status)

                with self.assertRaises(frappe.ValidationError):
                    self._complete_for_request(work_order, request)

                work_order.db_set.assert_not_called()
                request.db_set.assert_not_called()

    def test_cancel_only_restores_a_submitted_in_progress_request(self):
        for status, should_restore in (
            ("In Progress", True),
            ("Resolved", False),
            ("Closed", False),
        ):
            with self.subTest(status=status):
                work_order = MagicMock(name="MWO-1", maintenance_request="MR-1")
                work_order.name = "MWO-1"
                request = MagicMock(docstatus=1, status=status, name="MR-1")
                self._cancel_for_request(work_order, request)

                if should_restore:
                    request.db_set.assert_called_once_with("status", "Open")
                else:
                    request.db_set.assert_not_called()


class TestMaintenanceMetadata(TestCase):
    def test_resolved_submitted_requests_remain_active_until_closed(self):
        self.assertEqual(
            WORKLIST_REGISTRY["Maintenance Request"],
            {
                "active": ["Open", "In Progress", "Resolved"],
                "terminal": ["Closed"],
                "docstatus": 1,
            },
        )
        active = WORKLIST_REGISTRY["Maintenance Request"]["active"]
        self.assertEqual(
            safety_map._OPEN_MAINTENANCE_STATUSES,
            active,
        )
        self.assertEqual(
            maintenance_aging._OPEN_MAINTENANCE_STATUSES,
            active,
        )
        source = Path(maintenance_aging.__file__).with_suffix(".js").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            'options: ["", "Open", "In Progress", "Resolved"].join("\\n")',
            source,
        )

    def test_status_field_has_one_work_lifecycle_and_native_assignment_is_separate(
        self,
    ):
        metadata = json.loads(
            Path(__file__)
            .with_name("maintenance_request.json")
            .read_text(encoding="utf-8")
        )
        status = next(
            field for field in metadata["fields"] if field["fieldname"] == "status"
        )
        self.assertEqual(
            status["options"].splitlines(),
            ["Open", "In Progress", "Resolved", "Closed"],
        )
        self.assertTrue(status["read_only"])
        assigned_to = next(
            field for field in metadata["fields"] if field["fieldname"] == "assigned_to"
        )
        self.assertTrue(assigned_to["read_only"])
        self.assertNotIn("Assigned", {state["title"] for state in metadata["states"]})
        self.assertNotIn("Reopened", {state["title"] for state in metadata["states"]})
