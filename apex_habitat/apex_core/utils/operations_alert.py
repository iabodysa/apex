# Copyright (c) 2026, AFMCO and contributors

"""Operations Alert insert helper — the one place that writes the record.

The insert dict + the permission-bypassing system insert + rollback/log-error
block was copy-pasted across the fuel/rental reconciliation engines and the
scheduler notifiers. The DocType IS the native primitive; this only factors out the
repeated system-write boilerplate so a column or default change lives in one
place. Callers keep their own dedupe (the dedupe key is domain-specific).

Leaf utility under apex_core so an engine can import it without coupling to
``salis.tasks``.
"""

from __future__ import annotations

import frappe

ALERT_DOCTYPE = "Operations Alert"

# Operations Alert.message is a 2000-char field; clip so a long body never throws.
_MESSAGE_MAX = 2000


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
                "message": (message or "")[:_MESSAGE_MAX],
            }
        )
        alert.insert(ignore_permissions=True)  # audit-ok — scheduler-run alert
        return alert.name
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            message=frappe.get_traceback(),
            title=f"Operations Alert insert failed ({alert_type})"[:140],
        )
        return None
