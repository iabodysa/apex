# Copyright (c) 2026, AFMCO Support Services Co. Ltd
# Owner-scoped row security for Habitat Maintenance Request intake.
#
# Design (universal intake, private tickets):
#   - Maintenance Request grants the "All" role a CREATE-only DocPerm, so any
#     authenticated user can raise a ticket without holding an operational role.
#   - That same "All" DocPerm reads with ``if_owner``, so by the standard
#     permission engine a raiser can read only the rows they own.
#   - The query/has_permission functions below extend that owner read to also
#     cover the user the ticket is ``assigned_to`` (the technician working it),
#     while still hiding every other user's tickets — none can enumerate or open
#     a ticket they neither raised nor were assigned.
#   - A small set of privileged oversight roles (PRIVILEGED_ROLES) and the
#     Administrator are NOT scoped: they see and act on every ticket. Their
#     access is governed entirely by their own DocPerms (read/write/submit),
#     which these functions defer to (query returns "" / has_permission returns
#     None) and never widen.
#
# Ownership reliability (T4): the Maintenance Request controller forces
# ``reported_by`` to ``frappe.session.user`` server-side on intake, and Frappe
# stamps ``owner`` with the creating user, so the ``owner``-based scope here is a
# trustworthy identity boundary — a client cannot spoof who raised a ticket to
# see another user's row.
#
# Pattern (mirrors apex_habitat/salis/permissions.py):
#   - ``maintenance_request_query`` is wired in ``permission_query_conditions``
#     and returns a SQL WHERE fragment ("" = no restriction) confining the
#     list/report views to the user's own + assigned tickets.
#   - ``maintenance_request_has_permission`` is wired in ``has_permission`` and
#     enforces the same boundary on individual document access. It returns None
#     to defer to Frappe's default resolution (for privileged users) or True/
#     False for the scoped owner/assignee check — the same None/False/True
#     contract as the Salis scoped hooks, so it composes with DocPerms and never
#     widens access.

import frappe

# Oversight roles that see every Maintenance Request (no owner scoping). Their
# visibility is bounded only by their own read/write DocPerms.
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
