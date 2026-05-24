import frappe


def get_context(context):
    context.no_cache = 1


@frappe.whitelist(allow_guest=True, methods=["POST"])
@frappe.rate_limit(key="frappe.request.remote_addr", limit=5, seconds=60)
def submit_resident_request(location_token, request_type, description, contact_number=None):
    """Rate-limited public endpoint for resident request submission.

    Replaces direct Web Form submit for programmatic callers.
    Limit: 5 requests per IP per 60 seconds.
    """
    doc = frappe.get_doc({
        "doctype": "Accommodation Resident Request",
        "location_token": location_token,
        "request_type": request_type,
        "description": description,
        "contact_number": contact_number,
        "source_channel": "QR Web Form",
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return {"name": doc.name, "tracking_code": doc.anonymous_tracking_code}
