# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import today


SAFETY_FREQ_MAP = {
    "Daily": "Daily",
    "Weekly": "Weekly",
    "Monthly": "Monthly",
    "Quarterly": "Quarterly",
    "Annual": "Annually",
}

EVENT_DRIVEN_FREQUENCIES = {"As Needed", "On Entry"}


class SafetySetupTally:

    def __init__(self):
        self.created_scopes = 0
        self.skipped_scopes = 0
        self.created_templates = 0
        self.reused_templates = 0
        self.created_assignments = 0
        self.skipped_assignments = 0
        self.event_driven_excluded: list = []
        self.failures: list = []


def template_frequency(frequency):
    return SAFETY_FREQ_MAP.get(frequency)


def _ensure_building_scope(catalog, building_name, tally) -> None:
    scope_exists = frappe.db.exists(
        "Safety Task Building Scope",
        {"parent": catalog.name, "parenttype": "Safety Task Catalog", "building": building_name},
    )
    if scope_exists:
        tally.skipped_scopes += 1
        return
    try:
        doc = frappe.get_doc("Safety Task Catalog", catalog.name)
        doc.append("applicable_buildings", {"building": building_name})
        doc.save()
        tally.created_scopes += 1
    except Exception as exc:
        tally.failures.append(
            _("Scope for catalog {0}: {1}").format(catalog.name, str(exc))
        )


def _get_or_create_template(catalog, template_freq):
    existing = frappe.db.get_value(
        "Scheduled Task Template", {"safety_task_catalog": catalog.name}, "name",
        order_by="creation asc",
    )
    if existing:
        has_item = frappe.db.exists(
            "Scheduled Task Template Item",
            {"parent": existing, "parenttype": "Scheduled Task Template",
             "task_catalog": catalog.name},
        )
        if not has_item:
            tmpl = frappe.get_doc("Scheduled Task Template", existing)
            tmpl.append("template_items", {"task_catalog": catalog.name, "is_active": 1})
            tmpl.save()
        return existing, False

    title = catalog.task_title or catalog.task_code or catalog.name
    tmpl = frappe.get_doc({
        "doctype": "Scheduled Task Template",
        "template_name": f"Safety [{catalog.task_code}] {title}"[:140],
        "task_type": "Safety",
        "frequency": template_freq,
        "safety_task_catalog": catalog.name,
        "is_active": 1,
        "template_items": [{"task_catalog": catalog.name, "is_active": 1}],
    }).insert()
    return tmpl.name, True


def _ensure_assignment(catalog, template_name, building_name, tally) -> None:
    if frappe.db.exists(
        "Scheduled Task Assignment",
        {"template": template_name, "building": building_name},
    ):
        tally.skipped_assignments += 1
        return
    try:
        frappe.get_doc({
            "doctype": "Scheduled Task Assignment",
            "template": template_name,
            "building": building_name,
            "effective_from": today(),
            "is_active": 1,
        }).insert()
        tally.created_assignments += 1
    except Exception as exc:
        tally.failures.append(
            _("Assignment for catalog {0}: {1}").format(catalog.name, str(exc))
        )


def apply_catalog(catalog, building_name, tally) -> None:
    if not catalog.applicable_to_all_buildings:
        _ensure_building_scope(catalog, building_name, tally)

    if catalog.frequency in EVENT_DRIVEN_FREQUENCIES:
        tally.event_driven_excluded.append(catalog.task_code or catalog.name)
        return

    template_freq = template_frequency(catalog.frequency)
    if not template_freq:
        frappe.throw(
            _('Safety Task Catalog {0} has frequency "{1}", which has no scheduling '
              "equivalent. Set a supported catalog frequency (Daily, Weekly, Monthly, "
              "Quarterly, Annual) or map it before generating.").format(
                catalog.name, catalog.frequency
            ),
            title=_("Unmapped Safety Frequency"),
        )

    try:
        tmpl_name, tmpl_created = _get_or_create_template(catalog, template_freq)
        if tmpl_created:
            tally.created_templates += 1
        else:
            tally.reused_templates += 1
    except Exception as exc:
        tally.failures.append(
            _("Template for catalog {0}: {1}").format(catalog.name, str(exc))
        )
        return

    _ensure_assignment(catalog, tmpl_name, building_name, tally)


def setup_summary(tally) -> dict:
    return {
        "created_templates": tally.created_templates,
        "reused_templates": tally.reused_templates,
        "created_assignments": tally.created_assignments,
        "skipped_assignments": tally.skipped_assignments,
        "created_scopes": tally.created_scopes,
        "skipped_scopes": tally.skipped_scopes,
        "event_driven_excluded": tally.event_driven_excluded,
        "failures": tally.failures,
        "license_reminder": (
            "Building License records must be created manually with real license numbers. "
            "Recommended types: Civil Defense, Municipal Operating License, Accommodation Registration."
        ),
    }


def setup_message(tally) -> str:
    msg = _("Safety setup complete. Assignments created: {0}, skipped (existing): {1}. "
            "Templates created: {2}, reused: {3}.").format(
        tally.created_assignments, tally.skipped_assignments,
        tally.created_templates, tally.reused_templates
    )
    if tally.event_driven_excluded:
        msg += "<br><br>" + _(
            "{0} event-driven task(s) (As Needed / On Entry) were not scheduled — they "
            "run on a trigger, not a calendar: {1}."
        ).format(len(tally.event_driven_excluded), ", ".join(tally.event_driven_excluded))
    if tally.failures:
        failure_lines = "<br>".join(tally.failures)
        msg += "<br><br>" + _("Failures ({0}):").format(len(tally.failures)) + "<br>" + failure_lines
    return msg


def report_setup(tally) -> dict:
    summary = setup_summary(tally)
    frappe.msgprint(
        setup_message(tally),
        title=_("Safety Setup Generator"),
        indicator="green" if not tally.failures else "orange",
    )
    return summary
