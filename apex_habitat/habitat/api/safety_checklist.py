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

Endpoints:

- :func:`get_tasks_for_cadence` returns the EXPECTED catalog tasks the operator
  should check for a (building, cadence): active tasks of that frequency whose
  building scope covers the building (applies-to-all OR named in the Safety Task
  Building Scope child table). Read-only.
- :func:`get_due_cadences` returns, for a building, only the cadences that have
  NO submitted Safety Round in the current period (today / this ISO week / this
  month / this calendar quarter / this year) together with each due cadence's
  expected tasks. Powers the safety portal's "what is due now" view. Read-only.
- :func:`submit_round` records one round as a single transaction: a Safety Round
  plus one submitted Safety Task Execution per checklist line, with the round
  submitted last so its on_submit reads the full execution set. Wrapped in a
  savepoint so a failure on any line leaves no partial round behind.
- :func:`submit_due_rounds` records, in one outer transaction, ONE round per
  cadence present in a multi-cadence result set (each via the shared
  :func:`_create_round` helper), then emails the manager a report. A mail
  failure never rolls back a submitted round.

Both submit endpoints share the private :func:`_create_round` helper so the
savepoint-per-round logic lives in exactly one place.
"""

from __future__ import annotations

import datetime
import json

import frappe
from frappe import _
from frappe.utils import (
    get_first_day,
    get_last_day,
    get_quarter_ending,
    get_quarter_start,
    get_year_ending,
    get_year_start,
    getdate,
    nowdate,
)

# Mirrors safety_round_compliance._expected_tasks: only active catalog rows of
# the requested frequency are in scope.
_SCOPE_BASE = {"is_active": 1}

# Canonical cadence order for the portal: shortest period first. get_due_cadences
# returns due cadences in this order, and it is the set submit_due_rounds groups by.
_CADENCE_ORDER = ["Daily", "Weekly", "Monthly", "Quarterly", "Annual"]

# Render fields for one checklist row — the real catalog field names (verified
# against safety_task_catalog.json). Shared by get_tasks_for_cadence and
# get_due_cadences so the two endpoints return identical task payloads.
_TASK_FIELDS = [
    "name",
    "task_code",
    "task_title",
    "task_title_en",
    "department",
    "priority",
    "instructions",
    "evidence_required",
]


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

    return {
        "building": building,
        "cadence": cadence,
        "tasks": _scoped_tasks(building, cadence),
    }


def _scoped_tasks(building, cadence):
    """Return the in-scope Safety Task Catalog rows for a (building, cadence).

    The two-mode catalog scope, factored out so get_tasks_for_cadence and
    get_due_cadences resolve the SAME task set the same way: active tasks of the
    given ``cadence`` that either apply to all buildings OR name this building in
    their Safety Task Building Scope child table. De-duplicated and ordered by
    ``task_code`` for a stable render.
    """
    base = {**_SCOPE_BASE, "frequency": cadence}

    # Mode 1: tasks that apply to every building.
    tasks = {}
    for t in frappe.get_all(
        "Safety Task Catalog",
        filters={**base, "applicable_to_all_buildings": 1},
        fields=_TASK_FIELDS,
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
            fields=_TASK_FIELDS,
        ):
            tasks.setdefault(t.name, t)

    return sorted(tasks.values(), key=lambda t: str(t.get("task_code") or t.name))


def _current_period(cadence, on_date=None):
    """Return ``(start, end, period_label)`` for ``cadence``'s CURRENT period.

    ``start`` / ``end`` are inclusive ``datetime.date`` boundaries used to test
    whether an existing round's ``round_date`` falls in the live period; the
    label is a short human string for the portal.

    Boundaries (all computed from ``on_date``, default today):

    - **Daily**: the single day ``on_date`` (start == end). Label ``Today``.
    - **Weekly**: the ISO week Monday..Sunday. Computed DIRECTLY from
      ``date.weekday()`` (Mon=0) — NOT frappe ``get_first_day_of_week``, which
      honours the System Settings week-start (Sunday by default) and would give
      a Sun..Sat window, not the ISO Mon..Sun the contract requires. Label
      ``This week``.
    - **Monthly**: first..last day of the month. Label is the month name+year,
      e.g. ``June 2026``.
    - **Quarterly**: the calendar quarter via ``get_quarter_start`` /
      ``get_quarter_ending``. Label e.g. ``Q2 2026``.
    - **Annual**: Jan 1..Dec 31 of the year. Label e.g. ``2026``.
    """
    day = getdate(on_date or nowdate())

    if cadence == "Daily":
        return day, day, "Today"

    if cadence == "Weekly":
        # ISO week: Monday (weekday()==0) start, Sunday end. Deterministic and
        # independent of the site's first_day_of_the_week setting.
        start = day - datetime.timedelta(days=day.weekday())
        end = start + datetime.timedelta(days=6)
        return start, end, "This week"

    if cadence == "Monthly":
        start = getdate(get_first_day(day))
        end = getdate(get_last_day(day))
        # e.g. "June 2026"
        return start, end, start.strftime("%B %Y")

    if cadence == "Quarterly":
        start = getdate(get_quarter_start(day))
        end = getdate(get_quarter_ending(day))
        quarter = (day.month - 1) // 3 + 1
        return start, end, f"Q{quarter} {day.year}"

    if cadence == "Annual":
        start = getdate(get_year_start(day))
        end = getdate(get_year_ending(day))
        return start, end, str(day.year)

    frappe.throw(_("Unknown cadence: {0}").format(cadence))


def _cadence_is_due(building, cadence, on_date=None):
    """A cadence is DUE when no SUBMITTED round covers the current period.

    Returns ``True`` iff there is NO Safety Round with ``docstatus == 1`` for
    this building and cadence whose ``round_date`` lies within the current
    period's inclusive ``[start, end]`` boundary. Drafts and cancelled rounds
    (docstatus 0 / 2) do NOT satisfy a cadence — only a submitted round closes
    it for the period.
    """
    start, end, _label = _current_period(cadence, on_date)
    existing = frappe.db.exists(
        "Safety Round",
        {
            "building": building,
            "cadence": cadence,
            "docstatus": 1,
            "round_date": ["between", [start, end]],
        },
    )
    return not existing


@frappe.whitelist()
def get_due_cadences(building):
    """Return the cadences DUE for a building, each with its expected tasks.

    For every cadence (Daily -> Weekly -> Monthly -> Quarterly -> Annual) that is
    DUE — no submitted Safety Round in the current period (see
    :func:`_cadence_is_due`) — AND that has at least one scoped task, include a
    block of that cadence's expected tasks. A due cadence with zero scoped tasks
    is omitted (nothing to check). A cadence already covered by a submitted round
    this period is omitted.

    So on a fresh building every cadence with tasks is due; after a Daily round
    is submitted today, Daily drops out for the rest of today; at the start of a
    new ISO week Daily and Weekly are due again.

    Permission: caller must have ``read`` on Safety Task Catalog (same gate as
    :func:`get_tasks_for_cadence`).

    Args:
        building: Accommodation Building docname (source of truth).

    Returns:
        ``{"building": building, "due": [ {"cadence", "period_label",
        "tasks": [...]}, ... ]}`` — ``due`` ordered Daily..Annual, each task
        carrying the same render fields as :func:`get_tasks_for_cadence`.
    """
    frappe.has_permission("Safety Task Catalog", "read", throw=True)

    if not building:
        frappe.throw(_("A building is required to compute due cadences."))

    due = []
    for cadence in _CADENCE_ORDER:
        if not _cadence_is_due(building, cadence):
            continue
        tasks = _scoped_tasks(building, cadence)
        if not tasks:
            # Due, but nothing scoped to check — omit it.
            continue
        _start, _end, period_label = _current_period(cadence)
        due.append(
            {"cadence": cadence, "period_label": period_label, "tasks": tasks}
        )

    return {"building": building, "due": due}


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

    round_doc, count = _create_round(
        building, cadence, round_date, lines, is_reinspection
    )

    round_doc.reload()
    return {
        "ok": True,
        "safety_round": round_doc.name,
        "overall_result": round_doc.overall_result,
        "count": count,
    }


def _create_round(building, cadence, round_date, lines, is_reinspection):
    """Insert + submit ONE Safety Round and its executions in a savepoint.

    The single source of truth for "record a round": inserts the Safety Round
    (not yet submitted), inserts and submits one Safety Task Execution per line
    linked back to the round, then submits the round LAST so its on_submit reads
    the full, already-submitted execution set and derives ``overall_result``.

    Wrapped in a named DB savepoint: any failure rolls every write back to the
    savepoint (no partial round, no orphan executions) and re-raises so the
    caller surfaces it — including the Safety Round duplicate guard. Both
    :func:`submit_round` (one round) and :func:`submit_due_rounds` (one per
    cadence) call this; the savepoint logic is NOT duplicated anywhere else.

    Callers gate permissions and parse ``lines`` BEFORE calling this; here we
    only validate each line has a task and a status.

    Returns ``(round_doc, count)`` — the SUBMITTED round document (caller may
    ``reload()`` to read derived fields) and the number of executions created.
    """
    # A distinct savepoint name per cadence so nesting submit_due_rounds' outer
    # savepoint and these inner ones never collide on the same identifier.
    savepoint = f"safety_checklist_round_{frappe.scrub(cadence)}"
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

    return round_doc, count


# Manager role notified after a successful submit_due_rounds. Used both to read a
# configurable recipient override and as the role fallback.
_REPORT_ROLE = "Accommodation Manager"


@frappe.whitelist(methods=["POST"])
def submit_due_rounds(building, round_date, results):
    """Record one round per cadence from a multi-cadence result set, then email.

    ``results`` is a JSON list (an already-parsed list is also accepted) of
    ``{"task", "cadence", "execution_status", "notes"?}`` lines spanning one or
    more cadences. The lines are grouped by ``cadence`` and, for EACH cadence
    that has lines, ONE Safety Round plus its submitted executions is created via
    the shared :func:`_create_round` helper (round submitted last).

    The whole multi-cadence submit runs inside ONE OUTER savepoint: if any
    cadence fails, every round created in this call is rolled back together — so
    a partial multi-cadence submit never persists. (Each :func:`_create_round`
    keeps its own inner savepoint; the outer one wraps them all.)

    After the rounds commit, the manager is emailed a report
    (:func:`_email_round_report`). A mail failure is caught and logged and never
    rolls back a submitted round; ``emailed`` reports whether mail was sent.

    Permission: caller must have ``submit`` on Safety Task Execution (same gate
    as :func:`submit_round`).

    Args:
        building: Accommodation Building docname (source of truth).
        round_date: the round date; also each execution's ``execution_date``.
        results: JSON list (or list) of ``{"task", "cadence",
            "execution_status", "notes"?}``.

    Returns:
        ``{"ok": True, "rounds": [{"cadence", "safety_round", "overall_result"}],
        "count": <total executions>, "emailed": <bool>}`` — ``rounds`` ordered
        Daily..Annual.
    """
    frappe.has_permission("Safety Task Execution", "submit", throw=True)

    if not building:
        frappe.throw(_("A building is required to submit rounds."))
    if not round_date:
        frappe.throw(_("A round date is required to submit rounds."))

    if isinstance(results, str):
        results = json.loads(results)
    if not isinstance(results, list):
        frappe.throw(_("Results must be a list."))

    # Group lines by cadence, preserving the canonical Daily..Annual order for a
    # stable round/return ordering. An unknown cadence is rejected up-front.
    by_cadence: dict[str, list] = {}
    for line in results:
        cadence = line.get("cadence")
        if not cadence:
            frappe.throw(_("Each result line needs a cadence."))
        if cadence not in _CADENCE_ORDER:
            frappe.throw(_("Unknown cadence: {0}").format(cadence))
        by_cadence.setdefault(cadence, []).append(line)

    if not by_cadence:
        frappe.throw(_("No result lines to submit."))

    # Outer savepoint: roll back EVERY cadence's round together on any failure.
    outer = "safety_checklist_submit_due_rounds"
    frappe.db.savepoint(outer)
    rounds = []
    total = 0
    try:
        for cadence in _CADENCE_ORDER:
            lines = by_cadence.get(cadence)
            if not lines:
                continue
            round_doc, count = _create_round(
                building, cadence, round_date, lines, is_reinspection=0
            )
            round_doc.reload()
            rounds.append(
                {
                    "cadence": cadence,
                    "safety_round": round_doc.name,
                    "overall_result": round_doc.overall_result,
                }
            )
            total += count
    except Exception:
        frappe.db.rollback(save_point=outer)
        raise
    else:
        frappe.db.release_savepoint(outer)

    # Email the manager OUTSIDE the savepoint-critical path: a mail error must
    # not roll back the submitted rounds (caught + logged inside the helper).
    emailed = _email_round_report(building, round_date, rounds)

    return {"ok": True, "rounds": rounds, "count": total, "emailed": emailed}


def _report_recipients():
    """Resolve the safety-report recipients (configurable, then role fallback).

    Order:

    1. If a ``safety_report_recipient`` field exists and is set on the Habitat
       Settings single, use it. (The field is OPTIONAL — read defensively so
       this never breaks if the schema has not been extended yet.)
    2. Otherwise, the emails of enabled Users holding the Accommodation Manager
       role (``get_users_with_role`` already excludes disabled users).

    Returns a list of addresses (possibly empty).
    """
    try:
        configured = frappe.db.get_single_value(
            "Habitat Settings", "safety_report_recipient"
        )
    except Exception:
        # Field not present on this site's schema yet — fall through to the role.
        configured = None
    if configured:
        return [configured]

    from frappe.utils.user import get_users_with_role

    users = get_users_with_role(_REPORT_ROLE)
    if not users:
        return []
    return frappe.get_all(
        "User",
        filters={"name": ["in", users], "email": ["is", "set"]},
        pluck="email",
    )


def _round_report_html(building, round_date, rounds):
    """Build the report subject + HTML body for the manager email.

    Lists the building, the round date, and per cadence the overall result plus
    the issue tasks (executions that are Poor or Not Done) recorded in that
    cadence's round. Returns ``(subject, message)``.
    """
    subject = _("Safety Round Report: {0} ({1})").format(building, round_date)

    sections = []
    for r in rounds:
        # The issues for this round: executions that scored Poor or Not Done.
        issues = frappe.get_all(
            "Safety Task Execution",
            filters={
                "safety_round": r["safety_round"],
                "execution_status": ["in", ["Poor", "Not Done"]],
            },
            fields=["task", "execution_status", "notes"],
            order_by="execution_status",
        )
        if issues:
            items = "".join(
                "<li>{0} &mdash; <b>{1}</b>{2}</li>".format(
                    frappe.utils.escape_html(it.task or ""),
                    frappe.utils.escape_html(it.execution_status or ""),
                    (": " + frappe.utils.escape_html(it.notes)) if it.notes else "",
                )
                for it in issues
            )
            issues_html = "<ul>{0}</ul>".format(items)
        else:
            issues_html = "<p>{0}</p>".format(_("No issues recorded."))

        sections.append(
            "<h4>{0} &mdash; {1}</h4>{2}".format(
                frappe.utils.escape_html(r["cadence"]),
                frappe.utils.escape_html(r.get("overall_result") or ""),
                issues_html,
            )
        )

    message = "<p>{0}</p>{1}".format(
        _("Safety rounds were recorded for {0} on {1}.").format(building, round_date),
        "".join(sections),
    )
    return subject, message


def _email_round_report(building, round_date, rounds):
    """Email the safety-round report to the manager. Never raises.

    Honours the app email kill-switch (``Habitat Settings`` ->
    ``enable_email_notifications``) and resolves recipients via
    :func:`_report_recipients`. Returns ``True`` only if mail was handed to
    ``frappe.sendmail`` for at least one recipient; any failure (no recipient,
    kill-switch off, or a send error) returns ``False`` so the caller reports
    ``emailed=false`` WITHOUT rolling back the already-submitted rounds.
    """
    if not rounds:
        return False

    from apex_habitat.apex_core.utils.email_gate import email_enabled

    if not email_enabled():
        frappe.logger().info(
            "Email disabled (Habitat Settings): skipped safety round report "
            f"for {building} on {round_date}"
        )
        return False

    recipients = _report_recipients()
    if not recipients:
        return False

    try:
        subject, message = _round_report_html(building, round_date, rounds)
        frappe.sendmail(
            recipients=recipients,
            subject=subject,
            message=message,
            reference_doctype="Safety Round",
            reference_name=rounds[0]["safety_round"],
        )
        return True
    except Exception:
        frappe.log_error(
            title="Safety round report email failed",
            message=frappe.get_traceback(),
        )
        return False
