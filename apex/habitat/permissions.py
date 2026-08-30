# Copyright (c) 2026, afmcoltd

import frappe
from frappe import _

from apex.apex_core.utils import permission_scope

PRIVILEGED_ROLES = {
    "System Manager",
    "Accommodation Manager",
    "Resident Request Coordinator",
}

HOUSING_UNSCOPED_ROLES = {
    "System Manager",
    "Accommodation Manager",
    "Internal Auditor",
    "Finance Manager",
    "HR Manager",
}

BUILDING = "building"


def _is_privileged(user):
    if user in ("Administrator", "Guest"):
        return user == "Administrator"
    return bool(set(frappe.get_roles(user)) & PRIVILEGED_ROLES)


def allowed_buildings(user):
    return permission_scope.allowed_for(user, "Building", "apex_allowed_buildings")


def _allowed_buildings_for(user, doctype):
    return permission_scope.for_doctype(user, "Building", doctype, allowed_buildings(user))


def _building_is_unscoped(user):
    return permission_scope.is_unscoped(user, HOUSING_UNSCOPED_ROLES)


def validate_building_scope(user=None, doctype=None):
    user = permission_scope.resolve_user(user)
    if _building_is_unscoped(user):
        return
    if _allowed_buildings_for(user, doctype):
        return
    frappe.throw(
        _(
            "Your account is not granted any building yet, so there is nothing here it"
            " may act on. Ask an administrator to grant you a building."
        ),
        frappe.PermissionError,
        title=_("No building granted"),
    )


def _building_condition(user=None, column="`building`", doctype=None):
    return permission_scope.scope_condition(
        user, _building_is_unscoped, allowed_buildings, column, allow="Building", doctype=doctype
    )


def _column(field):
    return ("column", {"field": field})


def _dual(first, second):
    return ("dual", {"first": first, "second": second})


def _hop(field, doctype):
    return ("hop", {"field": field, "doctype": doctype})


def _child(child_doctype, parent_doctype):
    return ("child", {"child": child_doctype, "parent": parent_doctype})




BUILDING_SCOPE = {
    "Building": _column("name"),
    "Housing Assignment": _column(BUILDING),
    "Custody Issue": _column(BUILDING),
    "Cleaning Log": _column(BUILDING),
    "Safety Round": _column(BUILDING),
    "Safety Task Execution": _column(BUILDING),
    "Scheduled Task Instance": _column(BUILDING),
    "Safety Incident": _column(BUILDING),
    "Safety Inspection Report": _column(BUILDING),
    "Safety Finding Ledger": _column(BUILDING),
    "Cleaning Compliance Ledger": _column(BUILDING),
    "Resident Request": _column(BUILDING),
    "Idle Resident Report": _column(BUILDING),
    "Facility Asset Custody Assignment": _column(BUILDING),
    "Operational Depreciation Snapshot": _column(BUILDING),
    "Custody Return": _column(BUILDING),
    "Custody Damage Assessment": _column(BUILDING),
    "Custody Acknowledgment": _column(BUILDING),
    "Facility Asset": _column(BUILDING),
    "Housing Inventory": _column(BUILDING),
    "Building License": _column(BUILDING),
    "Maintenance Work Order": _column(BUILDING),
    "Maintenance Inspection Report": _column(BUILDING),
    "Occupancy Snapshot": _column(BUILDING),
    "Temporary Worker": _column(BUILDING),
    "Arrival Batch": _column(BUILDING),
    "Room": _column(BUILDING),
    "Bed": _column(BUILDING),
    "Accommodation Stock Ledger": _column(BUILDING),
    "Facility Asset Movement": _dual("from_building", "to_building"),
    "Custody Handover": _dual("from_building", "to_building"),
    "Material Transfer": _dual("from_building", "to_building"),
    "Facility Asset Delivery": _dual("from_building", "to_building"),
    "Housing Checkout": _hop("bed", "Bed"),
    "Room Bed Transfer": _hop("assignment", "Housing Assignment"),
    "Audit Remediation Plan": _child("Audit Remediation Building Scope", "Audit Remediation Plan"),
}

BUILDING_FETCH_ANCHOR = {
    "Bed": ("room", "Room"),
    "Custody Acknowledgment": ("custody_issue", "Custody Issue"),
    "Custody Damage Assessment": ("custody_return", "Custody Return"),
    "Custody Return": ("custody_issue", "Custody Issue"),
    "Housing Assignment": ("bed", "Bed"),
    "Housing Checkout": ("assignment", "Housing Assignment"),
    "Housing Inventory": ("room", "Room"),
    "Maintenance Inspection Report": ("maintenance_work_order", "Maintenance Work Order"),
    "Maintenance Work Order": ("maintenance_request", "Maintenance Request"),
    "Resident Request": ("bed", "Bed"),
    "Room Bed Transfer": ("assignment", "Housing Assignment"),
    "Scheduled Task Instance": ("assignment", "Scheduled Task Assignment"),
}






