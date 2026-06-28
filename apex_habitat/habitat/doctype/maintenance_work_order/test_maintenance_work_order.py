# Copyright (c) 2026, AFMCO and contributors
import frappe
from frappe.tests.utils import FrappeTestCase

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


class TestMaintenanceWorkOrder(FrappeTestCase):

    def test_docperm_maintenance_technician(self):
        """Maintenance Technician must have read/write on MWO (no submit/cancel/create/delete)."""
        meta = frappe.get_meta("Maintenance Work Order")
        roles = {p.role: p for p in meta.permissions}
        self.assertIn("Maintenance Technician", roles, "Maintenance Technician perm row is missing")
        p = roles["Maintenance Technician"]
        self.assertEqual(p.read, 1)
        self.assertEqual(p.write, 1)
        self.assertFalse(getattr(p, "submit", 0), "Maintenance Technician must NOT have submit")
        self.assertFalse(getattr(p, "cancel", 0), "Maintenance Technician must NOT have cancel")
        self.assertFalse(getattr(p, "create", 0), "Maintenance Technician must NOT have create")
        self.assertFalse(getattr(p, "delete", 0), "Maintenance Technician must NOT have delete")

    def test_create_valid_work_order(self):
        doc = frappe.get_doc({
            "doctype": "Maintenance Work Order",
            "naming_series": "MWO-.YYYY.-.####",
            "maintenance_request": "MAINT-QA-001",
            "work_description": "Fix pipe leak in room 101",
            "planned_start_date": "2026-06-10",
            "planned_end_date": "2026-06-12",
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertIsNotNone(doc.name)
        frappe.delete_doc("Maintenance Work Order", doc.name, force=True, ignore_permissions=True)

    def test_missing_work_description_raises(self):
        doc = frappe.get_doc({
            "doctype": "Maintenance Work Order",
            "naming_series": "MWO-.YYYY.-.####",
            "maintenance_request": "MAINT-QA-001",
            "planned_start_date": "2026-06-10",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_end_date_before_start_raises(self):
        from apex_habitat.habitat.doctype.maintenance_work_order.maintenance_work_order import validate

        doc = frappe.get_doc({
            "doctype": "Maintenance Work Order",
            "maintenance_request": "MAINT-QA-001",
            "work_description": "Repair work",
            "planned_start_date": "2026-06-15",
            "planned_end_date": "2026-06-10",
        })
        with self.assertRaises(frappe.ValidationError):
            validate(doc)


class TestMaintenanceWorkOrderCancel(FrappeTestCase):
    """on_cancel must net out the Accommodation Ledger memo the Work Order posted
    on completion and release the linked Maintenance Request off Closed/In
    Progress back to Open — so a cancel leaves no orphan ledger row or stuck
    ticket."""

    def _ensure_location(self):
        if not frappe.db.exists("Accommodation Building", "MWO-CANCEL-BLDG"):
            frappe.get_doc({
                "doctype": "Accommodation Building",
                "building_name": "MWO-CANCEL-BLDG",
                "total_capacity": 4,
            }).insert(ignore_permissions=True, ignore_links=True)
        if not frappe.db.exists("Accommodation Room", "MWO-CANCEL-ROOM"):
            frappe.get_doc({
                "doctype": "Accommodation Room",
                "building": "MWO-CANCEL-BLDG",
                "room_number": "MWO-CANCEL-ROOM",
                "bed_capacity": 2,
            }).insert(ignore_permissions=True, ignore_links=True)
        return "MWO-CANCEL-BLDG", "MWO-CANCEL-ROOM"

    def _submit_request(self, building, room):
        mr = frappe.get_doc({
            "doctype": "Maintenance Request",
            "naming_series": "MAINT-.YYYY.-.#####",
            "building": building,
            "room": room,
            "reported_by": "Administrator",
            "issue_type": "Plumbing",
            "issue_description": "Leak under sink",
        })
        mr.insert(ignore_permissions=True, ignore_links=True)
        mr.submit()
        return mr

    def _submit_work_order(self, mr, building):
        wo = frappe.get_doc({
            "doctype": "Maintenance Work Order",
            "naming_series": "MWO-.YYYY.-.####",
            "maintenance_request": mr.name,
            "building": building,
            "work_description": "Replace the worn washer",
            "planned_start_date": "2026-06-10",
            "planned_end_date": "2026-06-12",
            "actual_start_date": "2026-06-11",
            "actual_end_date": "2026-06-12",
            "completion_photo": "/files/done.png",
            # A priced procurement line so mark_completed posts a ledger memo.
            "procurement_items": [{"item_description": "Tap washer", "quantity": 1, "estimated_cost": 25}],
        })
        wo.insert(ignore_permissions=True, ignore_links=True)
        wo.submit()
        return wo

    def _ledger_rows(self, wo_name):
        return frappe.get_all(
            "Accommodation Ledger",
            filters={"source_doctype": "Maintenance Work Order", "source_name": wo_name},
            pluck="name",
        )

    def _cost_ledger_rows(self, wo_name, **extra):
        f = {"source_doctype": "Maintenance Work Order", "source_name": wo_name}
        f.update(extra)
        return frappe.get_all(
            "Maintenance Cost Ledger", filters=f, fields=["name", "amount", "reversal_of"]
        )

    def test_cancel_reverses_memo_and_releases_request(self):
        from apex_habitat.habitat.doctype.maintenance_work_order.maintenance_work_order import (
            mark_completed,
        )

        building, room = self._ensure_location()
        mr = self._submit_request(building, room)
        wo = self._submit_work_order(mr, building)
        try:
            # Completion posts the aggregate memo + the immutable per-item cost
            # ledger original, and drives the request to Closed.
            mark_completed(wo.name)
            self.assertEqual(len(self._ledger_rows(wo.name)), 1,
                             "completion should post exactly one ledger memo")
            originals = self._cost_ledger_rows(wo.name, reversal_of=["is", "not set"])
            self.assertEqual(len(originals), 1,
                             "completion should post one Maintenance Cost Ledger original")
            self.assertEqual(originals[0]["amount"], 25)
            self.assertEqual(
                frappe.db.get_value("Maintenance Request", mr.name, "status"), "Closed")

            # Cancel must undo the memo, reverse the immutable cost ledger, and
            # release the request.
            wo.reload()
            wo.cancellation_reason = "Duplicate work order"
            wo.cancel()

            self.assertEqual(self._ledger_rows(wo.name), [],
                             "cancel must delete the orphan ledger memo")
            # The immutable cost ledger is reversed (negative mirror), never deleted:
            # the original survives and a reversal_of row nets the total to zero.
            rows = self._cost_ledger_rows(wo.name)
            self.assertEqual(len(rows), 2,
                             "cancel must add a reversal row, not delete the original")
            self.assertTrue(any(r["reversal_of"] for r in rows),
                            "a reversal_of mirror row must exist after cancel")
            self.assertEqual(sum(r["amount"] for r in rows), 0,
                             "the reversed cost ledger must net to zero")
            self.assertEqual(
                frappe.db.get_value("Maintenance Request", mr.name, "status"), "Open",
                "cancel must release the request off Closed")
        finally:
            if frappe.db.exists("Maintenance Work Order", wo.name):
                wo.reload()
                if wo.docstatus == 1:
                    wo.cancellation_reason = wo.cancellation_reason or "cleanup"
                    wo.cancel()
                frappe.delete_doc("Maintenance Work Order", wo.name,
                                  force=True, ignore_permissions=True)
            for row in self._ledger_rows(wo.name):
                frappe.delete_doc("Accommodation Ledger", row,
                                  force=True, ignore_permissions=True)
            for row in self._cost_ledger_rows(wo.name):
                frappe.delete_doc("Maintenance Cost Ledger", row["name"],
                                  force=True, ignore_permissions=True)
            if frappe.db.exists("Maintenance Request", mr.name):
                mr.reload()
                if mr.docstatus == 1:
                    mr.cancel()
                frappe.delete_doc("Maintenance Request", mr.name,
                                  force=True, ignore_permissions=True)
