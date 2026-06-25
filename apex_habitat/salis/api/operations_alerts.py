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

from apex_habitat.salis.api.dispatch_board import _permitted_projects
from apex_habitat.salis.tasks import ALERT_DOCTYPE, _resolve_alert

OPEN_STATUSES = ["Open", "Acknowledged"]
SEVERITIES = ["Info", "Warning", "Critical"]


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
def get_open_alerts(project=None, severity=None):
    """Return the Open/Acknowledged Operations Alert queue for the caller's scope.

    Read-only and project-scoped server-side: a scoped user only sees alerts whose
    vehicle belongs to a project they are permitted, and an optional ``project``
    narrows further but cannot widen past that scope. ``severity`` optionally
    filters to one of Info/Warning/Critical.
    """
    frappe.has_permission(ALERT_DOCTYPE, "read", throw=True)
    unscoped, projects = _permitted_projects()

    proj_opts = (
        [p.name for p in frappe.get_all("Project", fields=["name"], order_by="name asc", limit_page_length=0)]
        if unscoped
        else list(projects or [])
    )

    filters = {"status": ["in", OPEN_STATUSES]}
    if severity in SEVERITIES:
        filters["severity"] = severity

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
        fields=[
            "name", "alert_type", "severity", "status",
            "vehicle", "driver", "message", "raised_on",
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

    summary = {"total": len(alerts), "by_severity": {s: 0 for s in SEVERITIES}}
    for a in alerts:
        a["plate_number"] = plates_map.get(a.get("vehicle"))
        a["driver_name"] = drv_map.get(a.get("driver"))
        if a.severity in summary["by_severity"]:
            summary["by_severity"][a.severity] += 1

    return {
        "alerts": alerts,
        "summary": summary,
        "projects": proj_opts,
        "severities": SEVERITIES,
        "unscoped": unscoped,
    }


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
