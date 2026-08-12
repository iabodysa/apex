"""Permission-scoped Masar operations backed by native Frappe workflows."""

import frappe

PLAN_PAGE_LENGTH = 50


def _require_portal_role():
    from apex.salis.api.route_supervisor import _require_portal_role as require

    return require()


def _validate_page(start, page_length):
    from apex.salis.api.route_supervisor import _validate_position_page

    return _validate_position_page(start, page_length)


def _permission_checked_doc(doctype: str, name: str, ptype: str = "read"):
    doc = frappe.get_doc(doctype, name)
    doc.check_permission(ptype)
    return doc


def _workflow_result(doc) -> dict:
    return {"name": doc.name, "status": doc.status, "docstatus": doc.docstatus}


def _page(doctype, fields, start, page_length, **kwargs):
    start, page_length = _validate_page(start, page_length)
    return frappe.get_list(
        doctype,
        fields=fields,
        limit_start=start,
        limit_page_length=page_length,
        **kwargs,
    )


@frappe.whitelist()
def get_transport_requests(start=0, page_length=PLAN_PAGE_LENGTH):
    """Return permission-scoped transport work through native User Permissions."""
    _require_portal_role()
    return _page(
        "Transport Request",
        [
            "name",
            "request_type",
            "service_line",
            "project",
            "from_location",
            "to_location",
            "pickup_datetime",
            "worker_count",
            "status",
        ],
        start,
        page_length,
        order_by="modified desc, name desc",
    )


@frappe.whitelist()
def get_shift_routes(start=0, page_length=PLAN_PAGE_LENGTH):
    _require_portal_role()
    return _page(
        "Route Assignment",
        ["name", "shift_name", "project", "route_template", "driver", "vehicle"],
        start,
        page_length,
        order_by="modified desc, name desc",
    )


@frappe.whitelist()
def get_route_plans(start=0, page_length=PLAN_PAGE_LENGTH):
    """Return plans through native DocPerm and Project User Permission filters."""
    _require_portal_role()
    return _page(
        "Route Plan",
        [
            "name",
            "route_name",
            "project",
            "shift",
            "driver",
            "vehicle",
            "transport_request",
            "docstatus",
            "modified",
        ],
        start,
        page_length,
        order_by="modified desc, name desc",
    )


@frappe.whitelist()
def get_route_plan(name: str):
    return _permission_checked_doc("Route Plan", name).as_dict(no_nulls=True)


@frappe.whitelist()
def get_dispatch_trips(start=0, page_length=PLAN_PAGE_LENGTH):
    _require_portal_role()
    return _page(
        "Dispatch Trip",
        [
            "name",
            "route_plan",
            "transport_request",
            "shift_name",
            "trip_date",
            "status",
            "driver",
            "vehicle",
        ],
        start,
        page_length,
        order_by="trip_date desc, modified desc, name desc",
    )


@frappe.whitelist()
def get_dispatch_trip(name: str):
    return _permission_checked_doc("Dispatch Trip", name).as_dict(no_nulls=True)


@frappe.whitelist()
def get_movement_history(start=0, page_length=PLAN_PAGE_LENGTH):
    _require_portal_role()
    return _page(
        "Dispatch Trip",
        ["name", "route_plan", "trip_date", "status", "driver", "vehicle"],
        start,
        page_length,
        filters={"status": ["in", ["Completed", "Cancelled"]]},
        order_by="trip_date desc, modified desc, name desc",
    )


def _apply_workflow(doctype, name, action):
    from frappe.model.workflow import apply_workflow

    doc = _permission_checked_doc(doctype, name, "write")
    return _workflow_result(apply_workflow(doc, action) or doc)


@frappe.whitelist(methods=["POST"])
def apply_transport_request_action(name: str, action: str):
    _require_portal_role()
    return _apply_workflow("Transport Request", name, action)


@frappe.whitelist(methods=["POST"])
def apply_dispatch_trip_action(name: str, action: str):
    """Native workflow keeps completion reserved for manager roles."""
    _require_portal_role()
    return _apply_workflow("Dispatch Trip", name, action)
