# Copyright (c) 2026, afmcoltd
import frappe
from frappe import _

from apex.apex_core.utils.rate_limit_identity import rate_limit


def get_context(context):
    context.no_cache = 1


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=5, seconds=60)
def submit_transport_request(
    from_location,
    to_location,
    pickup_datetime,
    passenger_count,
    purpose,
    requester_name=None,
    mobile_number=None,
    site_token=None,
    website_field=None,
):
    if website_field:
        return {"name": None, "tracking_code": None}

    if len(purpose or "") > 2000:
        frappe.throw(_("Purpose is too long. Please keep it under 2000 characters."))

    try:
        count = int(passenger_count)
    except (TypeError, ValueError):
        count = 1
    if count < 1:
        count = 1
    elif count > 50:
        count = 50

    doc = frappe.get_doc({
        "doctype": "Transport Request",
        "service_line": "Administrative Trip",
        "request_type": "Administrative Trip / Document Signing",
        "destination": to_location,
        "requester_name": requester_name,
        "mobile_number": mobile_number,
        "site_token": site_token,
        "from_location": from_location,
        "to_location": to_location,
        "pickup_datetime": pickup_datetime,
        "passenger_count": count,
        "purpose": purpose,
        "source_channel": "Web QR",
        "status": "New",
    })
    doc.insert(ignore_permissions=True)
    return {"name": doc.name, "tracking_code": doc.anonymous_tracking_code}
