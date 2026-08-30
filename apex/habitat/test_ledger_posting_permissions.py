# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.maintenance_engine import post_maintenance_cost


test_dependencies = ["Building", "Room"]
test_ignore = [
    "Item",
    "Maintenance Material",
    "Facility Asset",
    "Safety Round",
    "Cleaning Log",
]

BUILDING = "_Test Building"


class LedgerPostingPermissionCase(FrappeTestCase):
    def setUp(self):
        super().setUp()
        self.addCleanup(frappe.set_user, "Administrator")

    def user_with_role(self, role, scoped_to_building=False):
        email = f"{frappe.generate_hash(length=8)}@example.com"
        frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": "Grant Probe",
                "send_welcome_email": 0,
                "roles": [{"role": role}],
            }
        ).insert(ignore_permissions=True)
        self.addCleanup(
            lambda: frappe.delete_doc("User", email, force=True, ignore_permissions=True)
        )
        if scoped_to_building:
            frappe.get_doc(
                {
                    "doctype": "User Permission",
                    "user": email,
                    "allow": "Building",
                    "for_value": BUILDING,
                }
            ).insert(ignore_permissions=True)
        return email

    def as_role(self, role, scoped_to_building=False):
        frappe.set_user(self.user_with_role(role, scoped_to_building))

    def insert_as(self, role, payload, scoped_to_building=False):
        self.as_role(role, scoped_to_building)
        doc = frappe.get_doc(payload).insert()
        frappe.set_user("Administrator")
        self.addCleanup(
            lambda dt=doc.doctype, dn=doc.name: frappe.db.delete(dt, {"name": dn})
        )
        return doc

    def refuse_as(self, role, payload, scoped_to_building=False):
        self.as_role(role, scoped_to_building)
        with self.assertRaises(frappe.PermissionError):
            frappe.get_doc(payload).insert()
        frappe.set_user("Administrator")


def _movement_ledger_row():
    return {
        "doctype": "Facility Asset Movement Ledger",
        "posting_datetime": "2026-03-02 09:00:00",
        "source_doctype": "Facility Asset Movement",
        "source_name": "_T-FAM-" + frappe.generate_hash(length=6),
    }


def _cost_ledger_row():
    return {
        "doctype": "Maintenance Cost Ledger",
        "posting_date": "2026-03-02",
        "building": BUILDING,
        "item_description": "Grant probe",
        "amount": 10,
        "source_doctype": "Maintenance Work Order",
        "source_name": "_T-MWO-" + frappe.generate_hash(length=6),
        "source_detail_no": 1,
    }


def _cleaning_ledger_row():
    return {
        "doctype": "Cleaning Compliance Ledger",
        "posting_date": "2026-03-02",
        "building": BUILDING,
        "cleaned": 1,
        "source_doctype": "Cleaning Log",
        "source_name": "_T-CL-" + frappe.generate_hash(length=6),
    }


def _finding_ledger_row():
    return {
        "doctype": "Safety Finding Ledger",
        "posting_date": "2026-03-02",
        "building": BUILDING,
        "finding": "Grant probe",
        "source_doctype": "Safety Task Execution",
        "source_name": "_T-STE-" + frappe.generate_hash(length=6),
        "source_detail_no": 1,
    }


def _accommodation_ledger_row():
    return {
        "doctype": "Accommodation Ledger",
        "posting_date": "2026-03-02",
        "building": BUILDING,
        "ledger_type": "Maintenance",
        "total_site_cost": 10,
        "capacity_denominator": 0,
        "employee_daily_share": 0,
        "posting_mode": "Operational Memo",
        "allocation_basis": "Direct",
        "source_doctype": "Maintenance Work Order",
        "source_name": "_T-MWO-" + frappe.generate_hash(length=6),
    }


class TestAssetMovementLedgerPostsWithoutBypass(LedgerPostingPermissionCase):
    def test_accommodation_manager_posts_the_movement_ledger(self):
        self.assertTrue(self.insert_as("Accommodation Manager", _movement_ledger_row()).name)

    def test_procurement_supervisor_posts_the_movement_ledger(self):
        self.assertTrue(self.insert_as("Procurement Supervisor", _movement_ledger_row()).name)

    def test_internal_auditor_is_refused_the_movement_ledger(self):
        self.refuse_as("Internal Auditor", _movement_ledger_row())


class TestMaintenanceCostLedgerPostsWithoutBypass(LedgerPostingPermissionCase):
    def test_maintenance_technician_posts_the_cost_ledger(self):
        self.assertTrue(self.insert_as("Maintenance Technician", _cost_ledger_row()).name)

    def test_internal_auditor_is_refused_the_cost_ledger(self):
        self.refuse_as("Internal Auditor", _cost_ledger_row())

    def test_maintenance_engine_posts_the_cost_ledger_as_the_technician(self):
        work_order = _draft_work_order(self)
        self.as_role("Maintenance Technician")
        posted = post_maintenance_cost(work_order)
        frappe.set_user("Administrator")
        self.addCleanup(
            lambda: frappe.db.delete("Maintenance Cost Ledger", {"source_name": work_order.name})
        )
        self.assertEqual(posted, 1)


