# Copyright (c) 2026, AFMCO and contributors
"""Timesheet Exception Workbench - open data-quality exceptions, de-duplicated.

Groups the immutable Timesheet Exception Log by (type, entity, period, field) so
identical exceptions collapse to one actionable row with an occurrence count and
its disposition status (Open / Waived / Resolved). GATE groups sort first. The
grouping + disposition join is shared with the whitelisted workbench API so both
surfaces agree. Acting on a group is a TS Exception Disposition, never an edit of
the log row.
"""

from frappe import _

from apex_habitat.logistay.api.exception_workbench import get_grouped_exceptions


def execute(filters=None):
    filters = filters or {}
    return get_columns(), get_data(filters)


def get_columns():
    return [
        {"label": _("Severity"), "fieldname": "severity", "fieldtype": "Data", "width": 90},
        {"label": _("Type"), "fieldname": "exception_type", "fieldtype": "Data", "width": 170},
        {"label": _("Entity"), "fieldname": "entity", "fieldtype": "Data", "width": 160},
        {"label": _("Period"), "fieldname": "period_month", "fieldtype": "Data", "width": 90},
        {"label": _("Field"), "fieldname": "field_ref", "fieldtype": "Data", "width": 130},
        {"label": _("Count"), "fieldname": "occurrences", "fieldtype": "Int", "width": 80},
        {"label": _("Latest"), "fieldname": "latest_detected_at", "fieldtype": "Datetime", "width": 160},
        {"label": _("Disposition"), "fieldname": "disposition", "fieldtype": "Data", "width": 110},
        {"label": _("Disposed By"), "fieldname": "disposed_by", "fieldtype": "Link", "options": "User", "width": 150},
        {"label": _("Detail"), "fieldname": "sample_detail", "fieldtype": "Data", "width": 300},
        {"label": _("Group Key"), "fieldname": "group_key", "fieldtype": "Data", "width": 130},
    ]


def get_data(filters):
    return get_grouped_exceptions(filters)
