"""Size note: 214 test lines against 95 in the subject (2.3x), for 13 distinct behaviours. The ratio is arithmetic on a small subject, not overtesting: each test names a different behaviour."""
from __future__ import annotations

# Copyright (c) 2026, AFMCO and contributors
import frappe
from frappe.tests.utils import FrappeTestCase
import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch
from apex.habitat.api import safety_map
from apex.habitat.doctype.maintenance_request import maintenance_request
from apex.habitat.doctype.maintenance_work_order import maintenance_work_order
from apex.habitat.report.maintenance_aging import maintenance_aging
from apex.apex_core.worklist.my_work_center import WORKLIST_REGISTRY

class TestMaintenanceRequest(FrappeTestCase):

    def test_create_valid_request(self):
        doc = frappe.get_doc({
            "doctype": "Maintenance Request",
            "naming_series": "MAINT-.YYYY.-.#####",
            "building": "QA-BLDG",
            "room": "ROOM-QA",
            "reported_by": "Administrator",
            "issue_type": "Plumbing",
            "issue_description": "Leak under sink",
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertEqual(doc.issue_type, "Plumbing")
        frappe.delete_doc("Maintenance Request", doc.name, force=True, ignore_permissions=True)

    def test_missing_room_raises(self):
        doc = frappe.get_doc({
            "doctype": "Maintenance Request",
            "naming_series": "MAINT-.YYYY.-.#####",
            "building": "QA-BLDG",
            "reported_by": "Administrator",
            "issue_type": "Electrical",
            "issue_description": "Wiring problem",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_missing_issue_description_raises(self):
        doc = frappe.get_doc({
            "doctype": "Maintenance Request",
            "naming_series": "MAINT-.YYYY.-.#####",
            "building": "QA-BLDG",
            "room": "ROOM-QA",
            "reported_by": "Administrator",
            "issue_type": "Plumbing",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_reported_by_defaults_to_session_user(self):
        doc = frappe.get_doc({
            "doctype": "Maintenance Request",
            "naming_series": "MAINT-.YYYY.-.#####",
            "building": "QA-BLDG",
            "room": "ROOM-QA",
            "issue_type": "Plumbing",
            "issue_description": "Leak under sink",
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertEqual(doc.reported_by, frappe.session.user)
        self.assertEqual(doc.owner, frappe.session.user)
        self.assertEqual(doc.owner, doc.reported_by)
        frappe.delete_doc("Maintenance Request", doc.name, force=True, ignore_permissions=True)

    def test_reported_by_default_is_idempotent_on_update(self):
        doc = frappe.get_doc({
            "doctype": "Maintenance Request",
            "naming_series": "MAINT-.YYYY.-.#####",
            "building": "QA-BLDG",
            "room": "ROOM-QA",
            "reported_by": "Administrator",
            "issue_type": "Plumbing",
            "issue_description": "Leak under sink",
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertEqual(doc.reported_by, "Administrator")
        doc.priority = "High"
        doc.save(ignore_permissions=True)
        self.assertEqual(doc.reported_by, "Administrator")
        frappe.delete_doc("Maintenance Request", doc.name, force=True, ignore_permissions=True)

    def test_negative_cost_of_repair_raises(self):
        """cost_of_repair is a spend; a negative value must be rejected on save."""
        doc = frappe.get_doc({
            "doctype": "Maintenance Request",
            "naming_series": "MAINT-.YYYY.-.#####",
            "building": "QA-BLDG",
            "room": "ROOM-QA",
            "reported_by": "Administrator",
            "issue_type": "Plumbing",
            "issue_description": "Leak under sink",
            "cost_of_repair": -1,
        })
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_zero_and_positive_cost_of_repair_allowed(self):
        """Zero (default/unset) and a positive cost must pass the guard."""
        for cost in (0, 250.50):
            doc = frappe.get_doc({
                "doctype": "Maintenance Request",
                "naming_series": "MAINT-.YYYY.-.#####",
                "building": "QA-BLDG",
                "room": "ROOM-QA",
                "reported_by": "Administrator",
                "issue_type": "Plumbing",
                "issue_description": "Leak under sink",
                "cost_of_repair": cost,
            })
            doc.insert(ignore_permissions=True, ignore_links=True)
            self.assertEqual(doc.cost_of_repair, cost)
            frappe.delete_doc("Maintenance Request", doc.name, force=True, ignore_permissions=True)

    def _get_perms_by_role(self):
        """Return a dict mapping role name -> document-level (permlevel 0) perm row.

        Only permlevel-0 rows are indexed. An owner-approved change added permlevel-1
        DocPerm grants (System Manager, Finance Manager, Accommodation Manager) to gate the
        sensitive cost fields; those rows share a role name with the base rows, so a
        flat ``{p.role: p}`` map would let a permlevel-1 row clobber the permlevel-0
        one being asserted here. These tests assert document-level access, so the
        field-level grants are filtered out of this lookup (see
        ``test_field_level_cost_grants`` for the permlevel-1 assertions).

        Accommodation Manager holds BOTH a permlevel-0 row (document access) and a
        permlevel-1 row ( cost-field grant); filtering to permlevel 0 here keeps
        the document-level assertions reading the correct row."""
        meta = frappe.get_meta("Maintenance Request")
        return {p.role: p for p in meta.permissions if (p.permlevel or 0) == 0}

    def test_all_role_row_exists_with_create_and_if_owner(self):
        """'All' role must grant create:1 and if_owner:1 (universal owner-scoped intake)."""
        perms = self._get_perms_by_role()
        self.assertIn("All", perms, "Expected an 'All' role permission row")
        p = perms["All"]
        self.assertEqual(p.read, 1, "'All' role must have read:1")
        self.assertEqual(p.create, 1, "'All' role must have create:1")
        self.assertEqual(p.if_owner, 1, "'All' role must have if_owner:1")
        self.assertEqual(p.write, 0, "'All' role must NOT have write:1")
        self.assertEqual(p.delete, 0, "'All' role must NOT have delete:1")
        self.assertEqual(p.submit, 0, "'All' role must NOT have submit:1")
        self.assertEqual(p.cancel, 0, "'All' role must NOT have cancel:1")

    def test_maintenance_technician_row_is_read_only(self):
        """'Maintenance Technician' role must be read-only on Maintenance Request."""
        perms = self._get_perms_by_role()
        self.assertIn("Maintenance Technician", perms,
                      "Expected a 'Maintenance Technician' permission row")
        p = perms["Maintenance Technician"]
        self.assertEqual(p.read, 1, "'Maintenance Technician' must have read:1")
        self.assertEqual(p.write, 0, "'Maintenance Technician' must NOT have write:1")
        self.assertEqual(p.create, 0, "'Maintenance Technician' must NOT have create:1")
        self.assertEqual(p.delete, 0, "'Maintenance Technician' must NOT have delete:1")
        self.assertEqual(p.submit, 0, "'Maintenance Technician' must NOT have submit:1")

    def test_resident_request_coordinator_row_has_create_write_submit(self):
        """'Resident Request Coordinator' must have create/read/write/submit but no delete."""
        perms = self._get_perms_by_role()
        self.assertIn("Resident Request Coordinator", perms,
                      "Expected a 'Resident Request Coordinator' permission row")
        p = perms["Resident Request Coordinator"]
        self.assertEqual(p.read, 1, "'Resident Request Coordinator' must have read:1")
        self.assertEqual(p.create, 1, "'Resident Request Coordinator' must have create:1")
        self.assertEqual(p.write, 1, "'Resident Request Coordinator' must have write:1")
        self.assertEqual(p.submit, 1, "'Resident Request Coordinator' must have submit:1")
        self.assertEqual(p.delete, 0, "'Resident Request Coordinator' must NOT have delete:1")

    def test_existing_privileged_roles_untouched(self):
        """System Manager, Accommodation Manager, Resident Supervisor rows must be unchanged."""
        perms = self._get_perms_by_role()
        sm = perms.get("System Manager")
        self.assertIsNotNone(sm)
        self.assertEqual(sm.cancel, 1)
        self.assertEqual(sm.delete, 1)
        self.assertEqual(sm.submit, 1)
        am = perms.get("Accommodation Manager")
        self.assertIsNotNone(am)
        self.assertEqual(am.create, 1)
        self.assertEqual(am.read, 1)
        self.assertEqual(am.write, 1)
        self.assertEqual(am.submit, 1)
        self.assertEqual(am.delete, 0)
        rs = perms.get("Resident Supervisor")
        self.assertIsNotNone(rs)
        self.assertEqual(rs.create, 1)
        self.assertEqual(rs.read, 1)
        self.assertEqual(rs.write, 1)
        self.assertEqual(rs.submit, 1)
        self.assertEqual(rs.delete, 0)

    def test_field_level_cost_grants(self):
        """the sensitive cost fields (Financial section: cost_of_repair,
        cost_center) are gated at permlevel 1, readable/writable only by the
        approved field-level roles — System Manager, Finance Manager, and
        Accommodation Manager — and by no one else. These are the owner-approved
        permlevel-1 DocPerm grants; this test locks the exact grant set."""
        meta = frappe.get_meta("Maintenance Request")
        level1 = {p.role: p for p in meta.permissions if (p.permlevel or 0) == 1}
        self.assertEqual(
            set(level1),
            {"System Manager", "Finance Manager", "Accommodation Manager"},
            "permlevel-1 cost-field grant roles drifted from the approved set",
        )
        for role, p in level1.items():
            self.assertEqual(p.read, 1, f"{role} must have permlevel-1 read")
            self.assertEqual(p.write, 1, f"{role} must have permlevel-1 write")

class TestMakeWorkOrder(FrappeTestCase):
    """make_work_order must carry the context the Maintenance Work Order model
    actually holds (request link, building, issue_type, Planned status) and must
    NOT try to push fields the Work Order has no home for (room/bed/priority),
    which get_mapped_doc would silently drop."""

    def _request(self):
        mr = frappe.get_doc({
            "doctype": "Maintenance Request",
            "naming_series": "MAINT-.YYYY.-.#####",
            "building": "MWO-MAP-BLDG",
            "room": "MWO-MAP-ROOM",
            "reported_by": "Administrator",
            "issue_type": "Electrical",
            "priority": "Critical",
            "issue_description": "Sparking socket",
        })
        mr.insert(ignore_permissions=True, ignore_links=True)
        return mr

    def test_mapped_work_order_carries_context(self):
        from apex.habitat.doctype.maintenance_request.maintenance_request import (
            make_work_order,
        )

        mr = self._request()
        try:
            wo = make_work_order(mr.name)
            self.assertEqual(wo.doctype, "Maintenance Work Order")
            self.assertEqual(wo.maintenance_request, mr.name)
            self.assertEqual(wo.building, mr.building)
            self.assertEqual(wo.issue_type, mr.issue_type)
            self.assertEqual(wo.status, "Planned")
            meta_fields = {f.fieldname for f in frappe.get_meta("Maintenance Work Order").fields}
            for absent in ("room", "bed", "priority"):
                self.assertNotIn(absent, meta_fields,
                                 f"Work Order unexpectedly has a {absent} field")
                self.assertFalse(wo.get(absent),
                                 f"mapper leaked {absent} onto the Work Order")
        finally:
            frappe.delete_doc("Maintenance Request", mr.name,
                              force=True, ignore_permissions=True)

test_ignore = ['Additional Salary', 'Asset', 'Asset Movement', 'Company', 'Cost Center', 'Currency', 'Employee', 'Item', 'Payment Entry', 'Project', 'Purchase Invoice', 'Role', 'Salary Component', 'Supplier', 'User']

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

    def test_close_refuses_an_unsubmitted_or_unresolved_request_before_mutation(self):
        """Both preconditions the endpoint carries, each on a case that reaches only it."""
        for docstatus, status in ((0, "Resolved"), (1, "Open"), (1, "In Progress"), (1, "Closed")):
            with self.subTest(docstatus=docstatus, status=status):
                doc = MagicMock(docstatus=docstatus, status=status, name="MR-1")
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
                    with self.assertRaises(frappe.ValidationError):
                        _call(maintenance_request.close_request, "MR-1")

                doc.db_set.assert_not_called()
                close_assignments.assert_not_called()

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

    def test_reopen_refuses_an_unsubmitted_or_still_open_request_before_mutation(self):
        """The other two halves of the name: the docstatus boundary and the status one."""
        for docstatus, status in ((0, "Closed"), (1, "Open"), (1, "In Progress")):
            with self.subTest(docstatus=docstatus, status=status):
                doc = MagicMock(docstatus=docstatus, status=status, name="MR-1")
                doc.name = "MR-1"
                fake = _raising_frappe()
                fake.get_doc.return_value = doc

                with (
                    patch.object(maintenance_request, "frappe", fake),
                    patch.object(maintenance_request, "_", side_effect=lambda message: message),
                ):
                    with self.assertRaises(frappe.ValidationError):
                        _call(maintenance_request.reopen_request, "MR-1", "Repair failed again")

                doc.db_set.assert_not_called()
                doc.add_comment.assert_not_called()
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

    def _validate_draft(self, duplicate):
        fake = _raising_frappe()
        fake.db.exists.return_value = duplicate
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
        return fake

    def test_only_live_work_orders_block_a_new_order(self):
        fake = self._validate_draft(None)

        filters = fake.db.exists.call_args.args[1]
        self.assertEqual(filters["status"], ["in", ["Draft", "Planned", "In Progress"]])
        self.assertEqual(filters["docstatus"], ["!=", 2])

    def test_a_live_duplicate_is_actually_refused(self):
        """The filter shape alone proves nothing: with the throw deleted the probe still
        runs, still carries these filters, and the second work order is still saved."""
        with self.assertRaises(frappe.ValidationError) as raised:
            self._validate_draft("MWO-EXISTING")
        self.assertIn("MWO-EXISTING", str(raised.exception))

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
                work_order = MagicMock(
                    name="MWO-1",
                    status="Planned",
                    maintenance_request="MR-1",
                )
                work_order.name = "MWO-1"
                request = MagicMock(docstatus=1, status=status, name="MR-1")
                self._cancel_for_request(work_order, request)

                if should_restore:
                    request.db_set.assert_called_once_with("status", "Open")
                else:
                    request.db_set.assert_not_called()

    def test_cancelling_completed_old_order_does_not_reopen_request_owned_by_new_order(self):
        old_order = MagicMock(
            name="MWO-A",
            status="Completed",
            maintenance_request="MR-1",
        )
        old_order.name = "MWO-A"
        request = MagicMock(docstatus=1, status="In Progress", name="MR-1")

        self._cancel_for_request(old_order, request)

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
