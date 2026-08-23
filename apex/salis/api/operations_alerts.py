# Copyright (c) 2026, afmcoltd
"""Operations-queue action API (read the open queue + act on its rows), for the
operations-control board and the /fleet-os alert drawer.

The fleet operations feature uses this queue; fleet self-service does not.

The queue's rows are Fleet Supervisor assignments (ToDos carrying
reference_type/reference_name) rendered by ``assignment_queue`` in the row shape
the board page JS and the built /fleet-os bundle already speak — those bundles
predate the retired Operations Alert DocType and cannot change here.

Read-only ``get_open_alerts`` lists the open queue, project-scoped server-side
through the SAME ``_permitted_projects`` resolver the dispatch board uses: a
scoped user sees only rows anchored to a vehicle in a permitted project; a row
with no vehicle anchor cannot be safely scoped and is shown to oversight roles
only.

Each write action resolves the queue row back to its ASSIGNED DOCUMENT and
enforces ``write`` on that document — a real grant, not a board-role side door —
and is idempotent. Acknowledge and snooze have no queue-side state to move, so
they permission-check and report no transition rather than fake one. Resolving
closes every open assignment on the document; if the underlying condition still
holds, the next scheduled pass queues it again.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.desk.form import assign_to
from frappe.utils import add_to_date, get_datetime, now_datetime

from apex.apex_core.utils.role_assignment import clear_assignment
from apex.salis.api.assignment_queue import open_queue_rows, queue_ref
from apex.salis.api.dispatch_board import _permitted_projects
from apex.salis.api.enrich import vehicle_driver_titles
from apex.apex_core.doctype.salis_settings.salis_settings import get_salis_int
from apex.salis.tasks import QUEUE_DOCTYPES

SEVERITIES = ["Info", "Warning", "Critical"]

AGING_SETTING = {"Critical": "alert_aging_critical_hours", "Warning": "alert_aging_warning_hours", "Info": "alert_aging_info_hours"}
AGING_DEFAULT = {"Critical": 4, "Warning": 24, "Info": 72}


def _aging_thresholds() -> dict:
    """Per-severity aging cutoffs in hours, from Settings (with sane fallbacks)."""
    return {sev: get_salis_int(AGING_SETTING[sev], AGING_DEFAULT[sev]) for sev in SEVERITIES}


def _scoped_vehicles(unscoped, projects):
    """Vehicle names visible to the caller, or ``None`` when unscoped (no filter).

    A scoped user with no permitted project gets an empty list, so the queue is
    empty rather than leaking another project's rows.
    """
    if unscoped:
        return None
    if not projects:
        return []
    return frappe.get_all(
        "Salis Vehicle",
        filters={"project": ["in", projects]},
        pluck="name",
        limit_page_length=0,
    )


@frappe.whitelist()
def get_open_alerts(project=None, severity=None, since=None):
    """Return the open operations queue for the caller's scope, in the row shape
    the board and the drawer render.

    Read-only and project-scoped server-side: a scoped user only sees rows whose
    vehicle belongs to a project they are permitted, and an optional ``project``
    narrows further but cannot widen past that scope. ``severity`` optionally
    filters to one of Info/Warning/Critical. Each row carries ``_assign`` (the
    open holders) so the client can show the owner and offer the Mine/Unowned
    facet. ``since`` (the user's last-seen time) drives a ``resolved_since``
    count for the delta banner.
    """
    frappe.has_permission("Salis Vehicle", "read", throw=True)
    unscoped, projects = _permitted_projects()

    proj_opts = (
        [p.name for p in frappe.get_all("Project", fields=["name"], order_by="name asc", limit_page_length=0)]
        if unscoped
        else list(projects or [])
    )

    now = now_datetime()

    if project and (unscoped or project in (projects or [])):
        plates = frappe.get_all(
            "Salis Vehicle", filters={"project": project}, pluck="name", limit_page_length=0
        )
    else:
        plates = _scoped_vehicles(unscoped, projects)

    alerts = open_queue_rows()
    if severity in SEVERITIES:
        alerts = [r for r in alerts if r.severity == severity]
    if plates is not None:
        allowed_plates = {p for p in plates if p}
        alerts = [r for r in alerts if r.vehicle and r.vehicle in allowed_plates]
    alerts.sort(key=lambda a: str(a.get("raised_on") or ""), reverse=True)

    vehicle_driver_titles(alerts)

    for a in alerts:
        a["assignees"] = frappe.parse_json(a.get("_assign")) or []
    user = frappe.session.user
    assignee_ids = list({u for a in alerts for u in a["assignees"]})
    name_map = {
        u.name: u.full_name
        for u in frappe.get_all(
            "User", filters={"name": ["in", assignee_ids]}, fields=["name", "full_name"]
        )
    } if assignee_ids else {}

    summary = {"total": len(alerts), "by_severity": {s: 0 for s in SEVERITIES}, "mine": 0, "unowned": 0}
    for a in alerts:
        a["assignee_names"] = [name_map.get(u, u) for u in a["assignees"]]
        a["snooze_until"] = None
        if a.severity in summary["by_severity"]:
            summary["by_severity"][a.severity] += 1
        if user in a["assignees"]:
            summary["mine"] += 1
        if not a["assignees"]:
            summary["unowned"] += 1

    return {
        "alerts": alerts,
        "summary": summary,
        "projects": proj_opts,
        "severities": SEVERITIES,
        "unscoped": unscoped,
        "aging_hours": _aging_thresholds(),
        "server_now": str(now),
        "current_user": user,
        "resolved_since": _resolved_since(since, plates),
    }


def _resolved_since(since, plates) -> int:
    """Count queue rows drained after ``since`` for the delta banner.

    Unscoped callers only: a closed ToDo carries no vehicle column to scope by,
    so a scoped caller gets zero rather than leak another project's activity.
    """
    if not since or plates is not None:
        return 0
    return frappe.db.count(
        "ToDo",
        {
            "reference_type": ["in", list(QUEUE_DOCTYPES)],
            "status": "Closed",
            "modified": [">", since],
        },
    )


def _queue_ref_checked(name):
    """Resolve a queue row id to its reference, enforcing ``write`` on the
    ASSIGNED document — the grant the caller must hold is on the subject document
    itself. Throws when ``name`` is not a queue row (e.g. it drained between the
    board's fetch and the action)."""
    ref = queue_ref(name)
    if not ref:
        frappe.throw(_("Queue row {0} not found (it may have already drained).").format(name))
    frappe.has_permission(ref.reference_type, "write", doc=ref.reference_name, throw=True)
    return ref


def _queue_assignees(ref) -> list:
    """The current open-assignment holders of a queue row's document."""
    return frappe.get_all(
        "ToDo",
        filters={
            "reference_type": ref.reference_type,
            "reference_name": ref.reference_name,
            "status": ["in", ["Open", "Overdue"]],
        },
        pluck="allocated_to",
        distinct=True,
    )


@frappe.whitelist(methods=["POST"])
def acknowledge_alert(name):
    """Acknowledge a queue row: permission-check and report no transition.

    A queue row has no Acknowledged state to move to — the assignment either
    stands or drains — so this validates the caller's grant and reports
    ``acknowledged=False``, which the clients render as a no-op.
    """
    _queue_ref_checked(name)
    return {"ok": True, "name": name, "status": "Open", "acknowledged": False}


@frappe.whitelist(methods=["POST"])
def bulk_acknowledge_alerts(names):
    """Acknowledge several rows in one call (the queue's multi-select).

    Each row is run through ``acknowledge_alert``, which re-checks ``write``
    server-side, so a row the caller may not act on is skipped rather than
    trusted from the client.

    THE RETURNED LIST NAMES THE ROWS THE CALLER WAS ALLOWED TO ACT ON, and is read
    from ``ok`` rather than from ``acknowledged``. A queue row has no state to move to,
    so ``acknowledge_alert`` reports ``acknowledged=False`` for every row by design
    (:197) — reading that key here made the list unconditionally empty, and the desk
    renders its length as "{0} acknowledged" (operations_control.js:900), so an
    operator who acknowledged ten rows was told nought. The two sibling bulk actions
    already read ``ok`` for this reason.
    """
    if isinstance(names, str):
        names = frappe.parse_json(names)
    acknowledged = []
    for name in names or []:
        try:
            if acknowledge_alert(name).get("ok"):
                acknowledged.append(name)
        except frappe.PermissionError:
            continue
    return {"ok": True, "acknowledged": acknowledged}


@frappe.whitelist(methods=["POST"])
def assign_alert(name, user=None):
    """Take ownership of a queue row (or assign it to ``user``) via native
    ``_assign`` on the assigned document itself.

    Delegates to ``frappe.desk.form.assign_to.add``, which creates the ToDo,
    writes the ``_assign`` column and shares the doc. ``user`` defaults to the
    caller (assign-to-me). Permission is re-checked on the referenced document
    (assign_to.add re-checks too). Idempotent: a duplicate assignment is
    swallowed as success.
    """
    target = user or frappe.session.user
    ref = _queue_ref_checked(name)
    assign_to.add({
        "assign_to": [target],
        "doctype": ref.reference_type,
        "name": ref.reference_name,
    })
    return {"ok": True, "name": name, "assignees": _queue_assignees(ref)}


@frappe.whitelist(methods=["POST"])
def unassign_alert(name, user=None):
    """Drop ``user`` (default the caller) from a queue row's document.

    Delegates to ``assign_to.remove``, which closes the ToDo and rewrites
    ``_assign``. Permission is re-checked on the referenced document. No-op
    (still ``ok``) if not assigned.
    """
    target = user or frappe.session.user
    ref = _queue_ref_checked(name)
    try:
        assign_to.remove(ref.reference_type, ref.reference_name, target)
    except Exception:
        pass
    return {"ok": True, "name": name, "assignees": _queue_assignees(ref)}


@frappe.whitelist(methods=["POST"])
def bulk_assign_alerts(names, user=None):
    """Assign several queue rows to ``user`` (default the caller) in one call.

    Each id is run through ``assign_alert``, which re-checks ``write`` per row,
    so a row the caller may not act on is skipped rather than trusted from the
    client. Returns the ids actually assigned.
    """
    if isinstance(names, str):
        names = frappe.parse_json(names)
    assigned = []
    for name in names or []:
        try:
            if assign_alert(name, user=user).get("ok"):
                assigned.append(name)
        except frappe.PermissionError:
            continue
    return {"ok": True, "assigned": assigned}


SNOOZE_PRESETS = {"tomorrow": ("days", 1), "2d": ("days", 2), "1w": ("days", 7)}


def _snooze_target(preset=None, until=None):
    """Resolve a snooze deadline from a named preset or an explicit datetime."""
    if until:
        return get_datetime(until)
    if preset in SNOOZE_PRESETS:
        unit, amount = SNOOZE_PRESETS[preset]
        return add_to_date(now_datetime(), **{unit: amount})
    return None


@frappe.whitelist(methods=["POST"])
def snooze_alert(name, preset=None, until=None):
    """Snooze a queue row: permission-check and report a null snooze.

    A queue row carries no snooze state — the ToDo has no field to hold one —
    so this validates the caller's grant and reports ``snooze_until: None``
    rather than pretend the row will hide.
    """
    _queue_ref_checked(name)
    _snooze_target(preset, until)
    return {"ok": True, "name": name, "snooze_until": None}


@frappe.whitelist(methods=["POST"])
def bulk_snooze_alerts(names, preset=None, until=None):
    """Snooze several rows in one call (the queue's multi-select).

    Each id is run through ``snooze_alert``, which re-checks ``write`` per row,
    so a row the caller may not act on is skipped rather than trusted from the
    client. Returns the ids the check passed for.
    """
    if isinstance(names, str):
        names = frappe.parse_json(names)
    snoozed = []
    for name in names or []:
        try:
            if snooze_alert(name, preset=preset, until=until).get("ok"):
                snoozed.append(name)
        except frappe.PermissionError:
            continue
    return {"ok": True, "snoozed": snoozed}


@frappe.whitelist(methods=["POST"])
def resolve_alert(name, note=None):
    """Resolve a queue row: close every open assignment on its document.

    Permission is re-checked as ``write`` on the referenced document. An audit
    comment lands on the document with the resolver's note. If the underlying
    condition still holds, the next scheduled pass queues the document again.
    """
    reason = (note or _("Resolved by {0}").format(frappe.session.user)).strip()
    ref = _queue_ref_checked(name)
    resolved = bool(clear_assignment(ref.reference_type, ref.reference_name))
    try:
        frappe.get_doc(ref.reference_type, ref.reference_name).add_comment(
            "Info", _("Queue resolved: {0}").format(reason)
        )
    except Exception:
        frappe.log_error(
            message=frappe.get_traceback(),
            title=f"Queue resolve comment failed for {ref.reference_name}"[:140],
        )
    return {"ok": True, "name": name, "status": "Resolved", "resolved": resolved}
