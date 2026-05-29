"""Seed native Frappe Notification records for Salis (movement/fleet) operations.

Mirrors ``habitat/notifications_seed.py``: these are date-based and event-based
Notifications that surface the movement department's recurring risk events:

- vehicle compliance (Istimara / insurance / inspection) expiring soon
- a driver blocked at clearance who must be cleared before redeployment
- a fuel request left pending past its approval window
- a large worker-move transport request that needs management escalation

Each is idempotent (created only if absent, so admins can freely edit or disable
them afterwards) and existence-guarded on its ``document_type`` so a partially
installed module never raises a LinkValidationError or aborts migrate. All are
created **disabled** so they only send once an admin enables them and email is
configured.

User-facing text is English-first with ``{{ _("...") }}`` so it is translated
through ``translations/ar.csv`` rather than inlined. Fieldnames are verified
against ``salis/doctype/*/*.json``:

- Salis Vehicle: ``next_expiry_date`` (earliest compliance expiry), ``status``.
- Driver Clearance: ``status`` options Open|In Progress|Cleared|Blocked.
- Fuel Request: ``status`` options Pending|Approved|Done|Failed|Cancelled,
  ``request_date``.
- Transport Request: ``status`` New|Validated|Approved|Scheduled|Fulfilled|
  Rejected|Cancelled, ``worker_count``, ``request_type``.
"""

import frappe

_NOTIFICATIONS = [
    # --- Date-based: vehicle compliance expiry reminder -----------------------
    {
        "name": "Salis - Vehicle Compliance Expiring Soon",
        "subject": "Vehicle Compliance Expiring Soon: {{ doc.name }}",
        "document_type": "Salis Vehicle",
        "event": "Days Before",
        "date_changed": "next_expiry_date",
        "days_in_advance": 30,
        "condition": "doc.status != 'Stopped'",
        "message": '{{ _("A vehicle compliance document is expiring soon — please start renewal") }}: {{ doc.name }} ({{ doc.next_expiry_date }}).',
        "roles": ["Fleet Manager", "Fleet Supervisor", "Government Relations Officer"],
    },
    # --- Event-based: driver blocked at clearance -----------------------------
    {
        "name": "Salis - Blocked Driver Clearance",
        "subject": "Driver Clearance Blocked: {{ doc.name }}",
        "document_type": "Driver Clearance",
        "event": "Value Change",
        "value_changed": "status",
        "condition": "doc.status == 'Blocked'",
        "message": '{{ _("A driver clearance is blocked and must be resolved before the driver is redeployed") }}: {{ doc.name }} ({{ doc.driver }}).',
        "roles": ["Fleet Manager", "Fleet Supervisor"],
    },
    # --- Event-based: fuel request stuck pending ------------------------------
    {
        "name": "Salis - Overdue Fuel Request",
        "subject": "Fuel Request Awaiting Approval: {{ doc.name }}",
        "document_type": "Fuel Request",
        "event": "Days After",
        "date_changed": "request_date",
        "days_in_advance": 2,
        "condition": "doc.docstatus == 1 and doc.status == 'Pending'",
        "message": '{{ _("This fuel request has been pending approval for too long") }}: {{ doc.name }} ({{ doc.vehicle }}).',
        "roles": ["Fleet Manager", "Fleet Supervisor"],
    },
    # --- Event-based: large worker move needs escalation ----------------------
    {
        "name": "Salis - Large Worker Move Escalation",
        "subject": "Large Worker Move Needs Escalation: {{ doc.name }}",
        "document_type": "Transport Request",
        "event": "Value Change",
        "value_changed": "status",
        "condition": "doc.worker_count and doc.worker_count >= 20 and doc.status in ('New', 'Validated')",
        "message": '{{ _("A large worker-transport request needs management escalation") }}: {{ doc.name }} ({{ doc.worker_count }} {{ _("workers") }}).',
        "roles": ["Fleet Manager"],
    },
]


def seed_salis_notifications():
    """Create the Salis operational Notification records if absent. Disabled by
    default so they only send once an admin enables them and email is configured.
    Existence-guarded on document_type and idempotent — safe to re-run."""
    for cfg in _NOTIFICATIONS:
        if frappe.db.exists("Notification", cfg["name"]):
            continue
        if not frappe.db.exists("DocType", cfg["document_type"]):
            continue  # module not migrated yet — skip silently
        doc = frappe.get_doc({
            "doctype": "Notification",
            "name": cfg["name"],
            "subject": cfg["subject"],
            "document_type": cfg["document_type"],
            "channel": "Email",
            "event": cfg["event"],
            "date_changed": cfg.get("date_changed"),
            "days_in_advance": cfg.get("days_in_advance", 0),
            "value_changed": cfg.get("value_changed"),
            "condition": cfg.get("condition") or "",
            "message": cfg["message"],
            "enabled": 0,
            "is_standard": 0,
            "module": "Salis",
        })
        for role in cfg.get("roles", []):
            # Skip roles absent on this site so the seed never fails on recipient
            # link validation (core/HRMS roles may not be present everywhere).
            if frappe.db.exists("Role", role):
                doc.append("recipients", {"receiver_by_role": role})
        for fieldname in cfg.get("recipient_fields", []):
            doc.append("recipients", {"receiver_by_document_field": fieldname})
        doc.insert(ignore_permissions=True)  # audit-ok
    frappe.db.commit()
