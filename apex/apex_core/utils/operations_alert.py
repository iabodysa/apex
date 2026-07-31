# Copyright (c) 2026, AFMCO and contributors

"""Operations Alert insert helper — the one place that writes the record.

The insert dict + the permission-bypassing system insert + rollback/log-error
block was copy-pasted across the fuel/rental reconciliation engines and the
scheduler notifiers. The DocType IS the native primitive; this only factors out the
repeated system-write boilerplate so a column or default change lives in one
place. Callers keep their own dedupe (the dedupe key is domain-specific).

Leaf utility under apex_core so an engine can import it without coupling to
``salis.tasks``.

THE ALERT SYSTEM IS DELIBERATELY ALIVE. A decommission has been proposed once and
refused on architectural review; the surfaces are listed here so the next reader
weighs the real cost before proposing it again, measured at 2026-07-31:

- one DocType, ``Operations Alert``
- three workspace links: ``salis/salis.json``, ``salis/fleet.json``,
  ``habitat/safety.json``
- one workspace SHORTCUT that carries an open-count stats filter and is the most
  visible surface of the four (``salis/salis.json``, ``{} Open``, red)
- two Number Cards (``unresolved_alerts``, ``median_alert_resolve_days``), one
  Dashboard Chart (``open_alerts_by_type``), one Notification
  (``operations_alert_critical``), and a setting on ``Apex Settings``
- fifteen write sites across seven modules, every one funnelling through this
  helper: habitat maintenance/safety/custody tasks, salis common tasks, the fuel
  and rental engines, and ``system_notify``

Removing the record therefore blanks a card, a chart and a shortcut count before
any writer is touched.
"""

from __future__ import annotations

import frappe

ALERT_DOCTYPE = "Operations Alert"

# [#qqv12a]
_MESSAGE_MAX = 2000

# Every fixed scheduler loop calls this helper, so a bare frappe.db.rollback() here would
# undo the whole run each caller just learned to protect — one failed alert discarding
# every row already written. Own savepoint, distinct from the notify and clearance marks
# because more than one can be live in a single request.
_SAVEPOINT = "apex_operations_alert"


def _project_supervisor_for_vehicle(vehicle: str | None) -> str | None:
    """Resolve the vehicle's project supervisor User, or None.

    Denormalised onto the alert so the Critical-alert Notification can reach the
    specific project's supervisor (its ``receiver_by_document_field`` cannot
    follow the vehicle -> project -> supervisor chain declaratively). Office-scoped
    alerts pass no vehicle and correctly resolve None — the notification condition
    requires ``responsible_supervisor`` and skips them. Never raises: a lookup failure
    must not abort the calling job.
    """
    if not vehicle:
        return None
    try:
        from apex.salis.permissions import _project_supervisor

        project = frappe.db.get_value("Salis Vehicle", vehicle, "project")
        return _project_supervisor(project)
    except Exception:
        return None


def insert_operations_alert(
    alert_type: str,
    severity: str,
    message: str,
    vehicle: str | None = None,
    driver: str | None = None,
) -> str | None:
    """Insert one Open Operations Alert and return its name (None on failure).

    System-written from scheduler jobs, so ``ignore_permissions`` — the DocType
    grants no human write role. ``alert_type``/``severity`` MUST be valid Select
    options (the option sets are closed). Best-effort: a failure rolls back and
    logs but never raises, so the calling job keeps running. Dedupe is the
    caller's job — this always inserts.
    """
    from frappe.utils import now_datetime

    frappe.db.savepoint(_SAVEPOINT)
    try:
        alert = frappe.get_doc(
            {
                "doctype": ALERT_DOCTYPE,
                "alert_type": alert_type,
                "severity": severity,
                "status": "Open",
                "raised_on": now_datetime(),
                "vehicle": vehicle,
                "driver": driver,
                "responsible_supervisor": _project_supervisor_for_vehicle(vehicle),
                "message": (message or "")[:_MESSAGE_MAX],
            }
        )
        alert.insert(ignore_permissions=True)  # audit-ok — scheduler-run alert
        return alert.name
    except Exception:
        frappe.db.rollback(save_point=_SAVEPOINT)
        frappe.log_error(
            message=frappe.get_traceback(),
            title=f"Operations Alert insert failed ({alert_type})"[:140],
        )
        return None
