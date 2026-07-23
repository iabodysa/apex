# Copyright (c) 2026, AFMCO and contributors
"""Generate Safety Setup on the assignment-based model (T-552 / A-076).

``generate_safety_setup`` was rebuilt to stop writing the dropped
``Scheduled Task Template.building`` field. It now get-or-creates ONE reusable
Scheduled Task Template per Safety Task Catalog entry (carrying the catalog as an
active ``template_items`` row) and a Scheduled Task Assignment per (template,
building) — the pair the daily generator expands into Scheduled Task Instances.

These tests pin: template + assignment creation, frequency mapping
(catalog "Annual" -> template "Annually"), event-driven exclusion (As Needed /
On Entry are reported, never scheduled), idempotent re-run, legacy-template item
backfill, and the absence of any ``Scheduled Task Template.building`` usage.
"""

from __future__ import annotations

import os
import re

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.doctype.building.building import generate_safety_setup

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


def _rand(n: int = 12) -> str:
    return frappe.generate_hash(length=n)


def _make_catalog(code: str, frequency: str, all_buildings: int = 1) -> str:
    """Get-or-create an active Safety Task Catalog with a given frequency; return name."""
    existing = frappe.db.get_value("Safety Task Catalog", {"task_code": code}, "name")
    if existing:
        frappe.db.set_value("Safety Task Catalog", existing, {
            "frequency": frequency,
            "is_active": 1,
            "applicable_to_all_buildings": all_buildings,
        })
        return existing
    return frappe.get_doc({
        "doctype": "Safety Task Catalog",
        "naming_series": "STC-.####",
        "task_title": f"A076 {code}",
        "task_code": code,
        "department": "Fire Safety",
        "frequency": frequency,
        "priority": "High",
        "is_active": 1,
        "applicable_to_all_buildings": all_buildings,
    }).insert(ignore_permissions=True).name


def _make_building(name: str) -> str:
    existing = frappe.db.get_value("Building", {"building_name": name}, "name")
    if existing:
        return existing
    return frappe.get_doc({
        "doctype": "Building",
        "building_name": name,
        "status": "Active",
        "total_capacity": 10,
    }).insert(ignore_permissions=True).name


def _template_for(catalog: str) -> str | None:
    return frappe.db.get_value(
        "Scheduled Task Template", {"safety_task_catalog": catalog}, "name"
    )


