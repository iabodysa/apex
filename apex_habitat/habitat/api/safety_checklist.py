"""Safety Checklist API.

The testable backend for the Safety Checklist desk Page (the Page UI/JS is a
separate task and lives elsewhere). It reuses the safety-round backend: a round
is the periodic safety pass over one building for a given cadence, recorded as a
Safety Round grouping a set of submitted Safety Task Execution rows.

This module adds NO result/compliance logic of its own. The overall result is
derived by the Safety Round controller's on_submit (worst execution status
wins); the expected task set mirrors the Safety Round Compliance report's
two-mode catalog scope so the Page and the report agree on which tasks belong to
a (building, cadence).

Two endpoints:

- :func:`get_tasks_for_cadence` returns the EXPECTED catalog tasks the operator
  should check for a (building, cadence): active tasks of that frequency whose
  building scope covers the building (applies-to-all OR named in the Safety Task
  Building Scope child table). Read-only.
- :func:`submit_round` records one round as a single transaction: a Safety Round
  plus one submitted Safety Task Execution per checklist line, with the round
  submitted last so its on_submit reads the full execution set. Wrapped in a
  savepoint so a failure on any line leaves no partial round behind.
"""

from __future__ import annotations

import json

import frappe
from frappe import _

# Mirrors safety_round_compliance._expected_tasks: only active catalog rows of
# the requested frequency are in scope.
_SCOPE_BASE = {"is_active": 1}


@frappe.whitelist()
def get_tasks_for_cadence(building, cadence):
    """Return the expected Safety Task Catalog rows for a (building, cadence).

    Uses the SAME two-mode scope as
    ``safety_round_compliance._expected_tasks``: a task is expected when it is
    active, its ``frequency`` equals ``cadence``, AND either it applies to all
    buildings (``applicable_to_all_buildings == 1``) OR it names this building in
    its ``applicable_buildings`` child table (Safety Task Building Scope). Both
    modes are combined and de-duplicated, so the checklist denominator matches
    the compliance report exactly.

    Permission: caller must have ``read`` on Safety Task Catalog (checked
    explicitly below; defense in depth over the role grant).

    Args:
        building: Accommodation Building docname (source of truth).
        cadence: one of Daily / Weekly / Monthly / Quarterly / Annual.

    Returns:
        dict shaped as ``{"building", "cadence", "tasks": [...]}`` where each
        task carries ``name``, ``task_code``, ``task_title``, ``task_title_en``,
        ``department``, ``priority``, ``instructions``, and ``evidence_required``
        — enough for the Page to render one checklist row per task. ``tasks`` is
        ordered by ``task_code`` for a stable render.
    """
    frappe.has_permission("Safety Task Catalog", "read", throw=True)

    if not cadence:
        frappe.throw(_("A cadence is required to build the checklist."))
    if not building:
        frappe.throw(_("A building is required to build the checklist."))

    # Whatever the form needs to render a row. These are the real catalog field
    # names (verified against safety_task_catalog.json).
    fields = [
        "name",
        "task_code",
        "task_title",
        "task_title_en",
        "department",
        "priority",
        "instructions",
        "evidence_required",
    ]
    base = {**_SCOPE_BASE, "frequency": cadence}

    # Mode 1: tasks that apply to every building.
    tasks = {}
    for t in frappe.get_all(
        "Safety Task Catalog",
        filters={**base, "applicable_to_all_buildings": 1},
        fields=fields,
    ):
        tasks[t.name] = t

    # Mode 2: tasks scoped to THIS building via the child table.
    scoped_parents = frappe.get_all(
        "Safety Task Building Scope",
        filters={"parenttype": "Safety Task Catalog", "building": building},
        pluck="parent",
    )
    if scoped_parents:
        for t in frappe.get_all(
            "Safety Task Catalog",
            filters={
                **base,
                "applicable_to_all_buildings": 0,
                "name": ["in", scoped_parents],
            },
            fields=fields,
        ):
            tasks.setdefault(t.name, t)

    ordered = sorted(tasks.values(), key=lambda t: str(t.get("task_code") or t.name))
    return {"building": building, "cadence": cadence, "tasks": ordered}


