# Copyright (c) 2026, AFMCO and contributors
"""Direct coverage for ``apex.habitat.utils.safety_setup``.

The Building controller's whitelisted ``generate_safety_setup`` is exercised
end-to-end elsewhere (``building/test_building_safety_setup.py``); this module
drives ``apply_catalog`` directly so the module's own idempotency contract stays
provable without the Building controller in the loop.

Pins: seeding a catalog task twice creates exactly one Scheduled Task Template row
per task code, and the re-run (keyed on ``safety_task_catalog``) adds nothing —
no new template, no new assignment, no new building-scope row.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.utils import safety_setup


def _tag() -> str:
    """A collision-free identifier suffix, matching the suite-wide entropy floor."""
    return frappe.generate_hash(length=12)


def _make_catalog(task_code: str, frequency: str, applicable_to_all_buildings: int = 0):
    """An active Safety Task Catalog entry for the given task code and frequency."""
    return frappe.get_doc(
        {
            "doctype": "Safety Task Catalog",
            "naming_series": "STC-.####",
            "task_title": f"Safety Setup Utils {task_code}",
            "task_code": task_code,
            "department": "Fire Safety",
            "frequency": frequency,
            "priority": "High",
            "is_active": 1,
            "applicable_to_all_buildings": applicable_to_all_buildings,
        }
    ).insert(ignore_permissions=True)


def _make_building(name: str):
    """An Active Building with no floor plan — safety setup does not need rooms."""
    return frappe.get_doc(
        {"doctype": "Building", "building_name": name, "status": "Active", "total_capacity": 10}
    ).insert(ignore_permissions=True)


class TestSafetySetupFrequencyRules(FrappeTestCase):
    """Pure classification rules — no database involved."""

    def test_is_event_driven_true_for_as_needed_and_on_entry(self):
        """As Needed / On Entry run on a trigger, not a calendar."""
        self.assertTrue(safety_setup.is_event_driven("As Needed"))
        self.assertTrue(safety_setup.is_event_driven("On Entry"))

    def test_is_event_driven_false_for_a_calendar_frequency(self):
        """A calendar period is schedulable, so it is not event-driven."""
        self.assertFalse(safety_setup.is_event_driven("Monthly"))
        self.assertFalse(safety_setup.is_event_driven(None))

    def test_template_frequency_maps_catalog_periods_to_template_values(self):
        """Catalog 'Annual' maps to the Scheduled Task Template Select 'Annually'."""
        self.assertEqual(safety_setup.template_frequency("Annual"), "Annually")
        self.assertEqual(safety_setup.template_frequency("Monthly"), "Monthly")

    def test_template_frequency_is_none_for_an_unmapped_period(self):
        """An event-driven period has no scheduling equivalent."""
        self.assertIsNone(safety_setup.template_frequency("As Needed"))


class TestApplyCatalogIdempotency(FrappeTestCase):
    """``apply_catalog`` wires one catalog task to one building: scope, template,
    assignment — each keyed so a re-run creates nothing twice."""

    def _cleanup(self, building_name: str, catalog_name: str):
        """Removes the assignment, template, catalog, and building this test made."""
        frappe.set_user("Administrator")
        for assignment_name in frappe.get_all(
            "Scheduled Task Assignment", {"building": building_name}, pluck="name"
        ):
            frappe.delete_doc(
                "Scheduled Task Assignment", assignment_name, force=True, ignore_permissions=True
            )
        template_name = frappe.db.get_value(
            "Scheduled Task Template", {"safety_task_catalog": catalog_name}, "name"
        )
        if template_name:
            frappe.delete_doc(
                "Scheduled Task Template", template_name, force=True, ignore_permissions=True
            )
        frappe.delete_doc("Safety Task Catalog", catalog_name, force=True, ignore_permissions=True)
        frappe.delete_doc("Building", building_name, force=True, ignore_permissions=True)

    def test_seeding_a_catalog_task_twice_creates_one_row_per_task_code(self):
        """Seeding a safety catalogue twice creates one row per task code, and the
        re-run keyed on ``safety_task_catalog`` adds nothing."""
        task_code = f"UTIL-SAFETY-{_tag()}"
        catalog = _make_catalog(task_code, "Monthly", applicable_to_all_buildings=0)
        building = _make_building(f"Safety Setup Utils {_tag()}")
        self.addCleanup(self._cleanup, building.name, catalog.name)

        first_tally = safety_setup.SafetySetupTally()
        safety_setup.apply_catalog(catalog, building.name, first_tally)

        self.assertEqual(first_tally.created_templates, 1)
        self.assertEqual(first_tally.created_assignments, 1)
        self.assertEqual(first_tally.created_scopes, 1)
        self.assertEqual(
            frappe.db.count("Scheduled Task Template", {"safety_task_catalog": catalog.name}), 1,
        )
        template_name = frappe.db.get_value(
            "Scheduled Task Template", {"safety_task_catalog": catalog.name}, "name"
        )
        self.assertEqual(
            frappe.db.count(
                "Scheduled Task Assignment", {"template": template_name, "building": building.name}
            ),
            1,
        )
        self.assertEqual(
            frappe.db.count(
                "Safety Task Building Scope", {"parent": catalog.name, "building": building.name}
            ),
            1,
        )

        second_tally = safety_setup.SafetySetupTally()
        safety_setup.apply_catalog(catalog, building.name, second_tally)

        self.assertEqual(second_tally.created_templates, 0, "a re-run must add no new template")
        self.assertEqual(second_tally.created_assignments, 0, "a re-run must add no new assignment")
        self.assertEqual(second_tally.created_scopes, 0, "a re-run must add no new scope row")
        self.assertEqual(second_tally.reused_templates, 1)
        self.assertEqual(second_tally.skipped_assignments, 1)
        self.assertEqual(second_tally.skipped_scopes, 1)
        self.assertEqual(
            frappe.db.count("Scheduled Task Template", {"safety_task_catalog": catalog.name}), 1,
            "one template row per task code, even after a second seed",
        )
        self.assertEqual(
            frappe.db.count("Scheduled Task Assignment", {"building": building.name}), 1,
        )
        self.assertEqual(
            frappe.db.count(
                "Safety Task Building Scope", {"parent": catalog.name, "building": building.name}
            ),
            1,
        )

    def test_apply_catalog_excludes_event_driven_tasks_from_scheduling(self):
        """An event-driven catalog task is reported, never turned into a template."""
        task_code = f"UTIL-SAFETY-EVT-{_tag()}"
        catalog = _make_catalog(task_code, "As Needed", applicable_to_all_buildings=1)
        building = _make_building(f"Safety Setup Utils Evt {_tag()}")
        self.addCleanup(self._cleanup, building.name, catalog.name)

        tally = safety_setup.SafetySetupTally()
        safety_setup.apply_catalog(catalog, building.name, tally)

        self.assertIn(task_code, tally.event_driven_excluded)
        self.assertFalse(
            frappe.db.exists("Scheduled Task Template", {"safety_task_catalog": catalog.name})
        )


class TestSafetySetupReporting(FrappeTestCase):
    """``setup_summary`` / ``setup_message`` / ``report_setup`` read a tally back."""

    def test_setup_summary_carries_every_counter_and_the_license_reminder(self):
        """The machine-readable summary exposes every counter plus the manual
        Building License reminder (those records are never auto-created)."""
        tally = safety_setup.SafetySetupTally()
        tally.created_templates = 1
        tally.created_assignments = 2
        tally.skipped_assignments = 1

        summary = safety_setup.setup_summary(tally)

        self.assertEqual(summary["created_templates"], 1)
        self.assertEqual(summary["created_assignments"], 2)
        self.assertEqual(summary["skipped_assignments"], 1)
        self.assertIn("license_reminder", summary)

    def test_setup_message_names_excluded_event_driven_tasks(self):
        """The operator-facing message names an excluded event-driven task code."""
        tally = safety_setup.SafetySetupTally()
        tally.event_driven_excluded = ["SAF-001"]
        message = safety_setup.setup_message(tally)
        self.assertIn("SAF-001", message)

    def test_report_setup_returns_the_same_summary_and_does_not_raise(self):
        """``report_setup`` msgprints the operator account and hands back the same
        dict ``setup_summary`` would build."""
        tally = safety_setup.SafetySetupTally()
        tally.created_assignments = 1
        result = safety_setup.report_setup(tally)
        self.assertEqual(result, safety_setup.setup_summary(tally))
