# Copyright (c) 2026, AFMCO and contributors
"""Idempotency of the daily Scheduled Task Instance generator (Phase B, T-552).

The generator's contract is ONE instance per (assignment, task_catalog, period),
enforced by a check-then-insert guard plus the composite UNIQUE backstop
``unique_sti_assignment_catalog_due_status`` (scheduled_task_instance.on_doctype_update).
The only existing coverage (qa_probe_systems test_8) smoke-runs every scheduler
once and asserts no exception — it never RE-runs the generator and never counts
the resulting instances. So a regression in the period_key computation or the
exists() guard would silently spam duplicate instances with nothing in CI catching it.
This test runs the generator twice for the same period and asserts the per-assignment/
per-catalog/per-period count stays at exactly one.

Phase B design: the generator iterates Scheduled Task Assignment × Scheduled Task
Template Item, so both must exist for the generator to produce an instance.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import get_first_day, getdate, today


class TestStiGeneratorIdempotency(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        method = self._testMethodName

        catalog_code = f"STI-IDEM-{method}"[:20]
        existing_cat = frappe.db.get_value(
            "Safety Task Catalog", {"task_code": catalog_code}, "name"
        )
        if existing_cat:
            self.catalog = existing_cat
        else:
            cat_doc = frappe.get_doc({
                "doctype": "Safety Task Catalog",
                "naming_series": "STC-.####",
                "task_title": f"Idempotency Test Task {method}",
                "task_code": catalog_code,
                "department": "Maintenance",
                "frequency": "Monthly",
                "priority": "Medium",
                "is_active": 1,
            })
            cat_doc.insert(ignore_permissions=True)
            self.catalog = cat_doc.name
            self.addCleanup(
                frappe.delete_doc, "Safety Task Catalog", self.catalog,
                force=True, ignore_permissions=True,
            )

        bname = f"STI Idempotency Building {method}"
        existing_bld = frappe.db.get_value(
            "Building", {"building_name": bname}, "name"
        )
        if existing_bld:
            self.building = existing_bld
        else:
            bld_doc = frappe.get_doc({
                "doctype": "Building",
                "building_name": bname,
                "status": "Active",
                "total_capacity": 10,
            })
            bld_doc.insert(ignore_permissions=True)
            self.building = bld_doc.name
            self.addCleanup(
                frappe.delete_doc, "Building", self.building,
                force=True, ignore_permissions=True,
            )

        self.template_name = f"STI Idempotency {method}"
        existing_tmpl = frappe.db.get_value(
            "Scheduled Task Template", {"template_name": self.template_name}, "name"
        )
        if existing_tmpl:
            frappe.delete_doc(
                "Scheduled Task Template", existing_tmpl, force=True, ignore_permissions=True
            )
        tmpl_doc = frappe.get_doc({
            "doctype": "Scheduled Task Template",
            "template_name": self.template_name,
            "task_type": "Safety",
            "frequency": "Monthly",
            "is_active": 1,
            "template_items": [{"task_catalog": self.catalog, "is_active": 1}],
        })
        tmpl_doc.insert(ignore_permissions=True)
        self.template = tmpl_doc.name
        self.addCleanup(
            frappe.delete_doc, "Scheduled Task Template", self.template,
            force=True, ignore_permissions=True,
        )

        asgn_doc = frappe.get_doc({
            "doctype": "Scheduled Task Assignment",
            "template": self.template,
            "building": self.building,
            "effective_from": today(),
            "is_active": 1,
        })
        asgn_doc.insert(ignore_permissions=True)
        self.assignment = asgn_doc.name
        self.addCleanup(
            frappe.delete_doc, "Scheduled Task Assignment", self.assignment,
            force=True, ignore_permissions=True,
        )

        self.period_key = str(get_first_day(getdate(today())))

    def tearDown(self):
        frappe.set_user("Administrator")
        for name in frappe.get_all(
            "Scheduled Task Instance",
            filters={"assignment": self.assignment, "due_date": self.period_key},
            pluck="name",
        ):
            frappe.delete_doc(
                "Scheduled Task Instance", name, force=True, ignore_permissions=True
            )

    def _instance_count(self):
        return frappe.db.count(
            "Scheduled Task Instance",
            {
                "assignment": self.assignment,
                "task_catalog": self.catalog,
                "due_date": self.period_key,
                "docstatus": ["!=", 2],
            },
        )

    def test_generator_creates_one_instance_and_is_idempotent(self):
        from apex.habitat.tasks import daily_scheduled_task_instance_generator

        active = frappe.get_all(
            "Scheduled Task Assignment",
            filters={"is_active": 1, "name": self.assignment},
            pluck="name",
        )
        self.assertIn(
            self.assignment,
            active,
            "seed failed: the active-assignment scan did not find the fixture",
        )
        self.assertEqual(
            self._instance_count(),
            0,
            "fixture must start with no instance for its current period",
        )

        daily_scheduled_task_instance_generator()
        self.assertEqual(
            self._instance_count(),
            1,
            "the first generator run must create exactly one instance",
        )

        daily_scheduled_task_instance_generator()
        self.assertEqual(
            self._instance_count(),
            1,
            "re-running the generator for the same period must not duplicate",
        )
