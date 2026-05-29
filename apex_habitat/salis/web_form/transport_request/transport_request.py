import frappe
from frappe import _
from frappe.rate_limiter import rate_limit


def get_context(context):
    context.no_cache = 1


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(key="frappe.request.remote_addr", limit=5, seconds=60)
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
    """Rate-limited public endpoint for anonymous Transport Request submission.

    Limit: 5 requests per IP per 60 seconds.

    - ``website_field`` is a honeypot; any non-empty value is silently discarded.
    - ``passenger_count`` is clamped server-side to 1..50.
    - ``purpose`` is capped at 2000 characters.
    The controller (``before_insert``) tags ``source_channel='Web QR'`` and
    generates the ``anonymous_tracking_code`` for guest submissions.
    """
    # Honeypot — silently succeed but discard bot submissions.
    if website_field:
        return {"name": None, "tracking_code": None}

    # Server-side length cap on free text.
    if len(purpose or "") > 2000:
        frappe.throw(_("Purpose is too long. Please keep it under 2000 characters."))

    # Server-side passenger clamp.
    try:
        count = int(passenger_count)
    except (TypeError, ValueError):
        count = 1
    if count < 1:
        count = 1
    elif count > 50:
        count = 50

    # A guest QR submission is a lightweight ad-hoc request. Classify it as a
    # Representatives "Administrative Trip" (destination = the stated drop-off) so
    # it satisfies the service_line -> request_type guard; Operations re-classifies
    # to a Workers shuttle (and fills Building/Project) during triage if needed.
    doc = frappe.get_doc({
        "doctype": "Transport Request",
        "service_line": "Representatives",
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
    doc.insert(ignore_permissions=True)  # audit-ok
    frappe.db.commit()
    return {"name": doc.name, "tracking_code": doc.anonymous_tracking_code}
