# Copyright (c) 2026, AFMCO and contributors
# [#j03s5a]

"""Safety Task Compliance Summary.

Derives per-task compliance from submitted Safety Task Execution rows. The
denominator is the EXPECTED task set for the selected cadence and building -
the Safety Task Catalog tasks of that frequency whose building scope covers the
building. Scope is two-mode: a task either applies to all buildings
(applicable_to_all_buildings == 1) OR names the building in its
applicable_buildings child table (Safety Task Building Scope). Both modes are
replicated here; otherwise expected-vs-executed compliance would be wrong.

For each expected task the report reports its last execution status in the
window, the executed count, the needs-attention count (Poor + Not Done),
whether any execution carried photo evidence, and a linked Maintenance Request
if one was raised. Tasks expected but never executed surface with a blank
status and a zero executed count.
"""

import frappe
from frappe.utils import add_days, getdate, today

from apex.habitat import permissions


NEEDS_ATTENTION_STATUSES = ("Poor", "Not Done")


def execute(filters=None):
    filters = filters or {}

    cadence = filters.get("cadence")
    building = filters.get("building")
    date_from = getdate(filters.get("from_date") or add_days(today(), -30))
    date_to = getdate(filters.get("to_date") or today())

    columns = _columns()

    expected = _expected_tasks(cadence, building)
    executions = _executions(cadence, building, date_from, date_to)

    # Group executions by task, newest first so the first row seen is the last one.
    by_task = {}
    for ex in executions:
        by_task.setdefault(ex.task, []).append(ex)

    # The task universe is the expected set, plus any executed task not in it
    # (e.g. an ad-hoc or out-of-scope execution) so nothing is silently dropped.
    task_names = list(expected.keys())
    for task in by_task:
        if task not in expected:
            task_names.append(task)

    data = []
    for task in task_names:
        rows = by_task.get(task, [])
        executed_count = len(rows)
        last_status = rows[0].execution_status if rows else ""
        needs_attention = sum(
            1 for r in rows if r.execution_status in NEEDS_ATTENTION_STATUSES
        )
        done_count = executed_count - needs_attention
        has_evidence = any(r.evidence_photo for r in rows)
        linked_mr = next((r.linked_maintenance_request for r in rows if r.linked_maintenance_request), "")

        data.append({
            "task": task,
            "task_title": expected.get(task, {}).get("task_title", ""),
            "expected": 1 if task in expected else 0,
            "executed_count": executed_count,
            "last_status": last_status,
            "done_count": done_count,
            "needs_attention_count": needs_attention,
            "has_evidence": 1 if has_evidence else 0,
            "linked_maintenance_request": linked_mr,
        })

    return columns, data


def _columns():
    return [
        {"label": frappe._("Task"), "fieldname": "task", "fieldtype": "Link",
         "options": "Safety Task Catalog", "width": 140},
        {"label": frappe._("Task Title"), "fieldname": "task_title", "fieldtype": "Data", "width": 200},
        {"label": frappe._("Expected"), "fieldname": "expected", "fieldtype": "Check", "width": 80},
        {"label": frappe._("Executed"), "fieldname": "executed_count", "fieldtype": "Int", "width": 90},
        {"label": frappe._("Last Status"), "fieldname": "last_status", "fieldtype": "Data", "width": 110},
        {"label": frappe._("Done"), "fieldname": "done_count", "fieldtype": "Int", "width": 80},
        {"label": frappe._("Needs Attention"), "fieldname": "needs_attention_count",
         "fieldtype": "Int", "width": 130},
        {"label": frappe._("Evidence"), "fieldname": "has_evidence", "fieldtype": "Check", "width": 90},
        {"label": frappe._("Linked Maintenance"), "fieldname": "linked_maintenance_request",
         "fieldtype": "Link", "options": "Maintenance Request", "width": 160},
    ]


def _expected_tasks(cadence, building):
    """The expected task set for the cadence and building, keyed by task name.

    Two scope modes are combined: tasks applying to all buildings, and tasks
    that name this building in their Safety Task Building Scope child table.
    Without a cadence the report is not denominator-driven, so the expected set
    is empty (executed tasks still surface as expected=0).
    """
    if not cadence:
        return {}

    base = {"is_active": 1, "frequency": cadence}

    # Mode 1: applies to all buildings.
    all_buildings = frappe.get_all(
        "Safety Task Catalog",
        filters={**base, "applicable_to_all_buildings": 1},
        fields=["name", "task_title"],
    )
    expected = {t.name: {"task_title": t.task_title} for t in all_buildings}

    # Mode 2: scoped to specific buildings via the child table.
    if building:
        scoped_parents = frappe.get_all(
            "Safety Task Building Scope",
            filters={"parenttype": "Safety Task Catalog", "building": building},
            pluck="parent",
        )
        if scoped_parents:
            scoped = frappe.get_all(
                "Safety Task Catalog",
                filters={**base, "applicable_to_all_buildings": 0, "name": ["in", scoped_parents]},
                fields=["name", "task_title"],
            )
            for t in scoped:
                expected.setdefault(t.name, {"task_title": t.task_title})

    return expected


def _executions(cadence, building, date_from, date_to):
    query_filters = {
        "docstatus": 1,
        "execution_date": ["between", [str(date_from), str(date_to)]],
    }
    if building:
        query_filters["building"] = building
    if cadence:
        query_filters["frequency"] = cadence

    # get_all forces ignore_permissions, bypassing the building row-scoping the desk
    # list gets via permission_query_conditions; confine executions to the caller's
    # buildings so a scoped user never sees another estate's executions.
    restrict, allowed = permissions.report_building_scope(frappe.session.user)
    if restrict:
        chosen = query_filters.get("building")
        if not allowed or (chosen and chosen not in allowed):
            return []
        if not chosen:
            query_filters["building"] = ["in", allowed]

    return frappe.get_all(
        "Safety Task Execution",
        filters=query_filters,
        fields=[
            "name", "task", "execution_status", "execution_date",
            "evidence_photo", "linked_maintenance_request",
        ],
        order_by="execution_date desc, modified desc",
        limit_page_length=0,
    )
