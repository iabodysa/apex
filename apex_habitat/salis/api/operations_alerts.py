"""Operations Alert action API (read the open queue + advance the status ladder),
for the operations-control board and the /fleet alert drawer.

Read-only ``get_open_alerts`` lists the Open/Acknowledged queue, project-scoped
server-side through the SAME ``_permitted_projects`` resolver the dispatch board
and operations-control reader use. An Operations Alert has no own ``project``
column, so scope is derived from the alert's vehicle project: a scoped user sees
only alerts anchored to a vehicle in a permitted project; an alert with no
vehicle anchor cannot be safely scoped and is shown to oversight roles only.

The two write actions advance the ladder Open -> Acknowledged -> Resolved. Each
re-checks ``frappe.has_permission('Operations Alert', 'write')`` on top of the
DocPerm grant (the board role alone does not authorise the write) and is
idempotent. ``resolve_alert`` reuses the ``tasks._resolve_alert`` helper so the
manual and the periodic/auto resolvers stamp ``resolved_on`` + ``resolution_note``
and drop the audit comment identically.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.desk.form import assign_to
from frappe.utils import add_to_date, get_datetime, now_datetime

from apex_habitat.salis.api.dispatch_board import _permitted_projects
from apex_habitat.salis.tasks import ALERT_DOCTYPE, _resolve_alert, _settings_int

OPEN_STATUSES = ["Open", "Acknowledged"]
SEVERITIES = ["Info", "Warning", "Critical"]

# Per-severity "open too long" thresholds (hours). Read from Salis Settings so ops
# can tune them; the field may be absent, in which case _settings_int returns the
# default — so this is configurable without a schema change to the alert.
AGING_SETTING = {"Critical": "alert_aging_critical_hours", "Warning": "alert_aging_warning_hours", "Info": "alert_aging_info_hours"}
AGING_DEFAULT = {"Critical": 4, "Warning": 24, "Info": 72}


def _aging_thresholds() -> dict:
    """Per-severity aging cutoffs in hours, from Settings (with sane fallbacks)."""
    return {sev: _settings_int(AGING_SETTING[sev], AGING_DEFAULT[sev]) for sev in SEVERITIES}


def _scoped_vehicles(unscoped, projects):
    """Vehicle names visible to the caller, or ``None`` when unscoped (no filter).

    A scoped user with no permitted project gets an empty list, so the queue is
    empty rather than leaking another project's alerts.
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
    """Return the Open/Acknowledged Operations Alert queue for the caller's scope.

    Read-only and project-scoped server-side: a scoped user only sees alerts whose
    vehicle belongs to a project they are permitted, and an optional ``project``
    narrows further but cannot widen past that scope. ``severity`` optionally
    filters to one of Info/Warning/Critical. Snoozed rows (``snooze_until`` still
    in the future) are excluded so a deferred alert disappears until its moment
    passes. Each row carries native ``_assign`` (the assignment column) so the
    client can show the owner and offer the Mine/Unowned facet. ``since`` (the
    user's last-seen time) drives a ``resolved_since`` count for the delta banner.
    """
    frappe.has_permission(ALERT_DOCTYPE, "read", throw=True)
    unscoped, projects = _permitted_projects()

    proj_opts = (
        [p.name for p in frappe.get_all("Project", fields=["name"], order_by="name asc", limit_page_length=0)]
        if unscoped
        else list(projects or [])
    )

    now = now_datetime()
    filters = {"status": ["in", OPEN_STATUSES]}
    if severity in SEVERITIES:
        filters["severity"] = severity
    # Exclude still-snoozed rows: keep only alerts whose snooze has lapsed or was
    # never set. A list-of-lists or_filter is the native way to reference the same
    # column twice (NULL OR past) — a dict would collapse the duplicate key.
    or_filters = [
        ["Operations Alert", "snooze_until", "is", "not set"],
        ["Operations Alert", "snooze_until", "<=", now],
    ]

    if project and (unscoped or project in (projects or [])):
        # Narrow to the vehicles of a single in-scope project.
        plates = frappe.get_all(
            "Salis Vehicle", filters={"project": project}, pluck="name", limit_page_length=0
        )
        filters["vehicle"] = ["in", plates or [None]]
    else:
        plates = _scoped_vehicles(unscoped, projects)
        if plates is not None:
            # A vehicle-less alert has no project anchor, so a scoped user never sees it.
            filters["vehicle"] = ["in", plates or [None]]

    alerts = frappe.get_all(
        ALERT_DOCTYPE,
        filters=filters,
        or_filters=or_filters,
        fields=[
            "name", "alert_type", "severity", "status",
            "vehicle", "driver", "message", "raised_on", "snooze_until", "_assign",
        ],
        order_by="raised_on desc",
        limit_page_length=0,
    )

    veh_ids = list({a.vehicle for a in alerts if a.get("vehicle")})
    plates_map = {}
    if veh_ids:
        plates_map = {
            v.name: v.plate_number
            for v in frappe.get_all(
                "Salis Vehicle", filters={"name": ["in", veh_ids]}, fields=["name", "plate_number"]
            )
        }
    drv_ids = list({a.driver for a in alerts if a.get("driver")})
    drv_map = {}
    if drv_ids:
        drv_map = {
            d.name: d.full_name
            for d in frappe.get_all(
                "Salis Driver", filters={"name": ["in", drv_ids]}, fields=["name", "full_name"]
            )
        }

    # Parse native _assign (a JSON list of users) once per row into an assignees list.
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
        a["plate_number"] = plates_map.get(a.get("vehicle"))
        a["driver_name"] = drv_map.get(a.get("driver"))
        a["assignee_names"] = [name_map.get(u, u) for u in a["assignees"]]
        a["snooze_until"] = str(a["snooze_until"]) if a.get("snooze_until") else None
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
        # Per-severity aging cutoffs (hours) + the server clock, so the client can
        # flag a row open past its threshold without trusting the browser's time.
        "aging_hours": _aging_thresholds(),
        "server_now": str(now),
        "current_user": user,
        # Alerts resolved since the user's last visit, for the delta banner. Scoped
        # by the SAME vehicle filter as the queue (reuse filters['vehicle']).
        "resolved_since": _resolved_since(since, filters.get("vehicle")),
    }