def _render_hop(spec, escaped):
    return "{column} in (select `name` from `tab{doctype}` where `building` in ({values}))".format(
        column=permission_scope.quote_column(spec["field"]), doctype=spec["doctype"], values=escaped
    )


def _render_child(spec, escaped):
    return (
        "`name` in (select `parent` from `tab{child}` "
        "where `parenttype` = {parent} and `building` in ({values}))".format(
            child=spec["child"], parent=frappe.db.escape(spec["parent"]), values=escaped
        )
    )


FRAGMENTS = {
    "column": permission_scope.render_column,
    "dual": permission_scope.render_dual,
    "hop": _render_hop,
    "child": _render_child,
}


def _fragment(kind, spec, values):
    return permission_scope.render_fragment(kind, spec, values, FRAGMENTS)


def building_scope_query(user=None, doctype=None):
    user = permission_scope.resolve_user(user)
    if _building_is_unscoped(user):
        return ""

    buildings = _allowed_buildings_for(user, doctype)
    if not buildings:
        return "1=0"

    kind, spec = BUILDING_SCOPE.get(doctype) or _column(BUILDING)
    return _fragment(kind, spec, buildings)


def refuse_a_supervisor_with_no_building(user=None, doctype=None):
    user = permission_scope.resolve_user(user)
    if _building_is_unscoped(user):
        return ""
    return "" if allowed_buildings(user) else "1=0"


def _estate_from_anchor(doc, doctype):
    anchor = BUILDING_FETCH_ANCHOR.get(doctype)
    if not anchor:
        return None
    fieldname, parent_doctype = anchor
    parent = getattr(doc, fieldname, None)
    if not parent:
        return None
    return frappe.db.get_value(parent_doctype, parent, "building")


def _estates_column(doc, spec):
    stored = getattr(doc, spec["field"], None)
    return [stored] if stored else []


def _estates_dual(doc, spec):
    endpoints = (getattr(doc, spec["first"], None), getattr(doc, spec["second"], None))
    return [value for value in endpoints if value]


def _estates_child(doc, spec):
    rows = getattr(doc, "buildings_in_scope", None) or []
    return [value for value in (getattr(row, "building", None) for row in rows) if value]


def _estates_hop(doc, spec):
    link = getattr(doc, spec["field"], None)
    if not link:
        return []
    hopped = frappe.db.get_value(spec["doctype"], link, BUILDING)
    return [hopped] if hopped else []


ESTATES = {
    "column": _estates_column,
    "dual": _estates_dual,
    "hop": _estates_hop,
    "child": _estates_child,
}

ANCHORED_KINDS = ("column", "hop")


def _doc_estates(doc):
    doctype = getattr(doc, "doctype", None)
    kind, spec = BUILDING_SCOPE.get(doctype) or _column(BUILDING)

    estates = ESTATES[kind](doc, spec)
    if estates or kind not in ANCHORED_KINDS:
        return estates

    anchor = _estate_from_anchor(doc, doctype)
    return [anchor] if anchor else []


def building_scoped_has_permission(doc, ptype, user=None):
    user = permission_scope.resolve_user(user)
    if _building_is_unscoped(user):
        return None

    if permission_scope.is_portal_capacity(user):
        if ptype == "read":
            return False
        return permission_scope.portal_capacity_verdict(ptype)

    estates = _doc_estates(doc)
    if not estates:
        return False

    allowed = _allowed_buildings_for(user, doc.doctype)
    return None if any(estate in allowed for estate in estates) else False


def report_building_scope(user=None, doctype=None):
    return permission_scope.report_scope(
        user, _building_is_unscoped, allowed_buildings, allow="Building", doctype=doctype
    )


def maintenance_request_query(user=None, doctype=None):
    user = permission_scope.resolve_user(user)
    if user == "Guest":
        return "1=0"
    roles = set(frappe.get_roles(user))
    if "Resident Supervisor" in roles and not (
        roles & {"System Manager", "Accommodation Manager"}
    ):
        buildings = _allowed_buildings_for(user, "Maintenance Request")
        if not buildings:
            return "1=0"
        return _fragment("column", {"field": BUILDING}, buildings)
    if _is_privileged(user):
        return ""

    escaped = frappe.db.escape(user)
    return "(`owner` = {0} or `assigned_to` = {0})".format(escaped)


def maintenance_request_has_permission(doc, ptype, user=None):
    user = permission_scope.resolve_user(user)
    roles = set(frappe.get_roles(user))
    if "Resident Supervisor" in roles and not (
        roles & {"System Manager", "Accommodation Manager"}
    ):
        building = getattr(doc, "building", None)
        allowed = _allowed_buildings_for(user, "Maintenance Request")
        return bool(building and building in allowed)
    if _is_privileged(user):
        return None

    if getattr(doc, "owner", None) == user:
        return True
    if getattr(doc, "assigned_to", None) == user:
        return True
    return False


def report_maintenance_request_scope(user=None):
    user = permission_scope.resolve_user(user)
    if _is_privileged(user):
        return False, user
    return True, user
