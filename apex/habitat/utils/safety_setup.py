# Copyright (c) 2026, afmcoltd
"""The safety-setup generator: one building's Safety Task Catalog wiring.

For each active catalog entry the generator puts the building in the catalog's
scope, gets-or-creates the ONE reusable Scheduled Task Template for that task, and
assigns that template to the building. Every step is idempotent — the template is
keyed on the catalog, the assignment on (template, building), the scope on
(catalog, building) — so a re-run creates nothing twice.

Frequency classification and the operator report take plain values and return
values; only the four ``_ensure``/``_get_or_create`` helpers touch the database.

Those four pass ``ignore_permissions`` because they write the SCHEDULE, not an operator's record:
a scope row, the one reusable template, and the template-to-building assignment. The operator asks
for a building to be wired up and the generator derives everything else from the catalog. Granting
the role create on Scheduled Task Template would let a supervisor invent templates outside the
catalog, which is what keeps the catalog the single source of the safety programme.
"""

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
    """What one generator run did, folded as it goes."""

    def __init__(self):
        """Initializes the zeroed counters and empty lists that tally one safety-setup generator run."""
        self.created_scopes = 0
        self.skipped_scopes = 0
        self.created_templates = 0
        self.reused_templates = 0
        self.created_assignments = 0
        self.skipped_assignments = 0
        self.event_driven_excluded: list = []
        self.failures: list = []


def is_event_driven(frequency) -> bool:
    """An event-driven catalog task runs on a trigger, not a calendar, so it has no
    schedulable period and is reported rather than assigned."""
    return frequency in EVENT_DRIVEN_FREQUENCIES


def template_frequency(frequency):
    """The Scheduled Task Template Select value for a catalog period, or None when
    the catalog period has no scheduling equivalent."""
    return SAFETY_FREQ_MAP.get(frequency)


def _ensure_building_scope(catalog, building_name, tally) -> None:
    """Put the building inside a non-universal catalog task's applicable scope.

    Appended through the parent and saved, not inserted standalone: a standalone child
    row survives only until the catalog's own next save, which drops every stored child
    row absent from the in-memory parent (document.py:471-496) and silently narrows the
    task's scope with no error. ``_get_or_create_template`` below does this correctly
    for its own child table; this mirrors it.
    """
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
        doc.save(ignore_permissions=True)
        tally.created_scopes += 1
    except Exception as exc:
        tally.failures.append(
            _("Scope for catalog {0}: {1}").format(catalog.name, str(exc))
        )


def _get_or_create_template(catalog, template_freq):
    """The ONE reusable Scheduled Task Template for a Safety Task Catalog entry.

    Building-independent: a template is bound to buildings via
    Scheduled Task Assignment, never an on-template building field (that column was
    dropped). Keyed on the immutable ``safety_task_catalog`` link so re-runs and other
    buildings' setups share ONE template per catalog task. Guarantees the catalog is an
    active ``template_items`` row — the generator iterates those rows, so a template
    lacking them (e.g. one carried over from the pre-redesign model) would silently
    generate nothing. Returns ``(template_name, created)``.
    """
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
            tmpl.save(ignore_permissions=True)
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
    }).insert(ignore_permissions=True)
    return tmpl.name, True


def _ensure_assignment(catalog, template_name, building_name, tally) -> None:
    """Bind the catalog's template to this building; the daily generator turns each
    active assignment x item into Scheduled Task Instances."""
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
        }).insert(ignore_permissions=True)
        tally.created_assignments += 1
    except Exception as exc:
        tally.failures.append(
            _("Assignment for catalog {0}: {1}").format(catalog.name, str(exc))
        )


def apply_catalog(catalog, building_name, tally) -> None:
    """Wire ONE catalog task to the building: scope, template, assignment.

    An unmapped catalog frequency fails loudly rather than being silently swallowed
    by the closed template Select; a template failure is recorded and skips only that
    catalog, so one bad entry cannot abandon the rest of the run."""
    if not catalog.applicable_to_all_buildings:
        _ensure_building_scope(catalog, building_name, tally)

    if is_event_driven(catalog.frequency):
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
    """The machine-readable outcome of a run.

    Building License records are NOT created — they need a real license_number — so
    the summary names the types an operator still has to create by hand."""
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
    """The operator-facing account of the same run."""
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
    """Emit the operator msgprint and return the summary dict."""
    summary = setup_summary(tally)
    frappe.msgprint(
        setup_message(tally),
        title=_("Safety Setup Generator"),
        indicator="green" if not tally.failures else "orange",
    )
    return summary
