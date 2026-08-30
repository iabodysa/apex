# Copyright (c) 2026, afmcoltd

import frappe

from apex.apex_core.utils import permission_scope
from apex.apex_core.utils.portal_identity import (
    CAPACITY_USERS,
    DRIVER,
    WORKER,
    capacity_subject,
)
from apex.salis.api.boarding_flow import _manifest_employees, _request_workers
from apex.salis.utils import get_driver_for_session_user

UNSCOPED_ROLES = {
    "System Manager",
    "Fleet Manager",
    "Internal Auditor",
    "Finance Manager",
    "Government Relations Officer",
}

PROJECT = "project"
def allowed_projects(user):
    return permission_scope.allowed_for(user, "Project", "apex_allowed_projects")

def _allowed_projects_for(user, doctype):
    return permission_scope.for_doctype(user, "Project", doctype, allowed_projects(user))

def _is_unscoped(user):
    return permission_scope.is_unscoped(user, UNSCOPED_ROLES)

def report_project_scope(user=None, doctype=None):
    return permission_scope.report_scope(
        user, _is_unscoped, allowed_projects, allow="Project", doctype=doctype
    )

def _column(rule="scoped", own=None):
    return ("column", {"field": PROJECT, "own": own, "rule": rule})

def _dual():
    return (
        "dual",
        {"first": "from_project", "second": "to_project", "own": None, "rule": "dual"},
    )

def _hop(field, doctype, rule, own=None):
    return ("hop", {"field": field, "doctype": doctype, "own": own, "rule": rule})

def _trip(rule="dispatch_trip", own="trip_actor"):
    return ("trip", {"own": own, "rule": rule})

def _trip_child(rule="owner_or_project", own="owner"):
    return ("trip_child", {"own": own, "rule": rule})

def _trip_link(rule="scoped"):
    return ("trip_link", {"own": None, "rule": rule})

def _manifest():
    return ("manifest", {"own": None, "rule": "scoped"})

def _driver(field="driver", own=None):
    return ("driver", {"field": field, "own": own, "rule": "driver_chain"})


SALIS_SCOPE = {
    "Vehicle Assignment": _column(),
    "Fuel Request": _column(rule="owner_or_project", own="owner"),
    "Transport Request": _column(),
    "Route Plan": _column(),
    "Route Assignment": _column(
        rule="route_assignment", own="route_supervisor"
    ),
    "Issue": _column(rule="owner_or_project", own="owner"),
    "Fuel Claim": _column(),
    "Fuel Quota": _column(),
    "Fuel Exception Case": _column(),
    "Salis Vehicle": _column(),
    "Salis Payment Request": _column(rule="payment_sod"),
    "Salis Driver": _column(rule="owner_or_project", own="owner"),
    "Dispatch Trip": _trip(),
    "Trip Start Log": _trip_child(),
    "Passenger Manifest": _manifest(),
    "Driver Attendance": _driver(own="owner"),
    "Driver Suspension": _driver(own="owner"),
    "Boarding Scan Log": _driver(own="owner"),
    "Vehicle Damage Write-Off": _driver(),
    "Vehicle Incident": _driver(own="owner"),
    "Driver Clearance": _driver(),
    "Vehicle Suspension": _driver(field="related_driver"),
    "Movement Cost Transfer": _dual(),
    "Vehicle Handover": _hop("vehicle", "Salis Vehicle", "scoped"),
    "Wash Request": _hop("vehicle", "Salis Vehicle", "scoped"),
    "Fuel Daily Log": _hop("vehicle", "Salis Vehicle", "scoped"),
    "Rental Vehicle Movement": _hop("vehicle", "Salis Vehicle", "scoped"),
    "Movement Cost Recovery": _hop("vehicle", "Salis Vehicle", "scoped"),
    "Transport Trip Rating": _trip_link(),
}

INDIRECT_PROJECT_SCOPED = frozenset(
    doctype
    for doctype, (kind, spec) in SALIS_SCOPE.items()
    if kind in {"manifest", "trip_child", "trip_link"} or kind == "hop"
)