@frappe.whitelist(methods=["POST"])
def submit_round(building, cadence, round_date, lines, is_reinspection=0):
    """Record one safety round as a single, all-or-nothing transaction.

    Inserts a Safety Round (not yet submitted), inserts and submits one Safety
    Task Execution per checklist line linked back to the round, then submits the
    round LAST so the Safety Round controller's on_submit reads the full
    execution set and derives ``overall_result`` (worst status wins: any Not
    Done -> Fail; else any Poor -> Needs Attention; else Pass).

    The whole sequence runs inside a DB savepoint: on any error every write is
    rolled back to the savepoint (no partial round, no orphan executions) and the
    error is re-raised so the caller sees what failed — including the Safety
    Round duplicate guard, which throws for a second non-reinspection round on
    the same (building, date, cadence).

    Permission: caller must have ``submit`` on Safety Task Execution (checked
    explicitly via ``frappe.has_permission(..., throw=True)``). NOTE: the Safety
    Officer role has create but NOT submit on Safety Task Execution, so this
    endpoint is for roles that can submit (Accommodation Manager, Resident
    Supervisor, System Manager); a Safety Officer is rejected here rather than
    silently producing unsubmitted rows.

    Args:
        building: Accommodation Building docname (source of truth).
        cadence: one of Daily / Weekly / Monthly / Quarterly / Annual.
        round_date: the round date; also used as each execution's
            ``execution_date``.
        lines: a JSON list (or already-parsed list) of dicts, each
            ``{"task": <Safety Task Catalog>, "execution_status": <status>,
            "notes": <optional>}``. ``execution_status`` is one of Excellent /
            Good / Average / Poor / Not Done.
        is_reinspection: pass truthy to record a follow-up round for the same
            (building, date, cadence) past the duplicate guard.

    Returns:
        dict ``{"ok": True, "safety_round": <docname>, "overall_result": <str>,
        "count": <int executions>}``.
    """
    # Safety Officer has create but NOT submit on Safety Task Execution: gate on
    # submit so this method only proceeds for roles that can actually submit the
    # executions (and the round). Do not silently swallow that.
    frappe.has_permission("Safety Task Execution", "submit", throw=True)

    if not building:
        frappe.throw(_("A building is required to submit a round."))
    if not cadence:
        frappe.throw(_("A cadence is required to submit a round."))
    if not round_date:
        frappe.throw(_("A round date is required to submit a round."))

    # `lines` arrives as a JSON string over HTTP; accept an already-parsed list
    # too so server-side callers and tests can pass a list directly.
    if isinstance(lines, str):
        lines = json.loads(lines)
    if not isinstance(lines, list):
        frappe.throw(_("Checklist lines must be a list."))

    is_reinspection = 1 if frappe.utils.cint(is_reinspection) else 0

    # One nested transaction for the whole round: insert round + N submitted
    # executions + submit round. Any failure rolls back to here so no partial
    # round survives; the error is re-raised for the caller to surface.
    savepoint = "safety_checklist_submit_round"
    frappe.db.savepoint(savepoint)
    try:
        # Insert the round but do NOT submit yet — the executions must exist and
        # be submitted first so on_submit can read them.
        round_doc = frappe.get_doc(
            {
                "doctype": "Safety Round",
                "building": building,
                "round_date": round_date,
                "cadence": cadence,
                "supervisor": frappe.session.user,
                "is_reinspection": is_reinspection,
            }
        )
        round_doc.insert(ignore_permissions=False)

        count = 0
        for line in lines:
            task = line.get("task")
            execution_status = line.get("execution_status")
            if not task or not execution_status:
                frappe.throw(
                    _("Each checklist line needs a task and an execution status.")
                )
            ste = frappe.get_doc(
                {
                    "doctype": "Safety Task Execution",
                    "building": building,
                    "task": task,
                    "execution_date": round_date,
                    "execution_status": execution_status,
                    "notes": line.get("notes"),
                    "safety_round": round_doc.name,
                }
            )
            ste.insert(ignore_permissions=False)
            ste.submit()
            count += 1

        # Submit the round LAST so its on_submit derives overall_result from the
        # full, already-submitted execution set.
        round_doc.submit()
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
    else:
        frappe.db.release_savepoint(savepoint)

    round_doc.reload()
    return {
        "ok": True,
        "safety_round": round_doc.name,
        "overall_result": round_doc.overall_result,
        "count": count,
    }
