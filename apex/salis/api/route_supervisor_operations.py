"""Permission-scoped Masar operations backed by native Frappe workflows."""

import frappe

PLAN_PAGE_LENGTH = 50

_SERVICE_LINE_LABELS = {
    "Site Transport": "نقل العاملين",
    "Inter-City Relocation": "نقل بين المدن",
    "Airport Transfer": "نقل المطار",
    "Hospital Transfer": "نقل المستشفى",
}


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


def _transport_request_title(row) -> str:
    origin = (row.get("from_location") or "").strip()
    destination = (row.get("to_location") or "").strip()
    if origin and destination:
        return f"{origin} إلى {destination}"
    if origin or destination:
        return origin or destination
    requester = (row.get("requester_name") or "").strip()
    if requester:
        return requester
    return _SERVICE_LINE_LABELS.get(row.get("service_line"), "طلب نقل")


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
    rows = _page(
        "Transport Request",
        [
            "name",
            "requester_name",
            "request_type",
            "service_line",
            "project",
            "project.project_name as project_label",
            "from_location",
            "to_location",
            "pickup_datetime",
            "worker_count",
            "status",
        ],
        start,
        page_length,
        order_by=(
            "`tabTransport Request`.modified desc, "
            "`tabTransport Request`.name desc"
        ),
    )
    for row in rows:
        row["display_title"] = _transport_request_title(row)
    return rows


@frappe.whitelist()
def get_route_assignments(start=0, page_length=PLAN_PAGE_LENGTH):
    """Return recurring operations through native row-level permission hooks."""
    _require_portal_role()
    return _page(
        "Route Assignment",
        [
            "name",
            "assignment_name",
            "route_template",
            "route_template.template_name as route_template_label",
            "work_shift",
            "shift_name",
            "project",
            "project.project_name as project_label",
            "driver",
            "vehicle",
            "starts_on",
            "ends_on",
            "enabled",
            "route_supervisor",
            "status",
            "docstatus",
        ],
        start,
        page_length,
        order_by="modified desc, name desc",
    )


@frappe.whitelist()
def get_route_assignment(name: str):
    _require_portal_role()
    return _permission_checked_doc("Route Assignment", name).as_dict(no_nulls=True)


@frappe.whitelist()
def get_dispatch_trips(start=0, page_length=PLAN_PAGE_LENGTH):
    _require_portal_role()
    return _page(
        "Dispatch Trip",
        [
            "name",
            "trip_title",
            "trip_type",
            "route_assignment",
            "route_template",
            "project",
            "project.project_name as project_label",
            "route_plan",
            "transport_request",
            "shift_name",
            "trip_date",
            "planned_start",
            "planned_end",
            "status",
            "driver",
            "vehicle",
        ],
        start,
        page_length,
        order_by=(
            "`tabDispatch Trip`.trip_date desc, "
            "`tabDispatch Trip`.modified desc, "
            "`tabDispatch Trip`.name desc"
        ),
    )


@frappe.whitelist()
def get_dispatch_trip(name: str):
    _require_portal_role()
    return _permission_checked_doc("Dispatch Trip", name).as_dict(no_nulls=True)


@frappe.whitelist()
def get_movement_history(start=0, page_length=PLAN_PAGE_LENGTH):
    _require_portal_role()
    return _page(
        "Dispatch Trip",
        [
            "name",
            "trip_title",
            "trip_type",
            "route_assignment",
            "route_template",
            "project",
            "route_plan",
            "shift_name",
            "trip_date",
            "status",
            "driver",
            "vehicle",
        ],
        start,
        page_length,
        filters={"status": ["in", ["Completed", "Cancelled"]]},
        order_by=(
            "`tabDispatch Trip`.trip_date desc, "
            "`tabDispatch Trip`.modified desc, "
            "`tabDispatch Trip`.name desc"
        ),
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
def apply_route_assignment_action(name: str, action: str):
    _require_portal_role()
    return _apply_workflow("Route Assignment", name, action)


@frappe.whitelist(methods=["POST"])
def apply_dispatch_trip_action(name: str, action: str):
    """Native workflow keeps completion reserved for manager roles."""
    _require_portal_role()
    return _apply_workflow("Dispatch Trip", name, action)
