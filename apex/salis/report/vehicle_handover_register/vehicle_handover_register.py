# Copyright (c) 2026, AFMCO and contributors

"""Vehicle Handover Register — which vehicle changed hands, between whom, and whether
the handover is clean.

The rows are DOCUMENT rows: the fact is the handover itself, and the checklist under it
is evidence for that fact, so each row carries the count of failed check items rather
than a line per check. Only submitted handovers are listed — a draft has not changed
hands, and a cancelled one is out with docstatus 2.

Scoped by the vehicle's project through the same resolver the permission hook uses, so
a scope correction reaches this report and the desk list together.
"""

import frappe
from frappe import _

from apex.apex_core.utils.report_helpers import date_range_condition, scoped_names
from apex.apex_core.utils.report_summary import count_card, percent_card
from apex.salis import permissions


def execute(filters=None):
    filters = filters or {}
    columns = _columns()

    query_filters = {"docstatus": 1}
    if filters.get("vehicle"):
        query_filters["vehicle"] = filters["vehicle"]
    if filters.get("discrepancy_status"):
        query_filters["discrepancy_status"] = filters["discrepancy_status"]
    date_condition = date_range_condition(filters, "handover_date")
    if date_condition is not None:
        query_filters["handover_date"] = date_condition

    restrict, allowed = permissions.report_project_scope(frappe.session.user)
    if restrict:
        in_scope = scoped_names("Salis Vehicle", allowed) if allowed else []
        chosen = query_filters.get("vehicle")
        if not in_scope or (chosen and chosen not in in_scope):
            return columns, [], None, None, _summary([])
        if not chosen:
            query_filters["vehicle"] = ["in", in_scope]

    handovers = frappe.get_all(
        "Vehicle Handover",
        filters=query_filters,
        fields=[
            "name",
            "handover_date",
            "vehicle",
            "from_driver",
            "to_driver",
            "odometer_reading",
            "discrepancy_status",
            "signed_evidence",
        ],
        order_by="handover_date desc",
    )
    if filters.get("driver"):
        driver = filters["driver"]
        handovers = [h for h in handovers if driver in (h.from_driver, h.to_driver)]
    if not handovers:
        return columns, [], None, None, _summary([])

    failed = {}
    for item in frappe.get_all(
        "Vehicle Handover Item",
        filters={
            "parent": ["in", [h.name for h in handovers]],
            "parenttype": "Vehicle Handover",
            "ok": 0,
        },
        fields=["parent"],
    ):
        failed[item.parent] = failed.get(item.parent, 0) + 1

    data = []
    for handover in handovers:
        data.append(
            {
                "name": handover.name,
                "handover_date": handover.handover_date,
                "vehicle": handover.vehicle,
                "from_driver": handover.from_driver,
                "to_driver": handover.to_driver,
                "odometer_reading": handover.odometer_reading,
                "discrepancy_status": handover.discrepancy_status,
                "signed": _("Yes") if handover.signed_evidence else _("No"),
                "failed_checks": failed.get(handover.name, 0),
            }
        )

    if filters.get("unsigned_only"):
        data = [r for r in data if r["signed"] == _("No")]

    return columns, data, None, None, _summary(data)


def _summary(data):
    """Built for any result including none, so an empty register reads 0 rather than a
    blank strip that looks like a page which failed to load."""
    unsigned = [r for r in data if r.get("signed") == _("No")]
    discrepancies = [r for r in data if r.get("discrepancy_status") == "Discrepancy"]
    return [
        count_card(_("Handovers"), data),
        count_card(_("Open Discrepancies"), discrepancies, indicator="Red" if discrepancies else None),
        count_card(_("Unsigned"), unsigned, indicator="Orange" if unsigned else None),
        percent_card(_("Signed"), len(data) - len(unsigned), len(data)),
    ]


def _columns():
    return [
        {"label": _("Handover"), "fieldname": "name", "fieldtype": "Link", "options": "Vehicle Handover", "width": 150},
        {"label": _("Handover Date"), "fieldname": "handover_date", "fieldtype": "Date", "width": 115},
        {"label": _("Vehicle"), "fieldname": "vehicle", "fieldtype": "Link", "options": "Salis Vehicle", "width": 150},
        {"label": _("From Driver"), "fieldname": "from_driver", "fieldtype": "Link", "options": "Salis Driver", "width": 160},
        {"label": _("To Driver"), "fieldname": "to_driver", "fieldtype": "Link", "options": "Salis Driver", "width": 160},
        {"label": _("Odometer Reading"), "fieldname": "odometer_reading", "fieldtype": "Int", "width": 130},
        {"label": _("Discrepancy Status"), "fieldname": "discrepancy_status", "fieldtype": "Data", "width": 140},
        {"label": _("Signed"), "fieldname": "signed", "fieldtype": "Data", "width": 80},
        {"label": _("Failed Checks"), "fieldname": "failed_checks", "fieldtype": "Int", "width": 110},
    ]