class TestCleaningComplianceLedgerPostsWithoutBypass(LedgerPostingPermissionCase):
    def test_cleaning_supervisor_posts_the_compliance_ledger(self):
        doc = self.insert_as("Cleaning Supervisor", _cleaning_ledger_row(), scoped_to_building=True)
        self.assertTrue(doc.name)

    def test_internal_auditor_is_refused_the_compliance_ledger(self):
        self.refuse_as("Internal Auditor", _cleaning_ledger_row())


class TestSafetyFindingLedgerPostsWithoutBypass(LedgerPostingPermissionCase):
    def test_resident_supervisor_posts_the_finding_ledger(self):
        doc = self.insert_as("Resident Supervisor", _finding_ledger_row(), scoped_to_building=True)
        self.assertTrue(doc.name)

    def test_safety_officer_inside_the_building_is_still_refused_the_finding_ledger(self):
        self.refuse_as("Safety Officer", _finding_ledger_row(), scoped_to_building=True)


class TestAccommodationLedgerPostsWithoutBypass(LedgerPostingPermissionCase):
    def test_accommodation_manager_posts_the_accommodation_ledger(self):
        self.assertTrue(
            self.insert_as("Accommodation Manager", _accommodation_ledger_row()).name
        )

    def test_maintenance_technician_posts_the_accommodation_ledger(self):
        self.assertTrue(
            self.insert_as("Maintenance Technician", _accommodation_ledger_row()).name
        )

    def test_internal_auditor_is_refused_the_accommodation_ledger(self):
        self.refuse_as("Internal Auditor", _accommodation_ledger_row())


class TestSafetySetupWritesTemplatesWithoutBypass(LedgerPostingPermissionCase):
    def _template_row(self):
        return {
            "doctype": "Scheduled Task Template",
            "template_name": "Grant Probe " + frappe.generate_hash(length=6),
            "task_type": "Safety",
            "frequency": "Monthly",
            "is_active": 1,
        }

    def test_accommodation_manager_creates_and_saves_a_template(self):
        doc = self.insert_as("Accommodation Manager", self._template_row())
        self.as_role("Accommodation Manager")
        reopened = frappe.get_doc("Scheduled Task Template", doc.name)
        reopened.is_active = 0
        reopened.save()
        frappe.set_user("Administrator")
        self.assertEqual(
            frappe.db.get_value("Scheduled Task Template", doc.name, "is_active"), 0
        )

    def test_safety_officer_is_refused_a_template(self):
        self.refuse_as("Safety Officer", self._template_row())


class TestNoHabitatRoleDeletesAMaintenanceRequest(LedgerPostingPermissionCase):
    def _request(self):
        doc = frappe.get_doc(
            {
                "doctype": "Maintenance Request",
                "building": BUILDING,
                "room": _test_room(),
                "issue_type": "Other",
                "reported_by": "Administrator",
                "issue_description": "Grant probe",
                "status": "Open",
            }
        ).insert(ignore_permissions=True)
        return doc.name

    def test_accommodation_manager_is_refused_the_delete(self):
        name = self._request()
        self.addCleanup(
            lambda: frappe.delete_doc(
                "Maintenance Request", name, force=True, ignore_permissions=True
            )
        )
        self.as_role("Accommodation Manager")
        with self.assertRaises(frappe.PermissionError):
            frappe.delete_doc("Maintenance Request", name)
        frappe.set_user("Administrator")

    def test_maintenance_technician_is_refused_the_delete(self):
        name = self._request()
        self.addCleanup(
            lambda: frappe.delete_doc(
                "Maintenance Request", name, force=True, ignore_permissions=True
            )
        )
        self.as_role("Maintenance Technician")
        with self.assertRaises(frappe.PermissionError):
            frappe.delete_doc("Maintenance Request", name)
        frappe.set_user("Administrator")


def _test_room():
    return frappe.db.get_value("Room", {"building": BUILDING}, "name")


def _draft_work_order(case):
    request = frappe.get_doc(
        {
            "doctype": "Maintenance Request",
            "building": BUILDING,
            "room": _test_room(),
            "issue_type": "Other",
            "reported_by": "Administrator",
            "issue_description": "Grant probe",
            "status": "Open",
        }
    ).insert(ignore_permissions=True)
    case.addCleanup(
        lambda: frappe.delete_doc(
            "Maintenance Request", request.name, force=True, ignore_permissions=True
        )
    )
    work_order = frappe.get_doc(
        {
            "doctype": "Maintenance Work Order",
            "maintenance_request": request.name,
            "building": BUILDING,
            "planned_start_date": "2026-03-01",
            "work_description": "Grant probe",
            "actual_end_date": "2026-03-02",
            "procurement_items": [
                {"item_description": "Grant probe", "estimated_cost": 25}
            ],
        }
    ).insert(ignore_permissions=True)
    case.addCleanup(
        lambda: frappe.delete_doc(
            "Maintenance Work Order", work_order.name, force=True, ignore_permissions=True
        )
    )
    return work_order
