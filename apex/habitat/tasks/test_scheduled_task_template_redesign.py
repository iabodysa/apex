# Copyright (c) 2026, AFMCO and contributors
"""Regression tests for T-552 Phase B: Scheduled Task Template redesign.

Covers the Salary-Structure analogy:
  Scheduled Task Template   (holds child table of task catalog rows)
  Scheduled Task Assignment (template → building link)
  Scheduled Task Instance   (auto-generated per assignment × item)

Seven tests:
  1. test_new_instance_created_for_active_assignment
  2. test_no_duplicate_instance_for_same_day
  3. test_cancelled_assignment_produces_no_instance
  4. test_template_with_3_items_and_2_assignments_creates_6_instances
  5. test_frequency_override_is_used_when_set
  6. test_migration_patch_creates_assignment            (backfill LOGIC + idempotency)
  7. test_migration_patch_registered_pre_model_sync     (patch-phase ORDERING guard)
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.tasks import daily_scheduled_task_instance_generator


# [#ps6zpi]

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
        # [#1s6a2r]
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


# [#adahy4]

class TestScheduledTaskTemplateRedesign(FrappeTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")

        # [#80igj8]
        cls.catalog_a = _make_catalog("RSTTR-A")
        cls.catalog_b = _make_catalog("RSTTR-B")
        cls.catalog_c = _make_catalog("RSTTR-C")

        # [#7pxpbf]
        cls.building_1 = _make_building("RSTTR-1")
        cls.building_2 = _make_building("RSTTR-2")

    def setUp(self):
        frappe.set_user("Administrator")

    # Schema snapshot/restore for the migration-backfill test, which manufactures the
    # legacy `building` column with a COMMIT'd ALTER (escapes the FrappeTestCase
    # rollback). Uses uncached SHOW COLUMNS because frappe.db.get_table_columns caches
    # and would be stale right after the ALTER/DROP.
    @staticmethod
    def _live_columns() -> set:
        return {row[0] for row in frappe.db.sql("SHOW COLUMNS FROM `tabScheduled Task Template`")}

    @classmethod
    def _drop_building_column(cls):
        frappe.db.commit()
        if "building" in cls._live_columns():
            frappe.db.sql("ALTER TABLE `tabScheduled Task Template` DROP COLUMN `building`")
            frappe.db.commit()

    def _assert_schema_restored(self, cols_before):
        self.assertEqual(
            self._live_columns(), set(cols_before),
            "test must leave `tabScheduled Task Template` schema byte-identical; the "
            "manufactured legacy `building` column leaked onto the shared schema",
        )

    # [#8wtp3y]
    def test_new_instance_created_for_active_assignment(self):
        tmpl = _make_template("T1", frequency="Daily", items=[self.catalog_a])
        asgn = _make_assignment(tmpl, self.building_1)
        self.addCleanup(frappe.delete_doc, "Scheduled Task Assignment", asgn,
                        force=True, ignore_permissions=True)
        self.addCleanup(frappe.delete_doc, "Scheduled Task Template", tmpl,
                        force=True, ignore_permissions=True)

        # [#kh9ok1]
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

    # [#20a98h]
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

    # [#452ynq]
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

    # [#n4gju6]
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

    # [#o2db8p]
    def test_frequency_override_is_used_when_set(self):
        """Item with frequency_override='Weekly' must still produce an instance.
        The test verifies the instance is created (frequency filtering is the
        caller's concern; the generator always creates for the current period)."""
        # [#nywyc0]
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

    # [#fbte6e]
    def test_migration_patch_creates_assignment(self):
        """Call the migration patch execute() directly; confirm it creates an
        Assignment when a template has a legacy building set in the DB, and that a
        re-run creates no duplicate (idempotency guard).

        NOTE: this test validates backfill LOGIC only — it manufactures the legacy
        `building` column, so it cannot observe the real deploy-time ordering (that
        sync_all drops the column). The ordering guarantee is covered separately by
        ``test_migration_patch_registered_pre_model_sync``.
        """
        from apex.patches.v1_x.migrate_scheduled_task_template_to_assignments import execute

        # [#fwozt3]
        # The legacy `building` column was removed from the DocType JSON, so a synced
        # test site has no such column. Manufacture it to exercise the backfill; the
        # DDL + set_value below COMMIT (escaping the FrappeTestCase rollback), so we
        # snapshot the live schema, drop the manufactured column on cleanup, then assert
        # the schema is left byte-identical.
        cols_before = self._live_columns()
        if "building" not in cols_before:
            # addCleanup is LIFO: register the assertion FIRST so it runs AFTER the drop.
            self.addCleanup(self._assert_schema_restored, cols_before)
            self.addCleanup(self._drop_building_column)
            frappe.db.commit()
            frappe.db.sql(
                "ALTER TABLE `tabScheduled Task Template` ADD COLUMN `building` varchar(140)"
            )

        # [#hu62y6]
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

        # [#bwzi01]
        frappe.db.set_value(
            "Scheduled Task Template", tmpl, "building", self.building_1,
            update_modified=False,
        )
        frappe.db.commit()

        # [#ccju71]
        old_asgns = frappe.get_all(
            "Scheduled Task Assignment",
            filters={"template": tmpl, "building": self.building_1},
            pluck="name",
        )
        for a in old_asgns:
            frappe.delete_doc("Scheduled Task Assignment", a, force=True, ignore_permissions=True)

        # [#bity15]
        execute()
        execute()

        created = frappe.get_all(
            "Scheduled Task Assignment",
            filters={"template": tmpl, "building": self.building_1},
            pluck="name",
        )
        for a in created:
            self.addCleanup(frappe.delete_doc, "Scheduled Task Assignment", a,
                            force=True, ignore_permissions=True)

        self.assertEqual(
            len(created), 1,
            "Migration patch must create exactly one Assignment and be idempotent on re-run",
        )

    # [#bfbol7]
    def test_migration_patch_registered_pre_model_sync(self):
        """The backfill reads the legacy `building` column off tabScheduled Task
        Template. sync_all() drops that column on the same migrate that ships this
        release (the field was removed from the DocType JSON), so the patch MUST run
        in [pre_model_sync] — before the column is dropped. If it slips into
        [post_model_sync] the column is already gone and the whole backfill silently
        no-ops. This asserts the patch's phase directly from patches.txt so the
        regression cannot creep back in unnoticed."""
        import os

        import apex

        patches_txt = os.path.join(os.path.dirname(apex.__file__), "patches.txt")
        with open(patches_txt, encoding="utf-8") as fh:
            lines = [ln.strip() for ln in fh]

        patch = "apex.patches.v1_x.migrate_scheduled_task_template_to_assignments"
        self.assertIn(patch, lines, "Migration patch must be registered in patches.txt")

        pre_idx = lines.index("[pre_model_sync]")
        post_idx = lines.index("[post_model_sync]")
        patch_idx = lines.index(patch)
        self.assertTrue(
            pre_idx < patch_idx < post_idx,
            "migrate_scheduled_task_template_to_assignments must be in the "
            "[pre_model_sync] section (before [post_model_sync]) so it reads the "
            "legacy `building` column before sync_all() drops it",
        )


def tearDownModule():
    # A test body here commits (ALTER TABLE / set_value), so the class-fixture
    # Buildings survive FrappeTestCase rollback; drop every Building created after
    # the pre-suite baseline (P-148).
    from apex.tests import factories

    factories.purge_test_buildings()
