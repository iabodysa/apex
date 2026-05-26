# Copyright (c) 2026, Abdullah Fahad Al-Mutairi Co. (AFMCO)
# Project-based row scoping for Salis transactional DocTypes.
#
# control requirement: every role currently acts across all projects.
# Supervisors and project managers must be scoped to the projects they are
# granted via a User Permission on "Project". A small set of oversight roles
# remain unscoped (see UNSCOPED_ROLES) and continue to see every project.
#
# Pattern:
#   - permission_query_conditions hooks call the per-DocType <doctype>_query
#     functions below. Each returns a SQL WHERE fragment (or "" for unscoped
#     users) that restricts the list/report views to the allowed projects.
#   - the has_permission hook calls scoped_has_permission to enforce the same
#     restriction on individual document access.

import frappe

UNSCOPED_ROLES = {
    "System Manager",
    "Fleet Manager",
    "Fleet Operations Manager",
    "Fleet Regional Manager",
    "Internal Auditor",
}


def _resolve_user(user=None):
    """Return the effective user, defaulting to the session user."""
    return user or frappe.session.user


def _allowed_projects(user):
    """Project names the given user has an explicit User Permission for."""
    rows = frappe.get_all(
        "User Permission",
        filters={"allow": "Project", "user": user},
        pluck="for_value",
    )
    return list(rows)


def _is_unscoped(user):
    """True when the user holds any oversight role that sees all projects."""
    if user in ("Administrator", "Guest"):
        return user == "Administrator"
    user_roles = set(frappe.get_roles(user))
    return bool(user_roles & UNSCOPED_ROLES)


def _project_condition(user, column="`project`"):
    """Build the SQL fragment restricting `column` to the allowed projects.

    Returns "" for unscoped users (no restriction). Returns "1=0" when the
    user is scoped but has no allowed projects, so they see nothing.
    """
    user = _resolve_user(user)
    if _is_unscoped(user):
        return ""

    projects = _allowed_projects(user)
    if not projects:
        return "1=0"

    escaped = ", ".join(frappe.db.escape(p) for p in projects)
    return "{column} in ({values})".format(column=column, values=escaped)


# ---------------------------------------------------------------------------
# Per-DocType permission_query_conditions functions
# ---------------------------------------------------------------------------
# DocTypes with a direct `project` Link field.

def vehicle_assignment_query(user=None):
    return _project_condition(user)


def fuel_request_query(user=None):
    return _project_condition(user)


def fuel_topup_request_query(user=None):
    return _project_condition(user)


def transport_request_query(user=None):
    return _project_condition(user)


def route_plan_query(user=None):
    return _project_condition(user)


def sponsorship_transfer_case_query(user=None):
    return _project_condition(user)


def dispatch_trip_query(user=None):
    """Dispatch Trip has no own `project` field; it links to a Route Plan.

    Scope it through the parent Route Plan's project so the same project
    boundary applies. The fragment references the Dispatch Trip table's
    `route_plan` column via a subquery on `tabRoute Plan`.
    """
    user = _resolve_user(user)
    if _is_unscoped(user):
        return ""

    projects = _allowed_projects(user)
    if not projects:
        return "1=0"

    escaped = ", ".join(frappe.db.escape(p) for p in projects)
    return (
        "`route_plan` in ("
        "select `name` from `tabRoute Plan` where `project` in ({values})"
        ")".format(values=escaped)
    )


# ---------------------------------------------------------------------------
# Shared has_permission hook
# ---------------------------------------------------------------------------

def _doc_project(doc):
    """Resolve the project a document belongs to, including Dispatch Trip."""
    project = getattr(doc, "project", None)
    if project:
        return project

    if getattr(doc, "doctype", None) == "Dispatch Trip":
        route_plan = getattr(doc, "route_plan", None)
        if route_plan:
            return frappe.db.get_value("Route Plan", route_plan, "project")

    return None


def scoped_has_permission(doc, ptype, user=None):
    """Deny a scoped user acting on a doc outside their allowed projects.

    Returns False to block, or None to defer to Frappe's default permission
    resolution (which keeps standard role-based checks intact).
    """
    user = _resolve_user(user)
    if _is_unscoped(user):
        return None

    project = _doc_project(doc)
    if not project:
        # No project context to scope on; defer to default permissions.
        return None

    if project not in _allowed_projects(user):
        return False

    return None


# ---------------------------------------------------------------------------
# Segregation of duties (tiered authority)
# ---------------------------------------------------------------------------
# A user who holds both an operational role and the finance role must not be
# able to self-approve their own payment requests. This enforces
# approver != requester at the permission layer, in addition to the
# controller-level check, so a Finance-exclusive transition (Approved by
# Finance / Paid) on a document the acting user requested or created is
# blocked regardless of how the transition is attempted.

# Statuses that represent a Finance-exclusive approval/payment outcome.
FINANCE_EXCLUSIVE_STATES = {
    "Approved by Finance",
    "Paid",
}


def payment_sod_has_permission(doc, ptype, user=None):
    """Block self-approval of payment requests into Finance-exclusive states.

    For "Salis Payment Request", when the action is a submit/write that moves
    the document into a Finance-exclusive state (Approved by Finance / Paid),
    deny the action if the acting user is the requester or the original
    creator of the document. Returns False to block; otherwise returns None to
    defer to Frappe's default permission resolution.
    """
    if getattr(doc, "doctype", None) != "Salis Payment Request":
        return None

    if ptype not in ("submit", "write"):
        return None

    status = getattr(doc, "status", None)
    if status not in FINANCE_EXCLUSIVE_STATES:
        return None

    user = _resolve_user(user)
    if user in ("Administrator", "Guest"):
        return None

    requested_by = getattr(doc, "requested_by", None)
    owner = getattr(doc, "owner", None)

    if requested_by and requested_by == user:
        return False
    if owner and owner == user:
        return False

    return None
