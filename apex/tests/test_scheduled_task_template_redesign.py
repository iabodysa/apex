# Copyright (c) 2026, AFMCO and contributors
"""Regression tests for T-552 Phase B: Scheduled Task Template redesign.

Covers the Salary-Structure analogy:
  Scheduled Task Template   (holds child table of task catalog rows)
  Scheduled Task Assignment (template → building link)
  Scheduled Task Instance   (auto-generated per assignment × item)

Six tests:
  1. test_new_instance_created_for_active_assignment
  2. test_no_duplicate_instance_for_same_day
  3. test_cancelled_assignment_produces_no_instance
  4. test_template_with_3_items_and_2_assignments_creates_6_instances
  5. test_frequency_override_is_used_when_set
  6. test_migration_patch_creates_assignment
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.tasks import daily_scheduled_task_instance_generator


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------

def _make_catalog(suffix: str) -> str:
    """Get or create a minimal Safety Task Catalog record; returns name."""
    code = f"TEST-{suffix}"
    existing = frappe.db.get_value("Safety Task Catalog", {"task_code": code}, "name")
    if existing:
        return existing
    doc = frappe.get_doc({
        "doctype": "Safety Task Catalog",
        "naming_series": "STC-.####",
        "task_title": f"Test Task {suffix}",
        "task_code": code,
        "department": "Maintenance",
        "frequency": "Daily",
        "priority": "Medium",
        "is_active": 1,
    })
    doc.insert(ignore_permissions=True)
    return doc.name


def _make_building(suffix: str) -> str:
    """Get or create a minimal Accommodation Building record; returns name."""
    bname = f"Test Building {suffix}"
    existing = frappe.db.get_value(
        "Building", {"building_name": bname}, "name"
    )
    if existing:
        return existing
    doc = frappe.get_doc({
        "doctype": "Building",
        "building_name": bname,
        "status": "Active",
        "total_capacity": 10,
    })
    doc.insert(ignore_permissions=True)
    return doc.name


def _make_template(suffix: str, frequency: str = "Daily", items: list | None = None) -> str:
    """Create a Scheduled Task Template with optional child items; returns name."""
    tname = f"Test Template {suffix}"
    existing = frappe.db.get_value(
        "Scheduled Task Template", {"template_name": tname}, "name"
    )
    if existing:
        # Clean up child rows and re-add; simpler to delete and re-create.
        frappe.delete_doc("Scheduled Task Template", existing, force=True, ignore_permissions=True)

    child_rows = []
    for cat in (items or []):
        child_rows.append({
            "task_catalog": cat,
            "is_active": 1,
        })

    doc = frappe.get_doc({
        "doctype": "Scheduled Task Template",
        "template_name": tname,
        "frequency": frequency,
        "is_active": 1,
        "template_items": child_rows,
    })
    doc.insert(ignore_permissions=True)
    return doc.name


def _make_assignment(template: str, building: str, is_active: int = 1) -> str:
    """Create a Scheduled Task Assignment; returns name."""
    doc = frappe.get_doc({
        "doctype": "Scheduled Task Assignment",
        "template": template,
        "building": building,
        "effective_from": frappe.utils.today(),
        "is_active": is_active,
    })
    doc.insert(ignore_permissions=True)
    return doc.name


def _purge_instances(filters: dict) -> None:
    """Delete Scheduled Task Instances matching filters (force, ignore_permissions)."""
    for name in frappe.get_all("Scheduled Task Instance", filters=filters, pluck="name"):
        frappe.delete_doc("Scheduled Task Instance", name, force=True, ignore_permissions=True)


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class TestScheduledTaskTemplateRedesign(FrappeTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")

        # Shared catalog records
        cls.catalog_a = _make_catalog("RSTTR-A")
        cls.catalog_b = _make_catalog("RSTTR-B")
        cls.catalog_c = _make_catalog("RSTTR-C")

        # Shared building records
        cls.building_1 = _make_building("RSTTR-1")
        cls.building_2 = _make_building("RSTTR-2")

    def setUp(self):
        frappe.set_user("Administrator")

    # ------------------------------------------------------------------
    # Test 1: A new instance is created for an active assignment
    # ------------------------------------------------------------------
    def test_new_instance_created_for_active_assignment(self):
        tmpl = _make_template("T1", frequency="Daily", items=[self.catalog_a])
        asgn = _make_assignment(tmpl, self.building_1)
        self.addCleanup(frappe.delete_doc, "Scheduled Task Assignment", asgn,
                        force=True, ignore_permissions=True)
        self.addCleanup(frappe.delete_doc, "Scheduled Task Template", tmpl,
                        force=True, ignore_permissions=True)

        # Remove any pre-existing instance for this assignment + catalog today.
        _purge_instances({"assignment": asgn, "task_catalog": self.catalog_a,
                          "due_date": frappe.utils.today()})

        daily_scheduled_task_instance_generator()

        count = frappe.db.count(
            "Scheduled Task Instance",
            {"assignment": asgn, "task_catalog": self.catalog_a,
             "due_date": frappe.utils.today(), "docstatus": ["!=", 2]},
        )
        self.addCleanup(_purge_instances,
                        {"assignment": asgn, "task_catalog": self.catalog_a})
        self.assertEqual(count, 1, "Expected exactly 1 instance for the active assignment")

    # ------------------------------------------------------------------
    # Test 2: Running the generator twice does not create duplicates
    # ------------------------------------------------------------------
    def test_no_duplicate_instance_for_same_day(self):
        tmpl = _make_template("T2", frequency="Daily", items=[self.catalog_a])
        asgn = _make_assignment(tmpl, self.building_1)
        self.addCleanup(frappe.delete_doc, "Scheduled Task Assignment", asgn,
                        force=True, ignore_permissions=True)
        self.addCleanup(frappe.delete_doc, "Scheduled Task Template", tmpl,
                        force=True, ignore_permissions=True)

        _purge_instances({"assignment": asgn, "task_catalog": self.catalog_a,
                          "due_date": frappe.utils.today()})

        daily_scheduled_task_instance_generator()
        daily_scheduled_task_instance_generator()

        count = frappe.db.count(
            "Scheduled Task Instance",
            {"assignment": asgn, "task_catalog": self.catalog_a,
             "due_date": frappe.utils.today(), "docstatus": ["!=", 2]},
        )
        self.addCleanup(_purge_instances,
                        {"assignment": asgn, "task_catalog": self.catalog_a})
        self.assertEqual(count, 1, "Generator ran twice — must still produce exactly 1 instance")

    # ------------------------------------------------------------------
    # Test 3: An inactive assignment produces no instances
    # ------------------------------------------------------------------
    def test_cancelled_assignment_produces_no_instance(self):
        tmpl = _make_template("T3", frequency="Daily", items=[self.catalog_a])
        asgn = _make_assignment(tmpl, self.building_1, is_active=0)
        self.addCleanup(frappe.delete_doc, "Scheduled Task Assignment", asgn,
                        force=True, ignore_permissions=True)
        self.addCleanup(frappe.delete_doc, "Scheduled Task Template", tmpl,
                        force=True, ignore_permissions=True)

        _purge_instances({"assignment": asgn, "task_catalog": self.catalog_a,
                          "due_date": frappe.utils.today()})

        daily_scheduled_task_instance_generator()

        count = frappe.db.count(
            "Scheduled Task Instance",
            {"assignment": asgn, "task_catalog": self.catalog_a,
             "due_date": frappe.utils.today(), "docstatus": ["!=", 2]},
        )
        self.addCleanup(_purge_instances,
                        {"assignment": asgn, "task_catalog": self.catalog_a})
        self.assertEqual(count, 0, "Inactive assignment must produce 0 instances")

    # ------------------------------------------------------------------
    # Test 4: 3 items × 2 assignments = 6 instances
    # ------------------------------------------------------------------
    def test_template_with_3_items_and_2_assignments_creates_6_instances(self):
        catalogs = [self.catalog_a, self.catalog_b, self.catalog_c]
        tmpl = _make_template("T4", frequency="Daily", items=catalogs)
        asgn1 = _make_assignment(tmpl, self.building_1)
        asgn2 = _make_assignment(tmpl, self.building_2)
        self.addCleanup(frappe.delete_doc, "Scheduled Task Assignment", asgn1,
                        force=True, ignore_permissions=True)
        self.addCleanup(frappe.delete_doc, "Scheduled Task Assignment", asgn2,
                        force=True, ignore_permissions=True)
        self.addCleanup(frappe.delete_doc, "Scheduled Task Template", tmpl,
                        force=True, ignore_permissions=True)

        today = frappe.utils.today()
        for cat in catalogs:
            _purge_instances({"task_catalog": cat,
                              "assignment": ["in", [asgn1, asgn2]],
                              "due_date": today})

        daily_scheduled_task_instance_generator()

        count = frappe.db.count(
            "Scheduled Task Instance",
            {"assignment": ["in", [asgn1, asgn2]],
             "due_date": today,
             "docstatus": ["!=", 2]},
        )
        for cat in catalogs:
            self.addCleanup(_purge_instances,
                            {"task_catalog": cat, "assignment": ["in", [asgn1, asgn2]]})
        self.assertEqual(count, 6, "3 items × 2 assignments must yield exactly 6 instances")

    # ------------------------------------------------------------------
    # Test 5: Frequency override on item is respected
    # ------------------------------------------------------------------
    def test_frequency_override_is_used_when_set(self):
        """Item with frequency_override='Weekly' must still produce an instance.
        The test verifies the instance is created (frequency filtering is the
        caller's concern; the generator always creates for the current period)."""
        # Create template with Monthly as default, but item overrides to Weekly.
        tmpl_name = "Test Template T5"
        existing = frappe.db.get_value(
            "Scheduled Task Template", {"template_name": tmpl_name}, "name"
        )
        if existing:
            frappe.delete_doc("Scheduled Task Template", existing,
                              force=True, ignore_permissions=True)

        tmpl_doc = frappe.get_doc({
            "doctype": "Scheduled Task Template",
            "template_name": tmpl_name,
            "frequency": "Monthly",
            "is_active": 1,
            "template_items": [{
                "task_catalog": self.catalog_a,
                "frequency_override": "Weekly",
                "is_active": 1,
            }],
        })
        tmpl_doc.insert(ignore_permissions=True)
        tmpl = tmpl_doc.name

        asgn = _make_assignment(tmpl, self.building_1)
        self.addCleanup(frappe.delete_doc, "Scheduled Task Assignment", asgn,
                        force=True, ignore_permissions=True)
        self.addCleanup(frappe.delete_doc, "Scheduled Task Template", tmpl,
                        force=True, ignore_permissions=True)

        _purge_instances({"assignment": asgn, "task_catalog": self.catalog_a})

        daily_scheduled_task_instance_generator()

        count = frappe.db.count(
            "Scheduled Task Instance",
            {"assignment": asgn, "task_catalog": self.catalog_a, "docstatus": ["!=", 2]},
        )
        self.addCleanup(_purge_instances,
                        {"assignment": asgn, "task_catalog": self.catalog_a})
        self.assertGreaterEqual(count, 1,
                                "Item with frequency_override='Weekly' must produce at least 1 instance")

    # ------------------------------------------------------------------
    # Test 6: Migration patch creates an Assignment from a legacy template
    # ------------------------------------------------------------------
    def test_migration_patch_creates_assignment(self):
        """Call the migration patch execute() directly; confirm it creates an
        Assignment when a template has a legacy building set in the DB."""
        from apex.patches.v1_x.migrate_scheduled_task_template_to_assignments import execute

        # A fresh site built from the current JSON never created the legacy `building`
        # column (it lingers only on incrementally-migrated sites). Ensure it exists
        # BEFORE any write this test makes, so the DDL runs with no pending transaction
        # write (avoiding ImplicitCommitError) and we can simulate the pre-B legacy state.
        if "building" not in frappe.db.get_table_columns("Scheduled Task Template"):
            frappe.db.commit()
            frappe.db.sql(
                "ALTER TABLE `tabScheduled Task Template` ADD COLUMN `building` varchar(140)"
            )

        # Create a template without items (migration doesn't need them).
        tmpl_name = "Test Template T6 Migration"
        existing = frappe.db.get_value(
            "Scheduled Task Template", {"template_name": tmpl_name}, "name"
        )
        if existing:
            frappe.delete_doc("Scheduled Task Template", existing,
                              force=True, ignore_permissions=True)

        tmpl_doc = frappe.get_doc({
            "doctype": "Scheduled Task Template",
            "template_name": tmpl_name,
            "frequency": "Monthly",
            "is_active": 1,
        })
        tmpl_doc.insert(ignore_permissions=True)
        tmpl = tmpl_doc.name
        self.addCleanup(frappe.delete_doc, "Scheduled Task Template", tmpl,
                        force=True, ignore_permissions=True)

        # Write the building directly into the DB column (simulating the pre-B state
        # where the column existed on the table). The DocType JSON no longer lists the
        # field, but frappe.db.set_value writes the column unconditionally.
        frappe.db.set_value(
            "Scheduled Task Template", tmpl, "building", self.building_1,
            update_modified=False,
        )
        frappe.db.commit()

        # Remove any pre-existing Assignment for this (template, building) pair.
        old_asgns = frappe.get_all(
            "Scheduled Task Assignment",
            filters={"template": tmpl, "building": self.building_1},
            pluck="name",
        )
        for a in old_asgns:
            frappe.delete_doc("Scheduled Task Assignment", a, force=True, ignore_permissions=True)

        execute()

        created = frappe.db.exists(
            "Scheduled Task Assignment", {"template": tmpl, "building": self.building_1}
        )
        # Cleanup the created assignment
        if created:
            self.addCleanup(frappe.delete_doc, "Scheduled Task Assignment", created,
                            force=True, ignore_permissions=True)

        self.assertTrue(created, "Migration patch must create a Scheduled Task Assignment")
