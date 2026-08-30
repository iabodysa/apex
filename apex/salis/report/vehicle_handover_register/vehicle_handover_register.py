# Copyright (c) 2026, afmcoltd


import frappe
from frappe import _

from apex.apex_core.utils.report_helpers import date_range_condition
from apex.apex_core.utils.report_summary import count_card, percent_card


def execute(filters=None):
    filters = filters or {}
    columns = get_columns()

    query_filters = {"docstatus": 1}
    if filters.get("vehicle"):
        query_filters["vehicle"] = filters["vehicle"]
    if filters.get("discrepancy_status"):
        query_filters["discrepancy_status"] = filters["discrepancy_status"]
    date_condition = date_range_condition(filters, "handover_date")
    if date_condition is not None:
        query_filters["handover_date"] = date_condition

    handovers = frappe.get_list(
        "Vehicle Handover",
        filters=query_filters,
        fields=[
            "name",
            "handover_date",
            "handover_time",
            "vehicle",
            "from_driver",
            "to_driver",
            "odometer_reading",
            "discrepancy_status",
            "signed_evidence",
        ],
        order_by="handover_date desc, handover_time desc",
    )
    if filters.get("driver"):
        driver = filters["driver"]
        handovers = [h for h in handovers if driver in (h.from_driver, h.to_driver)]
    if not handovers:
        return columns, [], None, None, get_report_summary([])

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
                "handover_time": handover.handover_time,
                "vehicle": handover.vehicle,
                "from_driver": handover.from_driver,
                "to_driver": handover.to_driver,
                "odometer_reading": handover.odometer_reading,
                "discrepancy_status": handover.discrepancy_status,
                "is_signed": bool(handover.signed_evidence),
                "signed": _("Yes") if handover.signed_evidence else _("No"),
                "failed_checks": failed.get(handover.name, 0),
            }
        )

    if filters.get("unsigned_only"):
        data = [r for r in data if not r.get("is_signed")]

    return columns, data, None, None, get_report_summary(data)


def get_report_summary(data):
    unsigned = [r for r in data if not r.get("is_signed")]
    discrepancies = [r for r in data if r.get("discrepancy_status") == "Discrepancy"]
    return [
        count_card(_("Handovers"), data),
        count_card(_("Open Discrepancies"), discrepancies, indicator="Red" if discrepancies else None),
        count_card(_("Unsigned"), unsigned, indicator="Orange" if unsigned else None),
        percent_card(_("Signed"), len(data) - len(unsigned), len(data)),
    ]


def get_columns():
    return [
        {"label": _("Handover"), "fieldname": "name", "fieldtype": "Link", "options": "Vehicle Handover", "width": 150},
        {"label": _("Handover Date"), "fieldname": "handover_date", "fieldtype": "Date", "width": 115},
        {"label": _("Handover Time"), "fieldname": "handover_time", "fieldtype": "Time", "width": 90},
        {"label": _("Vehicle"), "fieldname": "vehicle", "fieldtype": "Link", "options": "Salis Vehicle", "width": 150},
        {"label": _("From Driver"), "fieldname": "from_driver", "fieldtype": "Link", "options": "Salis Driver", "width": 160},
        {"label": _("To Driver"), "fieldname": "to_driver", "fieldtype": "Link", "options": "Salis Driver", "width": 160},
        {"label": _("Odometer Reading"), "fieldname": "odometer_reading", "fieldtype": "Int", "width": 130},
        {"label": _("Discrepancy Status"), "fieldname": "discrepancy_status", "fieldtype": "Data", "width": 140},
        {"label": _("Signed"), "fieldname": "signed", "fieldtype": "Data", "width": 80},
        {"label": _("Failed Checks"), "fieldname": "failed_checks", "fieldtype": "Int", "width": 110},
    ]
