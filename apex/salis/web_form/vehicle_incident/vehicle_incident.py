# Copyright (c) 2026, afmcoltd
"""Public Vehicle Incident web form.

The insert passes ``ignore_permissions`` because the submitter is a Guest — a driver or passer-by
reporting from the roadside, never a signed-in user — so there is no role to consult, and a
DocPerm here would grant Guest create site-wide. The rate limit stands in for a permission.
"""
import frappe
from frappe import _

from apex.apex_core.utils.rate_limit_identity import rate_limit


def get_context(context):
    """Disables page caching for the Vehicle Incident web form."""
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
    ``incident_type`` is NOT checked here: it is a Select on the DocType, and
    ``_validate_selects`` (frappe/model/base_document.py:892) refuses anything outside
    its options from inside ``insert`` (frappe/model/document.py:310 reaches
    ``_validate`` at :627). ``ignore_permissions`` skips ``check_permission`` at :300
    and nothing else, so the field's own refusal still stands. A second list here would
    silently reject a third incident type the moment one is added to the DocType.
    ``description`` is a Text column with no server length, so its bound is real and
    stays. The controller's validate() guard force-stamps status="Open" and strips any
    disposition fields for a Guest author, so this endpoint only has to bound the free
    text and reject spam.
    """
    if website_field:
        return {"name": None}

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
    doc.insert(ignore_permissions=True)
    return {"name": doc.name}