def _resolved_since(since, vehicle_filter) -> int:
    """Count alerts resolved after ``since``, under the same vehicle scope as the queue."""
    if not since:
        return 0
    resolved_filters = {"status": "Resolved", "resolved_on": [">", since]}
    if vehicle_filter is not None:
        resolved_filters["vehicle"] = vehicle_filter
    return frappe.db.count(ALERT_DOCTYPE, resolved_filters)


@frappe.whitelist(methods=["POST"])
def acknowledge_alert(name):
    """Move an Open Operations Alert to Acknowledged.

    Re-checks ``write`` on the specific alert. Idempotent: an alert that is already
    Acknowledged or Resolved is left untouched (no status flip, no duplicate
    comment) and reports ``acknowledged=False``.
    """
    frappe.has_permission(ALERT_DOCTYPE, "write", doc=name, throw=True)
    current = frappe.db.get_value(ALERT_DOCTYPE, name, "status")
    if current != "Open":
        return {"ok": True, "name": name, "status": current, "acknowledged": False}

    frappe.db.set_value(ALERT_DOCTYPE, name, "status", "Acknowledged", update_modified=True)
    try:
        frappe.get_doc(ALERT_DOCTYPE, name).add_comment(
            "Info", _("Acknowledged by {0}").format(frappe.session.user)
        )
    except Exception:
        frappe.log_error(
            message=frappe.get_traceback(),
            title=f"Alert acknowledge comment failed for {name}"[:140],
        )
    return {"ok": True, "name": name, "status": "Acknowledged", "acknowledged": True}


@frappe.whitelist(methods=["POST"])
def bulk_acknowledge_alerts(names):
    """Acknowledge several Open alerts in one call (the queue's multi-select).

    ``names`` is a JSON list (or list) of Operations Alert ids. Each row is run
    through ``acknowledge_alert``, which re-checks ``write`` per alert server-side,
    so a row the caller may not act on is skipped rather than trusted from the
    client. Idempotent: an already-acknowledged/resolved row is left untouched.
    Returns the ids that actually moved Open -> Acknowledged.
    """
    if isinstance(names, str):
        names = frappe.parse_json(names)
    acknowledged = []
    for name in names or []:
        try:
            if acknowledge_alert(name).get("acknowledged"):
                acknowledged.append(name)
        except frappe.PermissionError:
            # Skip a row the caller cannot act on; don't abort the whole batch.
            continue
    return {"ok": True, "acknowledged": acknowledged}


@frappe.whitelist(methods=["POST"])
def assign_alert(name, user=None):
    """Take ownership of an alert (or assign it to ``user``) via native ``_assign``.

    Delegates to ``frappe.desk.form.assign_to.add``, which creates the ToDo, writes
    the ``_assign`` column and shares the doc — so the alert appears in the owner's
    ToDo list with no custom field. ``user`` defaults to the caller (assign-to-me).
    Permission is re-checked on the specific alert (assign_to.add re-checks too).
    Idempotent: a duplicate assignment is swallowed as success.
    """
    frappe.has_permission(ALERT_DOCTYPE, "write", doc=name, throw=True)
    target = user or frappe.session.user
    assign_to.add({"assign_to": [target], "doctype": ALERT_DOCTYPE, "name": name})
    return {"ok": True, "name": name, "assignees": _assignees(name)}


