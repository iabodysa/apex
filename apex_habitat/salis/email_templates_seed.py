"""Seed reusable native Frappe Email Templates for repeated Salis outbound messages.

Mirrors ``habitat/email_templates_seed.py``: these give staff a consistent,
pre-written body when emailing (e.g. from a document's Email action) and can be
referenced by Notifications. Idempotent — created only if absent, so admins can
freely edit them. Bodies are English; admins localize as needed.

The ``{{ doc.* }}`` variables are verified against the real DocType fields in
``salis/doctype/*/*.json``:

- Driver Clearance: ``driver``, ``clearance_reason``, ``status`` (Cleared = issued).
- Rental Settlement: ``rental_office``, ``period_month``, ``accrued_total``,
  ``claimed_total``, ``variance``, ``status``.
- Transport Request: ``requester_name``, ``request_type``, ``pickup_datetime``,
  ``status``.
"""

import frappe

_TEMPLATES = [
    {
        "name": "Salis - Driver Clearance Issued",
        "subject": "Driver clearance {{ doc.name }} issued",
        "response_html": (
            "<p>Dear Sir/Madam,</p>"
            "<p>Driver clearance <b>{{ doc.name }}</b> for driver <b>{{ doc.driver }}</b> "
            "({{ doc.clearance_reason }}) has been issued with status <b>{{ doc.status }}</b>.</p>"
            "<p>The driver may be redeployed once all custody, fuel chip, and vehicle items are returned.</p>"
            "<p>Regards,<br>Fleet Management</p>"
        ),
    },
    {
        "name": "Salis - Rental Settlement Statement",
        "subject": "Rental settlement {{ doc.name }} for {{ doc.period_month }}",
        "response_html": (
            "<p>Dear Sir/Madam,</p>"
            "<p>Please find the rental settlement statement for office <b>{{ doc.rental_office }}</b> "
            "covering <b>{{ doc.period_month }}</b>.</p>"
            "<p>Accrued total: <b>{{ doc.accrued_total }}</b><br>"
            "Claimed total: <b>{{ doc.claimed_total }}</b><br>"
            "Variance: <b>{{ doc.variance }}</b><br>"
            "Status: <b>{{ doc.status }}</b></p>"
            "<p>Kindly review and confirm at your earliest convenience.</p>"
            "<p>Regards,<br>Fleet Management</p>"
        ),
    },
    {
        "name": "Salis - Transport Request Acknowledgement",
        "subject": "Your transport request {{ doc.name }} has been received",
        "response_html": (
            "<p>Hello {{ doc.requester_name }},</p>"
            "<p>We have received your transport request <b>{{ doc.name }}</b> "
            "({{ doc.request_type }}) and it is now being reviewed.</p>"
            "<p>Requested pickup: <b>{{ doc.pickup_datetime }}</b><br>"
            "Current status: <b>{{ doc.status }}</b></p>"
            "<p>We will follow up with you shortly.</p>"
            "<p>Regards,<br>Fleet Management</p>"
        ),
    },
]


def seed_salis_email_templates():
    """Create the reusable Salis Email Templates if absent. Safe to re-run."""
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