PROJECT_MANDATORY_ON_CREATE = frozenset({"Fuel Claim"})

def _own_driver_trips_condition(user):
    return (
        "`driver` in ("
        "select `name` from `tabSalis Driver` where `employee` in ("
        "select `name` from `tabEmployee` where `user_id` = {user}"
        "))".format(user=frappe.db.escape(user))
    )

def _own_trip_actor_condition(user):
    escaped_user = frappe.db.escape(user)
    return (
        "({driver} or `route_assignment` in ("
        "select `name` from `tabRoute Assignment` where `route_supervisor` = {user}"
        ") or (coalesce(`route_assignment`, '') = '' and `route_plan` in ("
        "select `name` from `tabRoute Plan` where `route_supervisor` = {user})))"
    ).format(driver=_own_driver_trips_condition(user), user=escaped_user)

def _own_clause(spec, user):
    own = spec.get("own")
    if own == "owner":
        return "`owner` = {0}".format(frappe.db.escape(user))
    if own == "driver":
        return _own_driver_trips_condition(user)
    if own == "trip_actor":
        return _own_trip_actor_condition(user)
    if own == "route_supervisor":
        return "`route_supervisor` = {0}".format(frappe.db.escape(user))
    return None



def _render_hop(spec, escaped):
    return "{column} in (select `name` from `tab{doctype}` where `project` in ({values}))".format(
        column=permission_scope.quote_column(spec["field"]), doctype=spec["doctype"], values=escaped
    )

def _route_plan_scope(escaped):
    return "select `name` from `tabRoute Plan` where `project` in ({0})".format(
        escaped
    )

def _trip_scope(escaped):
    route_plans = _route_plan_scope(escaped)
    return (
        "select `name` from `tabDispatch Trip` where "
        "(`project` in ({values}) or (coalesce(`project`, '') = '' and "
        "`route_plan` in ({route_plans})))"
    ).format(values=escaped, route_plans=route_plans)

def _render_trip(spec, escaped):
    del spec
    route_plans = _route_plan_scope(escaped)
    return (
        "(`project` in ({values}) or (coalesce(`project`, '') = '' and "
        "`route_plan` in ({route_plans})))"
    ).format(values=escaped, route_plans=route_plans)

def _render_trip_child(spec, escaped):
    del spec
    trips = _trip_scope(escaped)
    route_plans = _route_plan_scope(escaped)
    return (
        "(`dispatch_trip` in ({trips}) or "
        "(coalesce(`dispatch_trip`, '') = '' and `route_plan` in ({route_plans})))"
    ).format(trips=trips, route_plans=route_plans)

def _render_trip_link(spec, escaped):
    del spec
    return "`dispatch_trip` in ({0})".format(_trip_scope(escaped))

def _render_driver(spec, escaped):
    return (
        "{column} in ("
        "select `name` from `tabSalis Driver` where `project` in ({values})"
        ")".format(column=permission_scope.quote_column(spec["field"]), values=escaped)
    )

def _render_manifest(spec, escaped):
    del spec
    route_plans = _route_plan_scope(escaped)
    trips = _trip_scope(escaped)
    return (
        "(`dispatch_trip` in ({trips}) or "
        "(coalesce(`dispatch_trip`, '') = '' and `route_plan` in ({route_plans})))"
    ).format(trips=trips, route_plans=route_plans)

FRAGMENTS = {
    "column": permission_scope.render_column,
    "dual": permission_scope.render_dual,
    "hop": _render_hop,
    "trip": _render_trip,
    "trip_child": _render_trip_child,
    "trip_link": _render_trip_link,
    "driver": _render_driver,
    "manifest": _render_manifest,
}

def _fragment(kind, spec, values):
    return permission_scope.render_fragment(kind, spec, values, FRAGMENTS)