@frappe.whitelist(methods=["POST"])
def unassign_alert(name, user=None):
    """Drop ``user`` (default the caller) from an alert's native ``_assign``.

    Delegates to ``assign_to.remove``, which closes the ToDo and rewrites ``_assign``.
    Permission is re-checked on the alert. No-op (still ``ok``) if not assigned.
    """
    frappe.has_permission(ALERT_DOCTYPE, "write", doc=name, throw=True)
    target = user or frappe.session.user
    try:
        assign_to.remove(ALERT_DOCTYPE, name, target)
    except Exception:
        # Removing an assignment that isn't there must not error the caller.
        pass
    return {"ok": True, "name": name, "assignees": _assignees(name)}


@frappe.whitelist(methods=["POST"])
def bulk_assign_alerts(names, user=None):
    """Assign several alerts to ``user`` (default the caller) in one call.

    Each id is run through ``assign_alert``, which re-checks ``write`` per alert, so
    a row the caller may not act on is skipped rather than trusted from the client.
    Returns the ids actually assigned.
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


def _assignees(name) -> list:
    """The current native-_assign user list for an alert (post-mutation read-back)."""
    return frappe.parse_json(frappe.db.get_value(ALERT_DOCTYPE, name, "_assign")) or []


# Named snooze windows the UI offers, mapped to (unit, amount) for add_to_date.
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
    """Hide an alert from the queue until a deadline by stamping ``snooze_until``.

    The deadline comes from a named ``preset`` (tomorrow / 2d / 1w) or an explicit
    ``until`` datetime. The queue reader excludes rows whose ``snooze_until`` is
    still in the future, so the alert disappears now and reappears once it lapses.
    Permission is re-checked on the alert. Pass an empty ``until`` with no preset to
    clear a snooze.
    """
    frappe.has_permission(ALERT_DOCTYPE, "write", doc=name, throw=True)
    target = _snooze_target(preset, until)
    frappe.db.set_value(ALERT_DOCTYPE, name, "snooze_until", target, update_modified=True)
    try:
        when = _("until {0}").format(target) if target else _("cleared")
        frappe.get_doc(ALERT_DOCTYPE, name).add_comment(
            "Info", _("Snoozed by {0} ({1})").format(frappe.session.user, when)
        )
    except Exception:
        frappe.log_error(
            message=frappe.get_traceback(),
            title=f"Alert snooze comment failed for {name}"[:140],
        )
    return {"ok": True, "name": name, "snooze_until": str(target) if target else None}


@frappe.whitelist(methods=["POST"])
def bulk_snooze_alerts(names, preset=None, until=None):
    """Snooze several alerts in one call (the queue's multi-select).

    Each id is run through ``snooze_alert``, which re-checks ``write`` per alert, so
    a row the caller may not act on is skipped rather than trusted from the client.
    Returns the ids actually snoozed.
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
    """Resolve an Operations Alert, stamping ``resolved_on`` + ``resolution_note``.

    Re-checks ``write`` on the specific alert, then delegates the transition to the
    shared ``_resolve_alert`` helper so a manual resolve is identical to the
    periodic/auto resolver (idempotent; an already-Resolved alert is a no-op).
    """
    frappe.has_permission(ALERT_DOCTYPE, "write", doc=name, throw=True)
    reason = (note or _("Resolved by {0}").format(frappe.session.user)).strip()
    resolved = _resolve_alert(name, reason)
    return {
        "ok": True,
        "name": name,
        "status": frappe.db.get_value(ALERT_DOCTYPE, name, "status"),
        "resolved": resolved,
    }


def _median(values):
    """Median of a non-empty numeric list (mean of the two middle items on even n)."""
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


@frappe.whitelist()
def get_alert_median_resolve_days(filters=None):
    """Custom Number Card: median days from ``raised_on`` to ``resolved_on``.

    The resolution-latency twin of the open-alert queue: it measures how long
    Resolved alerts took to close. Scoped through the SAME ``_permitted_projects``
    resolver as the queue, so a scoped user's median covers only alerts on a
    vehicle in a permitted project; a vehicle-less alert has no project anchor and
    is excluded for scoped users (oversight roles see all). Only alerts with both
    timestamps set are counted. ``filters`` is accepted and ignored (the widget
    always passes it). Returns ``{value, fieldtype}`` per the Custom card contract.
    """
    frappe.has_permission(ALERT_DOCTYPE, "read", throw=True)
    unscoped, projects = _permitted_projects()

    alert_filters = {
        "status": "Resolved",
        "raised_on": ["is", "set"],
        "resolved_on": ["is", "set"],
    }
    if not unscoped:
        plates = _scoped_vehicles(unscoped, projects)
        # A vehicle-less alert has no project anchor, so a scoped user never sees it.
        alert_filters["vehicle"] = ["in", plates or [None]]

    rows = frappe.get_all(
        ALERT_DOCTYPE,
        filters=alert_filters,
        fields=["raised_on", "resolved_on"],
        limit_page_length=0,
    )
    spans = [
        (r.resolved_on - r.raised_on).total_seconds() / 86400.0
        for r in rows
        if r.resolved_on and r.raised_on
    ]
    value = round(_median(spans), 2) if spans else 0
    return {"value": value, "fieldtype": "Float"}
