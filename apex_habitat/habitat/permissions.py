# Copyright (c) 2026, AFMCO Support Services Co. Ltd
# [#of2x05]

import frappe

# [#mirgwe]
PRIVILEGED_ROLES = {
    "System Manager",
    "Accommodation Manager",
    "Resident Supervisor",
    "Resident Request Coordinator",
}


def _resolve_user(user=None):
    """Return the effective user, defaulting to the session user."""
    return user or frappe.session.user


def _is_privileged(user):
    """True when the user is the Administrator or holds any privileged role.

    Guest is never privileged.
    """
    if user in ("Administrator", "Guest"):
        return user == "Administrator"
    return bool(set(frappe.get_roles(user)) & PRIVILEGED_ROLES)


def maintenance_request_query(user=None):
    """Owner-scope the Maintenance Request list/report view.

    Returns "" (no restriction) for the Administrator and privileged oversight
    roles. Returns "1=0" for Guest, who must see nothing. For every other user
    the fragment confines the view to the tickets they raised (``owner``) or
    were assigned (``assigned_to``).

    NOTE on the ``if_owner`` interaction: when a user's ONLY read on Maintenance
    Request is the universal "All" role's ``if_owner`` DocPerm, Frappe AND-s its
    own ``owner = me`` match onto this fragment, so their LIST view collapses to
    owner-only. The ``assigned_to`` branch therefore surfaces assigned rows in the
    list only for users who also hold a plain (non-``if_owner``) read — i.e. the
    operational roles such as Maintenance Technician (the realistic assignee).
    Any assignee can still OPEN an assigned ticket via ``has_permission`` below.
    """
    user = _resolve_user(user)
    if user == "Guest":
        return "1=0"
    if _is_privileged(user):
        return ""

    escaped = frappe.db.escape(user)
    return "(`owner` = {0} or `assigned_to` = {0})".format(escaped)


def maintenance_request_has_permission(doc, ptype, user=None):
    """Confine individual Maintenance Request access to its owner/assignee.

    Mirrors ``maintenance_request_query`` for the form view / REST resource /
    link reads. Returns None to defer to Frappe's default permission resolution
    for the Administrator and privileged oversight roles (so their DocPerms
    govern, unwidened). For every other user it returns True only when the user
    raised the ticket (``owner``) or is its ``assigned_to`` technician, and False
    otherwise — never exposing a ticket the user neither raised nor was assigned.
    """
    user = _resolve_user(user)
    if _is_privileged(user):
        return None

    if getattr(doc, "owner", None) == user:
        return True
    if getattr(doc, "assigned_to", None) == user:
        return True
    return False


# [#qyfpkv]
HOUSING_UNSCOPED_ROLES = {
    "System Manager",
    "Accommodation Manager",
    "Internal Auditor",
    "Finance Manager",
}


def _allowed_buildings(user):
    """Accommodation Building names the user has an explicit User Permission for."""
    return list(
        frappe.get_all(
            "User Permission",
            filters={"allow": "Accommodation Building", "user": user},
            pluck="for_value",
        )
    )


def _building_is_unscoped(user):
    """True when the user is the Administrator or holds a building-oversight role."""
    if user in ("Administrator", "Guest"):
        return user == "Administrator"
    return bool(set(frappe.get_roles(user)) & HOUSING_UNSCOPED_ROLES)


def _building_condition(user=None, column="`building`"):
    """SQL WHERE fragment restricting ``column`` to the user's allowed buildings.

    "" for unscoped users (no restriction); "1=0" when the user is scoped but has
    no allowed buildings (so they see nothing).
    """
    user = _resolve_user(user)
    if _building_is_unscoped(user):
        return ""
    buildings = _allowed_buildings(user)
    if not buildings:
        return "1=0"
    escaped = ", ".join(frappe.db.escape(b) for b in buildings)
    return "{column} in ({values})".format(column=column, values=escaped)


# [#63ah2p]
def accommodation_assignment_query(user=None):
    return _building_condition(user)


def custody_issue_query(user=None):
    return _building_condition(user)


def cleaning_log_query(user=None):
    return _building_condition(user)


def accommodation_building_query(user=None):
    # [#3n6e22]
    return _building_condition(user, column="`name`")


# [#wave4-safety] Building-scope the safety records on their own `building` field, so
# the Safety Officer / Resident Supervisor see only their buildings' rows while the
# oversight roles in HOUSING_UNSCOPED_ROLES stay unrestricted.
def safety_round_query(user=None):
    return _building_condition(user)


def safety_task_execution_query(user=None):
    return _building_condition(user)


def scheduled_task_instance_query(user=None):
    return _building_condition(user)


# Resident request + idle report carry their own `building` Link, so the same
# building scope applies — a Resident Supervisor sees only their estate's rows.
def accommodation_resident_request_query(user=None):
    return _building_condition(user)


def idle_resident_report_query(user=None):
    return _building_condition(user)