PORTAL_DRIVER_COLUMNS = {
    "Salis Driver": "name",
    "Salis Vehicle": "current_driver",
    "Route Plan": "driver",
    "Dispatch Trip": "driver",
    "Trip Start Log": "driver",
    "Passenger Manifest": "driver",
    "Transport Request": "assigned_driver",
    "Driver Attendance": "driver",
    "Driver Suspension": "driver",
    "Boarding Scan Log": "driver",
    "Vehicle Damage Write-Off": "driver",
    "Vehicle Incident": "driver",
    "Driver Clearance": "driver",
    "Vehicle Suspension": "related_driver",
}

_WORKER_REQUESTS = (
    "select `parent` from `tabTransport Request Worker` "
    "where `employee` = {subject} and `parenttype` = 'Transport Request'"
)

_WORKER_TRIPS = (
    "select `name` from `tabDispatch Trip` where `transport_request` in ({requests}) "
    "union select `parent` from `tabDispatch Trip Assigned Request` "
    "where `transport_request` in ({requests}) and `parenttype` = 'Dispatch Trip'"
)

PORTAL_WORKER_CLAUSES = {
    "Transport Request": "`name` in ({requests})",
    "Dispatch Trip": "`name` in ({trips})",
    "Trip Start Log": "`dispatch_trip` in ({trips})",
    "Passenger Manifest": "`dispatch_trip` in ({trips})",
}

def _capacity_audience(user):
    return DRIVER if user == CAPACITY_USERS[DRIVER] else WORKER

def _portal_capacity_clause(user, doctype):
    audience = _capacity_audience(user)
    subject = capacity_subject(audience)
    if not subject:
        return "1=0"

    escaped = frappe.db.escape(subject)
    if audience == DRIVER:
        column = PORTAL_DRIVER_COLUMNS.get(doctype)
        if not column:
            return "1=0"
        return "{column} = {subject}".format(
            column=permission_scope.quote_column(column), subject=escaped
        )

    template = PORTAL_WORKER_CLAUSES.get(doctype)
    if not template:
        return "1=0"
    requests = _WORKER_REQUESTS.format(subject=escaped)
    return template.format(requests=requests, trips=_WORKER_TRIPS.format(requests=requests))

def _portal_capacity_read_verdict(doc, user):
    audience = _capacity_audience(user)
    subject = capacity_subject(audience)
    doctype = getattr(doc, "doctype", None)
    if not subject:
        return False

    if audience == DRIVER:
        column = PORTAL_DRIVER_COLUMNS.get(doctype)
        if not column:
            return False
        value = doc.name if column == "name" else getattr(doc, column, None)
        return None if value == subject else False

    if doctype == "Transport Request":
        return None if subject in _request_workers(doc.name) else False
    if doctype not in PORTAL_WORKER_CLAUSES:
        return False
    trip = doc.name if doctype == "Dispatch Trip" else getattr(doc, "dispatch_trip", None)
    return None if trip and subject in _manifest_employees(trip) else False

def project_scope_query(user=None, doctype=None):
    user = permission_scope.resolve_user(user)
    if _is_unscoped(user):
        return ""

    if permission_scope.is_portal_capacity(user):
        return _portal_capacity_clause(user, doctype)

    kind, spec = SALIS_SCOPE.get(doctype) or _column()
    own = _own_clause(spec, user)

    projects = _allowed_projects_for(user, doctype)
    if not projects:
        return own or "1=0"

    in_scope = _fragment(kind, spec, projects)
    if own:
        return "({in_scope} or {own})".format(in_scope=in_scope, own=own)
    return in_scope

def _dispatch_trip_project(dispatch_trip):
    trip = frappe.db.get_value(
        "Dispatch Trip",
        dispatch_trip,
        ["project", "route_plan"],
        as_dict=True,
    )
    if not trip:
        return None
    if trip.project:
        return trip.project
    if trip.route_plan:
        return frappe.db.get_value("Route Plan", trip.route_plan, PROJECT)
    return None

