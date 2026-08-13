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


def _owned_plan(name: str):
    from apex.salis.api.route_supervisor import _owned_plan as owned_plan

    return owned_plan(name)


def _owned_trip(name: str):
    from apex.salis.api.route_supervisor import _owned_trip as owned_trip

    return owned_trip(name)


def _owned_plan_names():
    if frappe.session.user == "Administrator":
        return None
    return frappe.get_list(
        "Route Plan",
        filters={"route_supervisor": frappe.session.user},
        pluck="name",
        limit_page_length=0,
    )


def _trip_filters(filters=None):
    scoped = dict(filters or {})
    plan_names = _owned_plan_names()
    if plan_names is not None:
        scoped["route_plan"] = ["in", plan_names]
    return scoped, plan_names


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
    filters = (
        {}
        if frappe.session.user == "Administrator"
        else {"route_supervisor": frappe.session.user}
    )
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
        **({"filters": filters} if filters else {}),
    )


@frappe.whitelist()
def get_route_plan(name: str):
    _require_portal_role()
    _owned_plan(name)
    return _permission_checked_doc("Route Plan", name).as_dict(no_nulls=True)


@frappe.whitelist()
def get_dispatch_trips(start=0, page_length=PLAN_PAGE_LENGTH):
    _require_portal_role()
    filters, plan_names = _trip_filters()
    if plan_names == []:
        return []
    return _page(
        "Dispatch Trip",
        [
            "name",
            "route_plan",
            "route_plan.route_name as route_name",
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
        **({"filters": filters} if filters else {}),
    )


@frappe.whitelist()
def get_dispatch_trip(name: str):
    _require_portal_role()
    _owned_trip(name)
    return _permission_checked_doc("Dispatch Trip", name).as_dict(no_nulls=True)


@frappe.whitelist()
def get_movement_history(start=0, page_length=PLAN_PAGE_LENGTH):
    _require_portal_role()
    filters, plan_names = _trip_filters(
        {"status": ["in", ["Completed", "Cancelled"]]}
    )
    if plan_names == []:
        return []
    return _page(
        "Dispatch Trip",
        [
            "name",
            "route_plan",
            "route_plan.route_name as route_name",
            "shift_name",
            "trip_date",
            "status",
            "driver",
            "vehicle",
        ],
        start,
        page_length,
        filters=filters,
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
    _owned_trip(name)
    return _apply_workflow("Dispatch Trip", name, action)
