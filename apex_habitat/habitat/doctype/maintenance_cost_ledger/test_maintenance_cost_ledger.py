import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

# Dependencies whose absence in the test DB must not fail link validation.
test_ignore = [
    "Company",
    "Item",
    "Maintenance Material",
    "User",
]

SOURCE_DOCTYPE = "Maintenance Work Order"


class TestMaintenanceCostLedger(FrappeTestCase):
    """Completing a Maintenance Work Order posts one immutable Maintenance Cost
    Ledger row per priced procurement item; re-completion is idempotent (no
    duplicate); cancel reverses with negative mirror rows (never a delete)."""

    def _ensure_building(self):
        if not frappe.db.exists("Accommodation Building", "MCL-TEST-BLDG"):
            frappe.get_doc({
                "doctype": "Accommodation Building",
                "building_name": "MCL-TEST-BLDG",
                "total_capacity": 4,
            }).insert(ignore_permissions=True, ignore_links=True)
        if not frappe.db.exists("Accommodation Room", "MCL-TEST-ROOM"):
            frappe.get_doc({
                "doctype": "Accommodation Room",
                "building": "MCL-TEST-BLDG",
                "room_number": "MCL-TEST-ROOM",
                "bed_capacity": 2,
            }).insert(ignore_permissions=True, ignore_links=True)
        return "MCL-TEST-BLDG", "MCL-TEST-ROOM"

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
            "work_description": "Replace worn parts",
            "planned_start_date": "2026-06-10",
            "planned_end_date": "2026-06-12",
            "actual_start_date": "2026-06-11",
            "actual_end_date": "2026-06-12",
            "completion_photo": "/files/done.png",
            # Two priced lines + one zero-cost line (the zero line posts nothing).
            "procurement_items": [
                {"item_description": "Tap washer", "quantity": 2, "estimated_cost": 25},
                {"item_description": "Sealant tube", "quantity": 1, "estimated_cost": 40},
                {"item_description": "Free offcut", "quantity": 1, "estimated_cost": 0},
            ],
        })
        wo.insert(ignore_permissions=True, ignore_links=True)
        wo.submit()
        return wo

    def _originals(self, wo_name):
        return frappe.get_all(
            "Maintenance Cost Ledger",
            filters={
                "source_doctype": SOURCE_DOCTYPE,
                "source_name": wo_name,
                "reversal_of": ["is", "not set"],
            },
            fields=["name", "amount", "source_detail_no", "is_cancelled"],
        )

    def _reversals(self, wo_name):
        return frappe.get_all(
            "Maintenance Cost Ledger",
            filters={
                "source_doctype": SOURCE_DOCTYPE,
                "source_name": wo_name,
                "reversal_of": ["is", "set"],
            },
            fields=["name", "amount", "is_cancelled"],
        )

    def _all_rows(self, wo_name):
        return frappe.get_all(
            "Maintenance Cost Ledger",
            filters={"source_doctype": SOURCE_DOCTYPE, "source_name": wo_name},
            pluck="name",
        )

    def _net_amount(self, wo_name):
        return sum(
            flt(r.amount)
            for r in frappe.get_all(
                "Maintenance Cost Ledger",
                filters={"source_doctype": SOURCE_DOCTYPE, "source_name": wo_name},
                fields=["amount"],
            )
        )

    def test_post_idempotent_and_cancel_reverses(self):
        from apex_habitat.habitat.doctype.maintenance_work_order.maintenance_work_order import (
            mark_completed,
        )

        building, room = self._ensure_building()
        mr = self._submit_request(building, room)
        wo = self._submit_work_order(mr, building)
        try:
            # One immutable row per PRICED item (the zero-cost line posts nothing).
            mark_completed(wo.name)
            originals = self._originals(wo.name)
            self.assertEqual(len(originals), 2,
                             "one ledger row per priced procurement item")
            self.assertEqual(flt(self._net_amount(wo.name)), 65.0,
                             "net cost equals the sum of priced items (25 + 40)")

            # Re-running completion posts nothing new (idempotent).
            from apex_habitat.habitat.maintenance_engine import post_maintenance_cost
            wo.reload()
            self.assertEqual(post_maintenance_cost(wo), 0, "re-post must be idempotent")
            self.assertEqual(len(self._originals(wo.name)), 2)

            # Cancel reverses with negative mirror rows, never a delete.
            wo.reload()
            wo.cancellation_reason = "Duplicate work order"
            wo.cancel()

            self.assertEqual(len(self._originals(wo.name)), 2,
                             "originals are preserved for audit (reverse-not-delete)")
            reversals = self._reversals(wo.name)
            self.assertEqual(len(reversals), 2, "one reversal per original")
            self.assertTrue(all(r.is_cancelled for r in reversals),
                            "reversal rows flag is_cancelled")
            self.assertEqual(flt(self._net_amount(wo.name)), 0.0,
                             "Work Order nets to zero after cancellation")
        finally:
            self._cleanup(wo, mr)

    def test_ledger_row_is_immutable(self):
        from apex_habitat.habitat.doctype.maintenance_work_order.maintenance_work_order import (
            mark_completed,
        )

        building, room = self._ensure_building()
        mr = self._submit_request(building, room)
        wo = self._submit_work_order(mr, building)
        try:
            mark_completed(wo.name)
            row_name = self._originals(wo.name)[0].name
            row = frappe.get_doc("Maintenance Cost Ledger", row_name)
            row.amount = 9999
            with self.assertRaises(frappe.ValidationError):
                row.save(ignore_permissions=True)
        finally:
            self._cleanup(wo, mr)

    def _cleanup(self, wo, mr):
        if frappe.db.exists("Maintenance Work Order", wo.name):
            wo.reload()
            if wo.docstatus == 1:
                wo.cancellation_reason = wo.cancellation_reason or "cleanup"
                wo.cancel()
            frappe.delete_doc("Maintenance Work Order", wo.name,
                              force=True, ignore_permissions=True)
        for row in self._all_rows(wo.name):
            frappe.delete_doc("Maintenance Cost Ledger", row,
                              force=True, ignore_permissions=True)
        for row in frappe.get_all(
            "Accommodation Ledger",
            filters={"source_doctype": SOURCE_DOCTYPE, "source_name": wo.name},
            pluck="name",
        ):
            frappe.delete_doc("Accommodation Ledger", row,
                              force=True, ignore_permissions=True)
        if frappe.db.exists("Maintenance Request", mr.name):
            mr.reload()
            if mr.docstatus == 1:
                mr.cancel()
            frappe.delete_doc("Maintenance Request", mr.name,
                              force=True, ignore_permissions=True)