def _doc_project(doc):
    project = getattr(doc, PROJECT, None)
    if project:
        return project

    doctype = getattr(doc, "doctype", None)
    if doctype == "Dispatch Trip":
        route_plan = getattr(doc, "route_plan", None)
        return frappe.db.get_value("Route Plan", route_plan, PROJECT) if route_plan else None

    if doctype not in INDIRECT_PROJECT_SCOPED:
        return None

    dispatch_trip = getattr(doc, "dispatch_trip", None)
    if dispatch_trip:
        return _dispatch_trip_project(dispatch_trip)

    route_plan = getattr(doc, "route_plan", None)
    if route_plan:
        return frappe.db.get_value("Route Plan", route_plan, PROJECT)

    vehicle = getattr(doc, "vehicle", None)
    if vehicle:
        return frappe.db.get_value("Salis Vehicle", vehicle, PROJECT)

    return None

def _driver_chain_project(doc, driver_field="driver"):
    driver = getattr(doc, driver_field, None)
    if driver:
        project = frappe.db.get_value("Salis Driver", driver, PROJECT)
        if project:
            return project

    vehicle = getattr(doc, "vehicle", None)
    if vehicle:
        return frappe.db.get_value("Salis Vehicle", vehicle, PROJECT)

    dispatch_trip = getattr(doc, "dispatch_trip", None)
    if dispatch_trip:
        return _dispatch_trip_project(dispatch_trip)
    return None

def _is_unsaved(doc):
    return bool(getattr(doc, "__islocal", False))

def _own_driver_basis(doc, user, driver_field="driver"):
    own_driver = get_driver_for_session_user(user)
    if not own_driver:
        return False
    if getattr(doc, driver_field, None) == own_driver:
        return True
    dispatch_trip = getattr(doc, "dispatch_trip", None)
    if dispatch_trip:
        return frappe.db.get_value("Dispatch Trip", dispatch_trip, "driver") == own_driver
    return False

def _unanchored_create_is_denied(doc):
    return getattr(doc, "doctype", None) in PROJECT_MANDATORY_ON_CREATE and _is_unsaved(doc)

def scoped_has_permission(doc, ptype, user=None):
    user = permission_scope.resolve_user(user)
    if _is_unscoped(user):
        return None

    project = _doc_project(doc)
    if not project:
        if getattr(doc, "owner", None) == user and not _unanchored_create_is_denied(doc):
            return None
        return False

    if project not in _allowed_projects_for(user, doc.doctype):
        return False

    return None

def _owner_or_project_has_permission(doc, user=None):
    user = permission_scope.resolve_user(user)
    if _is_unscoped(user):
        return None

    unsaved = _is_unsaved(doc)

    if not unsaved and getattr(doc, "owner", None) == user:
        return None

    project = _doc_project(doc)
    if project and project in _allowed_projects_for(user, doc.doctype):
        return None

    if unsaved and _own_driver_basis(doc, user):
        return None

    return False

def _dispatch_trip_has_permission(doc, user=None):
    user = permission_scope.resolve_user(user)
    if _is_unscoped(user):
        return None

    own_driver = get_driver_for_session_user(user)
    if own_driver and getattr(doc, "driver", None) == own_driver:
        return None

    route_assignment = getattr(doc, "route_assignment", None)
    if route_assignment:
        supervisor = frappe.db.get_value(
            "Route Assignment", route_assignment, "route_supervisor"
        )
    else:
        route_plan = getattr(doc, "route_plan", None)
        supervisor = (
            frappe.db.get_value("Route Plan", route_plan, "route_supervisor")
            if route_plan
            else None
        )
    if supervisor == user:
        return None

    project = _doc_project(doc)
    if not project:
        return False

    if project not in _allowed_projects_for(user, doc.doctype):
        return False

    return None

def _route_assignment_has_permission(doc, user=None):
    user = permission_scope.resolve_user(user)
    if _is_unscoped(user):
        return None

    if getattr(doc, "route_supervisor", None) == user:
        return None

    project = _doc_project(doc)
    if not project:
        return False
    if project not in _allowed_projects_for(user, doc.doctype):
        return False
    return None