class TestGenerateSafetySetup(FrappeTestCase):

    def setUp(self):
        frappe.set_user("Administrator")

    def _cleanup(self, building: str, *catalogs: str):
        frappe.set_user("Administrator")
        # Assignments first (they link building -> template), then per-catalog
        # template, then catalog, then the building. force bypasses link checks.
        for sta in frappe.get_all(
            "Scheduled Task Assignment", {"building": building}, pluck="name"
        ):
            frappe.delete_doc("Scheduled Task Assignment", sta, force=True, ignore_permissions=True)
        for cat in catalogs:
            tmpl = _template_for(cat)
            if tmpl:
                frappe.delete_doc("Scheduled Task Template", tmpl, force=True, ignore_permissions=True)
            if frappe.db.exists("Safety Task Catalog", cat):
                frappe.delete_doc("Safety Task Catalog", cat, force=True, ignore_permissions=True)
        if frappe.db.exists("Building", building):
            frappe.delete_doc("Building", building, force=True, ignore_permissions=True)

    # [#a076-create]
    def test_creates_reusable_template_and_assignment(self):
        cat = _make_catalog(f"A076-CRT-{_rand()}", "Monthly")
        bld = _make_building(f"A076 CRT {_rand()}")
        self.addCleanup(self._cleanup, bld, cat)

        summary = generate_safety_setup(bld)

        tmpl = _template_for(cat)
        self.assertTrue(tmpl, "a reusable template must be created for the catalog task")

        row = frappe.db.get_value(
            "Scheduled Task Template", tmpl, ["task_type", "frequency"], as_dict=True
        )
        self.assertEqual(row.task_type, "Safety")
        self.assertEqual(row.frequency, "Monthly")

        # the catalog must be an active scheduling item (the generator iterates these)
        self.assertTrue(
            frappe.db.exists(
                "Scheduled Task Template Item",
                {"parent": tmpl, "task_catalog": cat, "is_active": 1},
            ),
            "catalog must be an active template_items row so the generator emits instances",
        )
        # the assignment binds the template to this building
        self.assertTrue(
            frappe.db.exists("Scheduled Task Assignment", {"template": tmpl, "building": bld}),
            "an assignment must bind the reusable template to this building",
        )
        self.assertGreaterEqual(summary["created_assignments"], 1)
        self.assertEqual(
            frappe.db.get_value("Building", bld, "safety_setup_status"), "Completed"
        )

    # [#a076-idem]
    def test_idempotent_rerun_creates_no_duplicate_assignment_or_template(self):
        cat = _make_catalog(f"A076-IDEM-{_rand()}", "Quarterly")
        bld = _make_building(f"A076 IDEM {_rand()}")
        self.addCleanup(self._cleanup, bld, cat)

        generate_safety_setup(bld)
        second = generate_safety_setup(bld)

        tmpl = _template_for(cat)
        self.assertEqual(
            frappe.db.count("Scheduled Task Assignment", {"template": tmpl, "building": bld}),
            1,
            "re-run must not duplicate the (template, building) assignment",
        )
        self.assertEqual(
            frappe.db.count("Scheduled Task Template", {"safety_task_catalog": cat}),
            1,
            "re-run must reuse the single template, not create a second",
        )
        self.assertGreaterEqual(
            second["skipped_assignments"], 1,
            "the already-present assignment must be counted as skipped on re-run",
        )

    # [#a076-annual]
    def test_annual_catalog_frequency_maps_to_annually(self):
        cat = _make_catalog(f"A076-ANN-{_rand()}", "Annual")
        bld = _make_building(f"A076 ANN {_rand()}")
        self.addCleanup(self._cleanup, bld, cat)

        generate_safety_setup(bld)

        tmpl = _template_for(cat)
        self.assertTrue(tmpl)
        self.assertEqual(
            frappe.db.get_value("Scheduled Task Template", tmpl, "frequency"),
            "Annually",
            "catalog 'Annual' must map to the template Select value 'Annually'",
        )

    # [#a076-event]
    def test_event_driven_frequency_is_excluded_not_scheduled(self):
        for freq in ("As Needed", "On Entry"):
            code = f"A076-EVT-{_rand()}"
            cat = _make_catalog(code, freq)
            bld = _make_building(f"A076 EVT {_rand()}")
            self.addCleanup(self._cleanup, bld, cat)

            summary = generate_safety_setup(bld)

            self.assertFalse(
                _template_for(cat),
                f"an event-driven ({freq}) task must NOT get a scheduled template",
            )
            self.assertIn(
                code, summary["event_driven_excluded"],
                f"an event-driven ({freq}) task must be reported as excluded, not swallowed",
            )

    # [#a076-legacy]
    def test_reused_template_backfills_missing_scheduling_item(self):
        """A pre-existing template linked to the catalog but WITHOUT items (as a
        pre-redesign / migrated template is) must be reused (not duplicated) and the
        generator must backfill the catalog as an active template_items row, otherwise
        the daily generator would silently emit nothing for it."""
        cat = _make_catalog(f"A076-LEG-{_rand()}", "Weekly")
        bld = _make_building(f"A076 LEG {_rand()}")
        self.addCleanup(self._cleanup, bld, cat)

        legacy = frappe.get_doc({
            "doctype": "Scheduled Task Template",
            "template_name": f"Legacy STT {_rand()}",
            "task_type": "Safety",
            "frequency": "Weekly",
            "safety_task_catalog": cat,
            "is_active": 1,
            # deliberately NO template_items -> inert for the scheduler
        }).insert(ignore_permissions=True)

        summary = generate_safety_setup(bld)

        self.assertEqual(
            frappe.db.count("Scheduled Task Template", {"safety_task_catalog": cat}),
            1,
            "must reuse the existing catalog template, not create a duplicate",
        )
        self.assertEqual(_template_for(cat), legacy.name)
        self.assertTrue(
            frappe.db.exists(
                "Scheduled Task Template Item",
                {"parent": legacy.name, "task_catalog": cat, "is_active": 1},
            ),
            "the reused template must be backfilled with the catalog scheduling item",
        )
        self.assertTrue(
            frappe.db.exists(
                "Scheduled Task Assignment", {"template": legacy.name, "building": bld}
            ),
        )
        self.assertGreaterEqual(summary["reused_templates"], 1)

    # [#a076-noguard]
    def test_no_scheduled_task_template_building_field_or_usage(self):
        """The T-552 redesign dropped ``Scheduled Task Template.building``. Prove the
        field is gone from the DocType AND that no product code constructs or queries a
        Scheduled Task Template with a ``building`` key (the A-076 breakage)."""
        # structural: the field is truly absent from the doctype
        self.assertIsNone(
            frappe.get_meta("Scheduled Task Template").get_field("building"),
            "Scheduled Task Template must have no 'building' field (dropped by T-552)",
        )

        # source guard: grep the app tree for a Scheduled Task Template built or filtered
        # by a `building` key. The migration patch (reads the legacy column by design via
        # raw SQL) and its regression test legitimately reference it — exclude those and
        # this test file itself.
        import apex

        apex_root = os.path.dirname(apex.__file__)
        this_file = os.path.abspath(__file__)
        allow = {
            os.path.join("patches", "v1_x", "migrate_scheduled_task_template_to_assignments.py"),
            os.path.join("tests", "test_scheduled_task_template_redesign.py"),
        }
        construct_re = re.compile(r'"doctype":\s*"Scheduled Task Template"')
        building_key_re = re.compile(r"""["']building["']\s*:""")
        filter_re = re.compile(
            r'"Scheduled Task Template"\s*,\s*\{[^}]*["\']building["\']'
        )

        offenders = []
        for dirpath, _dirs, files in os.walk(apex_root):
            for fn in files:
                if not fn.endswith(".py"):
                    continue
                full = os.path.join(dirpath, fn)
                if os.path.abspath(full) == this_file:
                    continue
                if os.path.relpath(full, apex_root) in allow:
                    continue
                with open(full, encoding="utf-8") as fh:
                    text = fh.read()
                for m in construct_re.finditer(text):
                    # scan the dict body that follows the doctype key
                    if building_key_re.search(text[m.start():m.start() + 400]):
                        offenders.append(os.path.relpath(full, apex_root))
                        break
                if filter_re.search(text):
                    offenders.append(os.path.relpath(full, apex_root))

        self.assertEqual(
            offenders, [],
            f"Scheduled Task Template.building usage must be gone; found in: {offenders}",
        )


def tearDownModule():
    # This module creates Accommodation Buildings; drop any left past the pre-suite
    # baseline so the post-suite count returns to baseline (P-148).
    from apex.tests import factories

    factories.purge_test_buildings()
