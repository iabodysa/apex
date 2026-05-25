"""Seed native Frappe Notification records for operational reminders and events.

These replace the custom Habitat Operations Alert for outbound email/alerts:
date-based Notifications fire before/on license and lease expiry; event-based
Notifications fire on new/assigned/submitted documents. Idempotent — created
only if absent, so admins can freely edit or disable them afterwards. All are
created disabled so they only send once an admin enables them and email is
configured.

New (v0.8.3+) notifications keep their user-facing text English-first with
``{{ _("...") }}`` so it is translated through ``translations/ar.csv`` rather
than inlined; the four original expiry notifications keep their pre-existing
inline bilingual bodies (acknowledged technical debt).
"""

import frappe

_NOTIFICATIONS = [
    # --- Date-based expiry reminders (original, inline-bilingual) -------------
    {
        "name": "Habitat - Building License Expiring Soon",
        "subject": "Building License Expiring Soon: {{ doc.name }}",
        "document_type": "Building License",
        "event": "Days Before",
        "date_changed": "expiry_date",
        "days_in_advance": 60,
        "condition": "doc.docstatus == 1 and doc.status in ('Active', 'Expiring Soon')",
        "message": (
            "Building License {{ doc.name }} ({{ doc.license_type }} {{ doc.license_number }}) "
            "for building {{ doc.building }} expires on {{ doc.expiry_date }}. Please start renewal.<br><br>"
            "رخصة المبنى {{ doc.name }} للمبنى {{ doc.building }} تنتهي بتاريخ {{ doc.expiry_date }}. يرجى بدء التجديد."
        ),
        "roles": ["Accommodation Manager", "Resident Supervisor"],
    },
    {
        "name": "Habitat - Building License Expired",
        "subject": "Building License EXPIRED: {{ doc.name }}",
        "document_type": "Building License",
        "event": "Days Before",
        "date_changed": "expiry_date",
        "days_in_advance": 0,
        "condition": "doc.docstatus == 1 and doc.status != 'Revoked'",
        "message": (
            "Building License {{ doc.name }} for building {{ doc.building }} has expired "
            "({{ doc.expiry_date }}).<br><br>"
            "رخصة المبنى {{ doc.name }} للمبنى {{ doc.building }} انتهت بتاريخ {{ doc.expiry_date }}."
        ),
        "roles": ["Accommodation Manager", "System Manager"],
    },
    {
        "name": "Habitat - Building Lease Expiring",
        "subject": "Building Lease Expiring: {{ doc.building_name }}",
        "document_type": "Accommodation Building",
        "event": "Days Before",
        "date_changed": "lease_end_date",
        "days_in_advance": 90,
        "condition": "doc.status == 'Active' and doc.lease_renewal_status in ('Active', 'Under Renewal')",
        "message": (
            "The lease for {{ doc.building_name }} ends on {{ doc.lease_end_date }}. "
            "Please review renewal or termination.<br><br>"
            "ينتهي عقد إيجار {{ doc.building_name }} بتاريخ {{ doc.lease_end_date }}. يرجى مراجعة التجديد أو الإنهاء."
        ),
        "roles": ["Accommodation Manager"],
    },
    {
        "name": "Habitat - Building Lease Expired",
        "subject": "Building Lease EXPIRED: {{ doc.building_name }}",
        "document_type": "Accommodation Building",
        "event": "Days Before",
        "date_changed": "lease_end_date",
        "days_in_advance": 0,
        "condition": "doc.status == 'Active' and doc.lease_renewal_status != 'Terminated'",
        "message": (
            "The lease for {{ doc.building_name }} has ended ({{ doc.lease_end_date }}).<br><br>"
            "انتهى عقد إيجار {{ doc.building_name }} بتاريخ {{ doc.lease_end_date }}."
        ),
        "roles": ["Accommodation Manager", "System Manager"],
    },
    # --- Event-based operational notifications (v0.8.3, English + _()) --------
    {
        "name": "Habitat - Maintenance Request Assigned",
        "subject": "Maintenance Request Assigned: {{ doc.name }}",
        "document_type": "Maintenance Request",
        "event": "Value Change",
        "value_changed": "status",
        "condition": "doc.status == 'Assigned' and doc.assigned_to",
        "message": '{{ _("A maintenance request has been assigned to you") }}: {{ doc.name }}.',
        "recipient_fields": ["assigned_to"],
        "roles": [],
    },
    {
        "name": "Habitat - New Maintenance Request",
        "subject": "New Maintenance Request: {{ doc.name }}",
        "document_type": "Maintenance Request",
        "event": "New",
        "condition": "",
        "message": '{{ _("A new maintenance request awaits triage") }}: {{ doc.name }}.',
        "roles": ["Accommodation Manager", "Resident Supervisor"],
    },
    {
        "name": "Habitat - Resident Request Waiting Evidence",
        "subject": "Resident Request Waiting for Evidence: {{ doc.name }}",
        "document_type": "Accommodation Resident Request",
        "event": "Value Change",
        "value_changed": "status",
        "condition": "doc.status == 'Waiting Evidence'",
        "message": '{{ _("This resident request is waiting for supporting evidence") }}: {{ doc.name }}.',
        "recipient_fields": ["assigned_to"],
        "roles": ["Resident Supervisor"],
    },
    {
        "name": "Habitat - New Resident Request",
        "subject": "New Resident Request: {{ doc.name }}",
        "document_type": "Accommodation Resident Request",
        "event": "New",
        "condition": "",
        "message": '{{ _("A new resident request has been received and awaits triage") }}: {{ doc.name }}.',
        "roles": ["Resident Supervisor", "Accommodation Manager"],
    },
    {
        "name": "Habitat - Temporary Stay Ending",
        "subject": "Temporary Stay Ending: {{ doc.name }}",
        "document_type": "Accommodation Assignment",
        "event": "Days Before",
        "date_changed": "expected_checkout_date",
        "days_in_advance": 2,
        "condition": "doc.docstatus == 1 and doc.stay_type == 'Temporary' and not doc.check_out_date",
        "message": '{{ _("This temporary stay is ending soon — please arrange check-out") }}: {{ doc.name }} ({{ doc.expected_checkout_date }}).',
        "roles": ["Resident Supervisor", "Accommodation Manager"],
    },
    {
        "name": "Habitat - Idle Resident Reported",
        "subject": "Idle Resident Reported: {{ doc.name }}",
        "document_type": "Idle Resident Report",
        "event": "New",
        "condition": "",
        "message": '{{ _("An idle resident has been reported and routed to the responsible department") }}: {{ doc.name }} ({{ doc.responsible_department }}).',
        "roles": ["Accommodation Manager", "HR Manager", "System Manager"],
    },
    {
        "name": "Habitat - Custody Damage Assessment Created",
        "subject": "Custody Damage Assessment Submitted: {{ doc.name }}",
        "document_type": "Custody Damage Assessment",
        "event": "Submit",
        "condition": "doc.docstatus == 1",
        "message": '{{ _("A custody damage assessment has been submitted and may create a salary deduction") }}: {{ doc.name }}.',
        "roles": ["Finance Manager", "Accommodation Manager"],
    },
]


def seed_operational_notifications():
    """Create the operational Notification records if absent. Disabled by default
    so they only send once an admin enables them and email is configured."""
    for cfg in _NOTIFICATIONS:
        if frappe.db.exists("Notification", cfg["name"]):
            continue
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
            "module": "Habitat",
        })
        for role in cfg.get("roles", []):
            doc.append("recipients", {"receiver_by_role": role})
        for fieldname in cfg.get("recipient_fields", []):
            doc.append("recipients", {"receiver_by_document_field": fieldname})
        doc.insert(ignore_permissions=True)  # audit-ok
    frappe.db.commit()
