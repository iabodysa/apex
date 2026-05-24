"""Seed native Frappe Notification records for operational reminders.

These replace the custom Habitat Operations Alert for outbound email: date-based
Notifications fire declaratively before/on license and lease expiry. Idempotent —
created only if absent, so admins can freely edit or disable them afterwards.
"""

import frappe

_NOTIFICATIONS = [
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
            "date_changed": cfg["date_changed"],
            "days_in_advance": cfg["days_in_advance"],
            "condition": cfg["condition"],
            "message": cfg["message"],
            "enabled": 0,
            "is_standard": 0,
            "module": "Habitat",
        })
        for role in cfg["roles"]:
            doc.append("recipients", {"receiver_by_role": role})
        doc.insert(ignore_permissions=True)  # audit-ok
    frappe.db.commit()
