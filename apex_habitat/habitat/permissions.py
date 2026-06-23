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


def building_scoped_has_permission(doc, ptype, user=None):
    """Deny a building-scoped user acting on a doc outside their buildings.

    Returns None to defer to Frappe's default resolution (unscoped users / in-scope
    docs — keeps DocPerms intact), or False to block. The Accommodation Building doc
    is scoped on its own name; the transactions are scoped on their `building` field.
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
