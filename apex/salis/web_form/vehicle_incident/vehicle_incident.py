# Copyright (c) 2026, AFMCO and contributors
import frappe
from frappe import _

from apex.apex_core.utils.rate_limit_identity import rate_limit


def get_context(context):
    context.no_cache = 1


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=5, seconds=60)
def submit_vehicle_incident(
    incident_type,
    vehicle,
    incident_date,
    description,
    location=None,
    report_number=None,
    reported_by=None,
    website_field=None,
):
    """Rate-limited public endpoint for anonymous Vehicle Incident reporting.

    Limit: 5 requests per IP per 60 seconds (tighter than the stock web-form
    accept() 10/60). Creates a docstatus-0 draft only; a supervisor reviews and
    submits it, so the Theft on_submit side-effect (stop vehicle / clear driver)
    never fires on a guest submission.

    - ``website_field`` is a honeypot; any non-empty value is silently discarded.
    - ``incident_type`` is restricted to the form's two safe options.
    The controller's validate() guard force-stamps status="Open" and strips any
    disposition fields for a Guest author, so this endpoint only has to bound the
    free-text inputs and reject spam.
    """
    if website_field:
        return {"name": None}

    if incident_type not in ("Accident", "Theft"):
        frappe.throw(_("Invalid incident type."))

    if len(description or "") > 4000:
        frappe.throw(_("Description is too long. Please keep it under 4000 characters."))

    doc = frappe.get_doc({
        "doctype": "Vehicle Incident",
        "incident_type": incident_type,
        "vehicle": vehicle,
        "incident_date": incident_date,
        "description": description,
        "location": location,
        "report_number": report_number,
        "reported_by": reported_by,
        "status": "Open",
    })
    doc.insert(ignore_permissions=True)  # audit-ok — guest web-form intake, rate-limited + honeypot-guarded; draft only
    return {"name": doc.name}
