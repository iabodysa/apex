# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe

from apex.salis.api.dispatch_board import _permitted_projects


def scope_filter():
    unscoped, projects = _permitted_projects()
    if unscoped:
        return True, None, {}
    if not projects:
        return False, projects, None
    return False, projects, {"project": ["in", projects]}


def scoped_vehicles(fields, base_filters, extra_filters=None, or_filters=None, order_by="plate_number asc"):
    filters = dict(base_filters or {})
    if extra_filters:
        filters.update(extra_filters)
    return frappe.get_all(
        "Salis Vehicle",
        filters=filters,
        or_filters=or_filters,
        fields=fields,
        order_by=order_by,
        limit_page_length=0,
    )


def driver_names(vehicle_rows):
    ids = list({v.get("current_driver") for v in vehicle_rows if v.get("current_driver")})
    if not ids:
        return {}
    return {
        d.name: d.full_name
        for d in frappe.get_all(
            "Salis Driver",
            filters={"name": ["in", ids]},
            fields=["name", "full_name"],
        )
    }
