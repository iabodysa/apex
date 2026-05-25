"""Seed reusable native Frappe Email Templates for repeated outbound messages.

These give staff a consistent, pre-written body when emailing (e.g. from a
document's Email action) and can be referenced by Notifications. Idempotent —
created only if absent, so admins can freely edit them. Bodies are English; admins
localize as needed.
"""

import frappe

_TEMPLATES = [
    {
        "name": "Habitat - Building License Renewal Notice",
        "subject": "Building License {{ doc.license_number }} renewal",
        "response_html": (
            "<p>Dear Sir/Madam,</p>"
            "<p>Building License <b>{{ doc.license_number }}</b> ({{ doc.license_type }}) for "
            "building {{ doc.building }} expires on <b>{{ doc.expiry_date }}</b>.</p>"
            "<p>Please proceed with the renewal at your earliest convenience.</p>"
            "<p>Regards,<br>Accommodation Management</p>"
        ),
    },
    {
        "name": "Habitat - Building Lease Renewal Notice",
        "subject": "Lease renewal for {{ doc.building_name }}",
        "response_html": (
            "<p>Dear Sir/Madam,</p>"
            "<p>The lease for <b>{{ doc.building_name }}</b> ends on <b>{{ doc.lease_end_date }}</b>.</p>"
            "<p>Kindly advise whether the lease will be renewed or terminated.</p>"
            "<p>Regards,<br>Accommodation Management</p>"
        ),
    },
    {
        "name": "Habitat - Resident Request Acknowledgement",
        "subject": "Your request {{ doc.name }} has been received",
        "response_html": (
            "<p>Hello,</p>"
            "<p>We have received your request <b>{{ doc.name }}</b> and it is now being reviewed.</p>"
            "<p>We will follow up with you shortly.</p>"
            "<p>Regards,<br>Accommodation Management</p>"
        ),
    },
]


def seed_email_templates():
    """Create the reusable Email Templates if absent. Safe to re-run."""
    for cfg in _TEMPLATES:
        if frappe.db.exists("Email Template", cfg["name"]):
            continue
        frappe.get_doc({
            "doctype": "Email Template",
            "name": cfg["name"],
            "subject": cfg["subject"],
            "use_html": 1,
            "response_html": cfg["response_html"],
        }).insert(ignore_permissions=True)  # audit-ok
    frappe.db.commit()