# [#rptscope] Script Reports run on frappe.get_all, which forces ignore_permissions
# (frappe/__init__.py get_all forces ignore_permissions), so the building row-scoping
# the desk list gets via permission_query_conditions is bypassed in report code. This
# helper consolidates the re-application: it returns the building filter a report must
# AND onto its own get_all so a building-scoped user sees only their estates' rows while
# the oversight roles in HOUSING_UNSCOPED_ROLES stay unrestricted.
def report_building_scope(user=None):
    """Return ``(restrict, allowed_buildings)`` for report-side building scoping.

    ``restrict`` is False for unscoped oversight roles (the report applies no extra
    filter — they see everything). When True the report must confine its rows to
    ``allowed_buildings`` (an empty list means a scoped user with no permitted
    building, i.e. the report should return no rows).
    """
    user = _resolve_user(user)
    if _building_is_unscoped(user):
        return False, []
    return True, _allowed_buildings(user)


def building_scoped_has_permission(doc, ptype, user=None):
    """Deny a building-scoped user acting on a doc outside their buildings.

    Returns None to defer to Frappe's default resolution (unscoped users / in-scope
    docs — keeps DocPerms intact), or False to block. The Accommodation Building doc
    is scoped on its own name; the transactions are scoped on their `building` field.

    Deny-only + ptype-agnostic: it never branches on ``ptype``, so an out-of-building
    doc is blocked for every action including ``submit`` — a scoped user can neither
    read nor submit another estate's record.
    """
    user = _resolve_user(user)
    if _building_is_unscoped(user):
        return None

    if getattr(doc, "doctype", None) == "Accommodation Building":
        building = getattr(doc, "name", None)
    else:
        building = getattr(doc, "building", None)

    if not building:
        # [#1i4wio]
        return False
    return None if building in _allowed_buildings(user) else False


# [#wave5-tenant] close the cross-tenant read/submit gap on the remaining
# building-bearing Habitat DocTypes. Single-`building` members reuse the helpers above
# (pqc -> _building_condition, form/submit -> building_scoped_has_permission). The
# transfer/movement/handover members carry NO single `building` (only from_building +
# to_building), so they get the dual-column variants below: a row is in scope when
# EITHER endpoint is the user's estate, and a cross-building doc is denied for every
# action including submit.

# single-`building` query members (reuse _building_condition)
def facility_asset_custody_assignment_query(user=None):
    return _building_condition(user)


def non_financial_depreciation_snapshot_query(user=None):
    return _building_condition(user)


def custody_return_query(user=None):
    return _building_condition(user)


def custody_damage_assessment_query(user=None):
    return _building_condition(user)


def facility_asset_movement_query(user=None):
    # [#dual] movement has from_building + to_building, not `building`.
    return _dual_building_condition(user)


def custody_acknowledgment_query(user=None):
    return _building_condition(user)


def accommodation_custody_handover_query(user=None):
    # [#dual] handover has from_building + to_building, not `building`.
    return _dual_building_condition(user)


def accommodation_material_transfer_query(user=None):
    # [#dual] transfer has from_building + to_building, not `building`.
    return _dual_building_condition(user)


def facility_asset_query(user=None):
    return _building_condition(user)


def housing_inventory_query(user=None):
    return _building_condition(user)


def building_license_query(user=None):
    return _building_condition(user)


def maintenance_work_order_query(user=None):
    return _building_condition(user)


# more single-`building` query members (reuse _building_condition)
def accommodation_occupancy_snapshot_query(user=None):
    return _building_condition(user)


def temporary_worker_query(user=None):
    return _building_condition(user)


def arrival_batch_query(user=None):
    return _building_condition(user)


def accommodation_room_query(user=None):
    return _building_condition(user)


def accommodation_bed_query(user=None):
    return _building_condition(user)


def _dual_building_condition(user=None):
    """WHERE fragment scoping a from_building/to_building doc to the user's estate.

    A single fragment (pqc hooks AND-join, so the OR must live inside one fragment):
    matches a row when EITHER endpoint is one of the user's allowed buildings. "" for
    unscoped users; "1=0" when the user is scoped but has no allowed buildings.
    """
    user = _resolve_user(user)
    if _building_is_unscoped(user):
        return ""
    buildings = _allowed_buildings(user)
    if not buildings:
        return "1=0"
    escaped = ", ".join(frappe.db.escape(b) for b in buildings)
    return "(`from_building` in ({values}) or `to_building` in ({values}))".format(
        values=escaped
    )


def dual_building_scoped_has_permission(doc, ptype, user=None):
    """Deny a scoped user acting on a from/to_building doc outside their estate.

    Mirrors ``_dual_building_condition`` for the form view / REST / submit. Returns
    None to defer (unscoped users / in-scope docs — DocPerms intact), or False to
    block. In scope when EITHER endpoint is the user's building; a cross-building doc
    (neither endpoint in scope) is denied for every action including submit.
    """
    user = _resolve_user(user)
    if _building_is_unscoped(user):
        return None

    allowed = _allowed_buildings(user)
    endpoints = [
        getattr(doc, "from_building", None),
        getattr(doc, "to_building", None),
    ]
    endpoints = [b for b in endpoints if b]
    if not endpoints:
        # [#1i4wio] a scoped user can never act on an estate-less transfer doc.
        return False
    return None if any(b in allowed for b in endpoints) else False
