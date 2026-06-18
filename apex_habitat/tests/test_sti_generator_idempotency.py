# Copyright (c) 2026, AFMCO and contributors
"""Idempotency of the daily Scheduled Task Instance generator.

The generator's contract is ONE instance per template per period, enforced by a
check-then-insert guard plus the composite UNIQUE backstop
``unique_sti_template_due_status`` (scheduled_task_instance.on_doctype_update).
The only existing coverage (qa_probe_systems test_8) smoke-runs every scheduler
once and asserts no exception — it never RE-runs the generator and never counts
the resulting instances. So a regression in the period_key computation or the
exists() guard would silently spam a duplicate instance every day with nothing
in CI catching it. This test runs the generator twice for the same period and
asserts the per-template/per-period count stays at exactly one.

Verified against the DocType JSON:
  Scheduled Task Template — required: template_name (Data, unique, also the
    autoname `field:template_name`), frequency (Select; Monthly is a valid
    option and the default). `building` is optional, so the fixture omits it to
    stay self-contained (no Accommodation Building needed) and to skip the
    generator's building-exists branch.
  Scheduled Task Instance — `template` Link, `due_date` Date; the generator
    inserts at docstatus 0 (Draft, it does NOT submit). The guard counts
    {template, due_date, docstatus != 2}, so the assertion scopes the count the
    same way and to THIS template only (the migrated site may carry other active
    seed templates).
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import get_first_day, getdate, today


class TestStiGeneratorIdempotency(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        # Unique per-test fixture keyed off the method name (mirrors the Vehicle
        # Incident pattern); template_name is also the autoname, so it is the
        # link value the generator writes onto the instance.
        self.template_name = f"STI Idempotency {self._testMethodName}"
        self.template = (
            frappe.get_doc(
                {
                    "doctype": "Scheduled Task Template",
                    "template_name": self.template_name,
                    "task_type": "Safety",
                    "frequency": "Monthly",
                    "is_active": 1,
                }
            )
            .insert(ignore_permissions=True)
            .name
        )
        # Recompute the period_key exactly as the Monthly branch of the generator
        # does (first day of the current month) so the count is scoped to the
        # one period this run targets, independent of the calendar date.
        self.period_key = str(get_first_day(getdate(today())))

    def tearDown(self):
        frappe.set_user("Administrator")

    def _instance_count(self):
        # Scope to this template + this period, and exclude Cancelled (docstatus
        # == 2) exactly as the generator's own existence guard does.
        return frappe.db.count(
            "Scheduled Task Instance",
            {
                "template": self.template,
                "due_date": self.period_key,
                "docstatus": ["!=", 2],
            },
        )

    def test_generator_creates_one_instance_and_is_idempotent(self):
        from apex_habitat.habitat.tasks import daily_scheduled_task_instance_generator

        # Non-vacuous precondition: the seeded template must be discoverable by
        # the same scan the generator runs (active templates), and there must be
        # no pre-existing instance for it this period.
        active = frappe.get_all(
            "Scheduled Task Template",
            filters={"is_active": 1, "name": self.template},
            pluck="name",
        )
        self.assertIn(
            self.template,
            active,
            "seed failed: the active-template scan did not find the fixture",
        )
        self.assertEqual(
            self._instance_count(),
            0,
            "fixture must start with no instance for its current period",
        )

        # First run: the generator must create exactly one instance for the
        # template's current period. (Also proves the seed/scan path works, so
        # the idempotency assertion below is not vacuously satisfied by zero.)
        daily_scheduled_task_instance_generator()
        self.assertEqual(
            self._instance_count(),
            1,
            "the first generator run must create exactly one instance",
        )

        # Second run for the same period: the check-then-insert guard (backed by
        # the unique_sti_template_due_status index) must create NO duplicate.
        daily_scheduled_task_instance_generator()
        self.assertEqual(
            self._instance_count(),
            1,
            "re-running the generator for the same period must not duplicate",
        )
