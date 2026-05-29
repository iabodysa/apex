# Copyright (c) 2026, AFMCO Support Services Co. Ltd
# Project-based row scoping for Salis transactional DocTypes.
#
# By default every role acts across all projects.
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
    "Internal Auditor",
    # Finance Manager is a central finance-control role, not a project-bound
    # operator: across the operational DocTypes it holds read/report oversight,
    # and on the finance-boundary DocTypes (Salis Payment Request, Fuel Claim,
    # Rental Settlement) it is THE cross-project approver/payer. Scoping it to a
    # single project would make it unable to approve payments for other projects,
    # so — like Internal Auditor — it sees every project. (Maker != checker is
    # still enforced separately by the SoD hooks/workflow conditions.)
    "Finance Manager",
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


def transport_request_query(user=None):
    return _project_condition(user)


def route_plan_query(user=None):
    return _project_condition(user)


def sponsorship_transfer_case_query(user=None):
    return _project_condition(user)


def support_ticket_query(user=None):
    return _project_condition(user)


def fuel_claim_query(user=None):
    return _project_condition(user)


def fuel_quota_query(user=None):
    return _project_condition(user)


def fuel_exception_case_query(user=None):
    return _project_condition(user)


def salis_payment_request_query(user=None):
    return _project_condition(user)


def approval_request_query(user=None):
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


def trip_start_log_query(user=None):
    """Trip Start Log has no own `project` field; it links to a Dispatch Trip,
    which in turn links to a Route Plan carrying the project.

    Scope it through that chain so the same project boundary applies as on every
    other Salis transactional DocType. The fragment restricts the Trip Start Log
    table's `route_plan` column (populated by fetch from the Dispatch Trip) to the
    user's allowed projects via a subquery on `tabRoute Plan`.
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
    """Resolve the project a document belongs to, including the docs that reach
    their project through a Route Plan (Dispatch Trip, Trip Start Log)."""
    project = getattr(doc, "project", None)
    if project:
        return project

    if getattr(doc, "doctype", None) in ("Dispatch Trip", "Trip Start Log"):
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
        # Project-less doc. Ownership is an independent, legitimate access basis
        # (an if_owner permission row), so defer to Frappe's default resolution
        # when the acting user owns the doc — e.g. a Driver reading the Support
        # Ticket they raised, where the row carries no project. This does not
        # widen project scope: every project-BEARING doc is still filtered below.
        if getattr(doc, "owner", None) == user:
            return None
        # Otherwise deny, to mirror the list-view query condition (which shows
        # scoped users nothing when the project is absent). Without this, a
        # project-less record would bypass scoping.
        return False

    if project not in _allowed_projects(user):
        return False

    return None


# ---------------------------------------------------------------------------
# Segregation of duties (requester cannot approve)
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
    """Project-scope a payment request AND block self-approval of it.

    This single hook composes two independent denials for "Salis Payment
    Request" (it is the function wired in ``hooks.has_permission`` for the
    DocType, so it must carry BOTH controls):

      1. Project row-scoping (``scoped_has_permission``) — a scoped user
         (Fleet Supervisor / Fleet Project Manager, i.e. not an oversight role
         in ``UNSCOPED_ROLES``) may only act on documents in a project they
         hold a User Permission for; a project-less document they do not own is
         denied. This mirrors every other project-bearing Salis DocType and
         closes the hole the native User-Permission link match leaves open for
         NULL/blank ``project`` rows.
      2. Segregation of duties — when the action is a submit/write that moves
         the document into a Finance-exclusive state (Approved by Finance /
         Paid), deny it if the acting user is the requester or the original
         creator.

    The document is denied if EITHER control denies. Returns False to block;
    otherwise returns None to defer to Frappe's default permission resolution.
    """
    if getattr(doc, "doctype", None) != "Salis Payment Request":
        return None

    # (1) Project scope first. A False here is an unconditional deny regardless
    # of the action; None means scope does not object, so fall through to SoD.
    if scoped_has_permission(doc, ptype, user=user) is False:
        return False

    # (2) Segregation of duties (maker != checker) for Finance-exclusive moves.
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


# Decisions that represent an authorization outcome on an Approval Request.
APPROVAL_DECISION_STATES = {
    "Approved",
    "Rejected",
}


def approval_sod_has_permission(doc, ptype, user=None):
    """Project-scope an Approval Request AND block self-authorization of it.

    This single hook composes two independent denials for "Approval Request"
    (it is the function wired in ``hooks.has_permission`` for the DocType, so it
    must carry BOTH controls):

      1. Project row-scoping (``scoped_has_permission``) — a scoped user may
         only act on documents in a project they hold a User Permission for; a
         project-less document they do not own is denied. This mirrors every
         other project-bearing Salis DocType and closes the hole the native
         User-Permission link match leaves open for NULL/blank ``project`` rows.
      2. Segregation of duties — when the action is a submit/write that records
         an authorization decision (Approved / Rejected), deny it if the acting
         user is the requester or the original creator. This enforces
         approver != requester at the permission layer (maker != checker), in
         addition to the controller-level check in
         :meth:`ApprovalRequest._enforce_segregation_of_duties`, so a requester
         can never self-authorize regardless of how the transition is attempted.

    The document is denied if EITHER control denies. Returns False to block;
    otherwise returns None to defer to Frappe's default permission resolution.
    """
    if getattr(doc, "doctype", None) != "Approval Request":
        return None

    # (1) Project scope first; a False here denies unconditionally.
    if scoped_has_permission(doc, ptype, user=user) is False:
        return False

    # (2) Segregation of duties (maker != checker) for authorization decisions.
    if ptype not in ("submit", "write"):
        return None

    decision = getattr(doc, "decision", None)
    if decision not in APPROVAL_DECISION_STATES:
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
