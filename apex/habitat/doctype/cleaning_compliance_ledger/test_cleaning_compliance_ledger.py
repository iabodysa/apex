# Copyright (c) 2026, AFMCO and contributors
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.cleaning_engine import (
    post_cleaning_compliance,
    reverse_cleaning_compliance,
)

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

_AREA_PHOTOS = [
    {"area": "Bathrooms", "status": "Cleaned", "photo": "/files/qa-bath.jpg"},
    {"area": "Kitchen", "status": "Cleaned", "photo": "/files/qa-kitchen.jpg"},
    {"area": "Corridors", "status": "N/A", "note": "No corridor in this unit"},
]


class TestCleaningComplianceLedger(FrappeTestCase):
    def setUp(self):
        self.building = (
            frappe.get_doc(
                {
                    "doctype": "Building",
                    "building_name": f"CCL Bldg {self._testMethodName}",
                    "status": "Active",
                }
            )
            .insert(ignore_permissions=True)
            .name
        )
        self.rooms = []
        for n in (1, 2):
            self.rooms.append(
                frappe.get_doc(
                    {
                        "doctype": "Room",
                        "building": self.building,
                        "room_number": f"CCL-{self._testMethodName}-{n}",
                    }
                )
                .insert(ignore_permissions=True)
                .name
            )

    def _make_log(self):
        doc = frappe.get_doc(
            {
                "doctype": "Cleaning Log",
                "naming_series": "CLEAN-.YYYY.-.####",
                "building": self.building,
                "cleaning_date": "2026-06-15",
                "area_photos": list(_AREA_PHOTOS),
                "room_details": [
                    {"room": self.rooms[0], "room_status": "Cleaned", "cleaned": 1},
                    {"room": self.rooms[1], "room_status": "Skipped", "skip_reason": "Locked"},
                ],
            }
        )
        doc.insert(ignore_permissions=True)
        return doc

    def _ledger_rows(self, cleaning_log, **extra):
        filters = {"cleaning_log": cleaning_log}
        filters.update(extra)
        return frappe.get_all(
            "Cleaning Compliance Ledger",
            filters=filters,
            fields=["name", "room", "cleaned", "skip_reason", "is_cancelled", "reversal_of"],
        )

    def tearDown(self):
        frappe.db.rollback()

    def test_docperm_no_create_write(self):
        """No role may create or write the ledger — system-written only."""
        meta = frappe.get_meta("Cleaning Compliance Ledger")
        for p in meta.permissions:
            self.assertFalse(p.create, f"{p.role} must not have create")
            self.assertFalse(p.write, f"{p.role} must not have write")

    def test_submit_posts_one_row_per_room(self):
        """A submitted Cleaning Log posts exactly one live ledger row per room."""
        doc = self._make_log()
        doc.submit()
        live = self._ledger_rows(doc.name, is_cancelled=0)
        self.assertEqual(len(live), 2)
        by_room = {r.room: r for r in live}
        self.assertEqual(by_room[self.rooms[0]].cleaned, 1)
        self.assertEqual(by_room[self.rooms[1]].cleaned, 0)
        self.assertEqual(by_room[self.rooms[1]].skip_reason, "Locked")

    def test_repost_is_idempotent(self):
        """Re-running the engine on an already-posted log adds no rows."""
        doc = self._make_log()
        doc.submit()
        before = len(self._ledger_rows(doc.name))
        posted = post_cleaning_compliance(doc)
        self.assertEqual(posted, 0)
        self.assertEqual(len(self._ledger_rows(doc.name)), before)

    def test_cancel_reverses(self):
        """Cancel posts a mirror per original and flags both is_cancelled, so the
        live (non-cancelled) set is empty and nothing is deleted."""
        doc = self._make_log()
        doc.submit()
        originals = self._ledger_rows(doc.name, is_cancelled=0)
        self.assertEqual(len(originals), 2)
        doc.cancel()
        self.assertEqual(len(self._ledger_rows(doc.name, is_cancelled=0)), 0)
        all_rows = self._ledger_rows(doc.name)
        self.assertEqual(len(all_rows), 4)
        reversals = [r for r in all_rows if r.reversal_of]
        self.assertEqual(len(reversals), 2)

    def test_reverse_is_idempotent(self):
        """Reversing twice posts at most one mirror per original row."""
        doc = self._make_log()
        doc.submit()
        reverse_cleaning_compliance(doc.name)
        again = reverse_cleaning_compliance(doc.name)
        self.assertEqual(again, 0)
        self.assertEqual(len(self._ledger_rows(doc.name)), 4)

    def test_editing_a_posted_row_is_refused(self):
        """A row posted by the engine is immutable outside its own insert."""
        doc = self._make_log()
        doc.submit()
        row_name = self._ledger_rows(doc.name)[0].name
        row = frappe.get_doc("Cleaning Compliance Ledger", row_name)
        row.cleaned = 0
        with self.assertRaises(frappe.ValidationError):
            row.save(ignore_permissions=True)

    def test_deleting_a_posted_row_without_system_manager_is_refused(self):
        doc = self._make_log()
        doc.submit()
        row_name = self._ledger_rows(doc.name)[0].name
        with patch("frappe.get_roles", return_value=["Employee"]):
            with self.assertRaises(frappe.ValidationError):
                frappe.delete_doc(
                    "Cleaning Compliance Ledger", row_name, ignore_permissions=True
                )
        self.assertTrue(frappe.db.exists("Cleaning Compliance Ledger", row_name))

    def test_deleting_a_posted_row_as_system_manager_is_allowed(self):
        """Non-vacuity control: the guard is role-gated, not an absolute refusal."""
        doc = self._make_log()
        doc.submit()
        row_name = self._ledger_rows(doc.name)[0].name
        frappe.delete_doc("Cleaning Compliance Ledger", row_name, ignore_permissions=True)
        self.assertFalse(frappe.db.exists("Cleaning Compliance Ledger", row_name))
