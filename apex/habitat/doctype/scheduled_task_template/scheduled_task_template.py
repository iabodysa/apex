# Copyright (c) 2026, afmcoltd
"""Scheduled Task Template controller."""

from __future__ import annotations

from frappe.model.document import Document


class ScheduledTaskTemplate(Document):
    """Recurrence definition for a Building's operational checklist, cross-produced
    against every active Scheduled Task Assignment by
    ``apex.habitat.tasks.scheduled_tasks.daily_scheduled_task_instance_generator``.

    Not Auto Repeat: ``validate_reference_doctype``
    (frappe/automation/doctype/auto_repeat/auto_repeat.py:113-119) requires the
    repeated doctype to carry ``allow_auto_repeat``, and ``make_new_document``
    (frappe/automation/doctype/auto_repeat/auto_repeat.py:238-239) clones ONE
    reference document of that SAME doctype on its own schedule. This template and
    its instance are two different doctypes, and one template fans out to many
    instances per period (one per assignment x template item), not one clone of
    itself; Auto Repeat also carries no location field to cross with.

    Not ERPNext Asset Maintenance: ``Asset Maintenance.asset_name``
    (erpnext/assets/doctype/asset_maintenance/asset_maintenance.json) is a
    mandatory Link to ``Asset``, a depreciable, GL-tracked entity. A Building is
    deliberately kept outside ERPNext Asset in this app (see CLAUDE.md's
    ``facility_asset`` hybrid-bridge doctrine); routing a recurring safety/cleaning
    checklist through Asset Maintenance would put every scheduled Building task
    under fixed-asset depreciation it has nothing to do with.

    Not ERPNext Maintenance Schedule: ``Maintenance Schedule``
    (erpnext/maintenance/doctype/maintenance_schedule/maintenance_schedule.json)
    anchors on ``customer`` and ``items`` (Item Code) — an external after-sales
    service contract against a sold item, not an internal Building checklist.

    What DOES map: ``frequency`` is the same recurrence vocabulary as
    ``Asset Maintenance Task.periodicity``; a Scheduled Task Instance's submit
    lifecycle plus ``completed_date``/``cancellation_reason``
    (scheduled_task_instance.py:on_submit, :mark_completed, :before_cancel) is the
    same completion-evidence shape as ``Asset Maintenance Log``. What has no home
    in either family is ``Scheduled Task Assignment.building`` — the location axis
    this template is cross-produced against — since neither Asset Maintenance nor
    Maintenance Schedule carries a location field at all.
    """