def _driver_chain_has_permission(doc, user=None, driver_field="driver", with_owner=False):
    user = permission_scope.resolve_user(user)
    if _is_unscoped(user):
        return None

    unsaved = _is_unsaved(doc)

    if with_owner and not unsaved and getattr(doc, "owner", None) == user:
        return None

    project = _driver_chain_project(doc, driver_field=driver_field)
    if project and project in _allowed_projects_for(user, doc.doctype):
        return None

    if with_owner and unsaved and _own_driver_basis(doc, user, driver_field=driver_field):
        return None

    return False

def movement_cost_transfer_has_permission(doc, ptype, user=None):
    user = permission_scope.resolve_user(user)
    if _is_unscoped(user):
        return None

    from_project = getattr(doc, "from_project", None)
    to_project = getattr(doc, "to_project", None)
    if not from_project and not to_project:
        return None

    allowed = _allowed_projects_for(user, doc.doctype)
    if (from_project and from_project in allowed) or (to_project and to_project in allowed):
        return None
    return False

FINANCE_EXCLUSIVE_STATES = {
    "Approved by Finance",
    "Paid",
}

def payment_sod_has_permission(doc, ptype, user=None):
    if getattr(doc, "doctype", None) != "Salis Payment Request":
        return None

    if scoped_has_permission(doc, ptype, user=user) is False:
        return False

    if ptype not in ("submit", "write"):
        return None

    status = getattr(doc, "status", None)
    if status not in FINANCE_EXCLUSIVE_STATES:
        return None

    user = permission_scope.resolve_user(user)
    if user in ("Administrator", "Guest"):
        return None

    requested_by = getattr(doc, "requested_by", None)
    owner = getattr(doc, "owner", None)

    if requested_by and requested_by == user:
        return False
    if owner and owner == user:
        return False

    return None

def _rule_driver_chain(doc, ptype, user, spec):
    return _driver_chain_has_permission(
        doc, user=user, driver_field=spec["field"], with_owner=spec.get("own") == "owner"
    )

DOCUMENT_RULES = {
    "scoped": lambda doc, ptype, user, spec: scoped_has_permission(doc, ptype, user=user),
    "owner_or_project": lambda doc, ptype, user, spec: _owner_or_project_has_permission(doc, user),
    "dispatch_trip": lambda doc, ptype, user, spec: _dispatch_trip_has_permission(doc, user),
    "route_assignment": lambda doc, ptype, user, spec: _route_assignment_has_permission(
        doc, user
    ),
    "driver_chain": _rule_driver_chain,
    "dual": lambda doc, ptype, user, spec: movement_cost_transfer_has_permission(doc, ptype, user),
    "payment_sod": lambda doc, ptype, user, spec: payment_sod_has_permission(doc, ptype, user),
}

def _trip_start_log_capacity_verdict(doc, ptype):
    verdict = permission_scope.portal_capacity_verdict(ptype)
    if verdict is False:
        return False

    driver_field = getattr(doc, "driver", None)
    if driver_field and driver_field == capacity_subject(DRIVER):
        return verdict

    worker = capacity_subject(WORKER)
    dispatch_trip = getattr(doc, "dispatch_trip", None)
    if worker and dispatch_trip:
        if worker in _manifest_employees(dispatch_trip):
            return verdict

    return False

def project_scoped_has_permission(doc, ptype, user=None):
    user = permission_scope.resolve_user(user)
    if permission_scope.is_portal_capacity(user):
        if getattr(doc, "doctype", None) == "Trip Start Log":
            return _trip_start_log_capacity_verdict(doc, ptype)
        if ptype == "read":
            return _portal_capacity_read_verdict(doc, user)
        return permission_scope.portal_capacity_verdict(ptype)

    kind, spec = SALIS_SCOPE.get(getattr(doc, "doctype", None)) or _column()
    del kind
    return DOCUMENT_RULES[spec["rule"]](doc, ptype, user, spec)
