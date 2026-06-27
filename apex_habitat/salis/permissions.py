# Copyright (c) 2026, AFMCO Support Services Co. Ltd
# [#a7e2jk]

import frappe

from apex_habitat.salis.utils import get_driver_for_user

UNSCOPED_ROLES = {
    "System Manager",
    "Fleet Manager",
    "Internal Auditor",
    # [#m3bfwj]
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


def _project_supervisor(project):
    """Return the supervisor User scoped to ``project``, or None.

    The reverse of ``_allowed_projects``: a project's supervisor is the enabled,
    non-oversight User who holds a User Permission for that Project. When several
    qualify, the lowest user id is returned deterministically so the resolution is
    stable. Oversight roles are excluded — they see every project and are not a
    project's owning supervisor.
    """
    if not project:
        return None
    users = frappe.get_all(
        "User Permission",
        filters={"allow": "Project", "for_value": project},
        pluck="user",
        order_by="user asc",
    )
    for user in users:
        if user in ("Administrator", "Guest"):
            continue
        if not frappe.db.get_value("User", user, "enabled"):
            continue
        if _is_unscoped(user):
            continue
        return user
    return None


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


# [#rptscope] Script Reports run on frappe.get_all, which forces ignore_permissions
# (frappe/__init__.py get_all forces ignore_permissions), so the project row-scoping
# the desk list gets via permission_query_conditions is bypassed in report code. This
# helper consolidates the re-application that the Salis reports had duplicated inline:
# it returns the project filter a report must AND onto its own get_all so a project-
# scoped user sees only their projects' rows while the UNSCOPED_ROLES oversight roles
# stay unrestricted.
def report_project_scope(user=None):
    """Return ``(restrict, allowed_projects)`` for report-side project scoping.

    ``restrict`` is False for unscoped oversight roles (the report applies no extra
    filter — they see everything). When True the report must confine its rows to
    ``allowed_projects`` (an empty list means a scoped user with no permitted
    project, i.e. the report should return no rows).
    """
    user = _resolve_user(user)
    if _is_unscoped(user):
        return False, []
    return True, _allowed_projects(user)


# [#89nxdl]

def vehicle_assignment_query(user=None):
    return _project_condition(user)


def fuel_request_query(user=None):
    return _project_condition(user)


def transport_request_query(user=None):
    return _project_condition(user)


def route_plan_query(user=None):
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


def _own_driver_trips_condition(user):
    """SQL fragment matching Dispatch Trips assigned to the acting user's driver.

    Resolves the user -> Employee -> Salis Driver chain in SQL so the fragment
    holds the trip's `driver` column to a driver linked to ``user``. Mirrors the
    driver-own access basis used across the Salis driver-linked DocTypes — a Driver
    reads the trips dispatched to them without needing a Project User Permission."""
    return (
        "`driver` in ("
        "select `name` from `tabSalis Driver` where `employee` in ("
        "select `name` from `tabEmployee` where `user_id` = {user}"
        "))".format(user=frappe.db.escape(user))
    )


def dispatch_trip_query(user=None):
    """Dispatch Trip has no own `project` field; it links to a Route Plan.

    Scope it through the parent Route Plan's project so the same project
    boundary applies. The fragment references the Dispatch Trip table's
    `route_plan` column via a subquery on `tabRoute Plan`.

    Like the other driver-linked Salis DocTypes, a Driver reads the trips
    dispatched to them even without a Project User Permission: the project scope is
    OR-ed with `driver = my driver` so a scoped Driver who holds no project still
    sees their own trips, while a scoped supervisor stays confined to their projects.
    Returns "" (no restriction) for unscoped oversight roles.
    """
    user = _resolve_user(user)
    if _is_unscoped(user):
        return ""

    own = _own_driver_trips_condition(user)

    projects = _allowed_projects(user)
    if not projects:
        # No project scope: a Driver still sees their own trips; any other scoped
        # user (no driver) is held to that same own-trips clause (matches nothing).
        return own

    escaped = ", ".join(frappe.db.escape(p) for p in projects)
    in_scope = (
        "`route_plan` in ("
        "select `name` from `tabRoute Plan` where `project` in ({values})"
        ")".format(values=escaped)
    )
    return "({in_scope} or {own})".format(in_scope=in_scope, own=own)


def trip_start_log_query(user=None):
    """Trip Start Log has no own `project` field; it links to a Dispatch Trip,
    which in turn links to a Route Plan carrying the project.

    Scope it through that chain so the same project boundary applies as on every
    other Salis transactional DocType. The fragment restricts the Trip Start Log
    table's `route_plan` column (populated by fetch from the Dispatch Trip) to the
    user's allowed projects via a subquery on `tabRoute Plan`.

    Like Salis Driver, the Driver role reads its OWN logs via an ``if_owner``
    DocPerm, so we OR the project scope with ``owner = me`` (mirroring
    ``salis_driver_query``): a Driver who holds no Project User Permission still
    sees the Trip Start Logs they created, while a scoped supervisor remains
    confined to the logs in their permitted projects. Returns "" (no restriction)
    for unscoped oversight roles.
    """
    user = _resolve_user(user)
    if _is_unscoped(user):
        return ""

    own = "`owner` = {0}".format(frappe.db.escape(user))

    projects = _allowed_projects(user)
    if not projects:
        # [#7eocrd]
        return own

    escaped = ", ".join(frappe.db.escape(p) for p in projects)
    in_scope = (
        "`route_plan` in ("
        "select `name` from `tabRoute Plan` where `project` in ({values})"
        ")".format(values=escaped)
    )
    return "({in_scope} or {own})".format(in_scope=in_scope, own=own)


def salis_vehicle_query(user=None):
    """Salis Vehicle carries a direct `project` Link, so it is scoped exactly like
    the other project-bearing master/transactional DocTypes: a scoped user sees
    only vehicles in their allowed projects; oversight roles see all. This closes
    the desk-list leak where a scoped Fleet Supervisor could enumerate every
    project's vehicles at /app/salis-vehicle (the Dispatch Board already filtered
    by project, but the standard list view did not)."""
    return _project_condition(user)


def salis_driver_query(user=None):
    """Salis Driver carries a direct `project` Link, scoped like Salis Vehicle —
    with one addition: the Driver role reads its OWN profile via an ``if_owner``
    DocPerm. Frappe ANDs this query fragment with the ``owner = me`` clause it adds
    for an if_owner match, so a bare project restriction (``1=0`` for a Driver who
    holds no Project User Permission) would make a Driver unable to see even their
    own row. We therefore OR the project scope with ``owner = me`` so the self-
    profile path survives while a scoped supervisor is still confined to the
    drivers in their permitted projects.

    Returns "" (no restriction) for unscoped oversight roles."""
    user = _resolve_user(user)
    if _is_unscoped(user):
        return ""

    own = "`owner` = {0}".format(frappe.db.escape(user))

    projects = _allowed_projects(user)
    if not projects:
        # [#5hk4nq]
        return own

    escaped = ", ".join(frappe.db.escape(p) for p in projects)
    return "(`project` in ({values}) or {own})".format(values=escaped, own=own)


def passenger_manifest_query(user=None):
    """Passenger Manifest has no own `project` field; it links to a Route Plan
    (and a Dispatch Trip, which itself links to a Route Plan) that carries the
    project. Scope it through either link so the same project boundary applies as
    on every other Salis movement record. Without this a scoped Fleet Supervisor
    could read passenger lists/counts for another project's transport at
    /app/passenger-manifest.

    A manifest can be keyed by ``route_plan`` directly OR only by ``dispatch_trip``
    (neither field is mandatory and there is no fetch between them), so the
    fragment admits a row whose Route Plan — reached by EITHER path — is in scope.
    """
    user = _resolve_user(user)
    if _is_unscoped(user):
        return ""

    projects = _allowed_projects(user)
    if not projects:
        return "1=0"

    escaped = ", ".join(frappe.db.escape(p) for p in projects)
    in_scope_route_plans = (
        "select `name` from `tabRoute Plan` where `project` in ({values})".format(
            values=escaped
        )
    )
    return (
        "(`route_plan` in ({rp}) or `dispatch_trip` in ("
        "select `name` from `tabDispatch Trip` where `route_plan` in ({rp})"
        "))".format(rp=in_scope_route_plans)
    )


# Indirect-tenant DocTypes: no own `project`, but a Salis Driver link carries it.
# Scope each through `driver -> Salis Driver -> project`; where a Driver `if_owner`
# DocPerm exists (Driver Attendance / Driver Stop / Boarding Scan Log) OR the
# `owner = me` clause so the self-record path survives (mirrors salis_driver_query).
# [#dr1tz9]

def _driver_chain_condition(user, column="`driver`", with_owner=False):
    """SQL fragment scoping a `driver`-link column through Salis Driver's project.

    `column` is the back-quoted driver-link column on the target table (e.g.
    ```driver``` or ```related_driver```). Returns "" for unscoped
    oversight roles. When ``with_owner`` is True the project scope is OR-ed with
    ``owner = me`` (for DocTypes whose Driver role reads its own rows via if_owner);
    a scoped user with no allowed projects then falls back to their own rows, while
    a non-owner DocType (``with_owner`` False) yields ``1=0``.
    """
    user = _resolve_user(user)
    if _is_unscoped(user):
        return ""

    own = "`owner` = {0}".format(frappe.db.escape(user))

    projects = _allowed_projects(user)
    if not projects:
        # [#dr0own]
        return own if with_owner else "1=0"

    escaped = ", ".join(frappe.db.escape(p) for p in projects)
    in_scope = (
        "{column} in ("
        "select `name` from `tabSalis Driver` where `project` in ({values})"
        ")".format(column=column, values=escaped)
    )
    if with_owner:
        return "({in_scope} or {own})".format(in_scope=in_scope, own=own)
    return in_scope


def driver_attendance_query(user=None):
    """Driver Attendance links a `driver` (Salis Driver carries the project) and
    grants the Driver role an `if_owner` read DocPerm, so scope project-OR-owner."""
    return _driver_chain_condition(user, with_owner=True)


def driver_stop_query(user=None):
    """Driver Stop links a `driver`; the Driver role reads its own via if_owner."""
    return _driver_chain_condition(user, with_owner=True)


def boarding_scan_log_query(user=None):
    """Boarding Scan Log links a `driver`; the Driver role reads its own via
    if_owner. (It also links a dispatch_trip, but `driver` is the durable tenant
    anchor present on every row.)"""
    return _driver_chain_condition(user, with_owner=True)


def vehicle_damage_write_off_query(user=None):
    """Vehicle Damage Write-Off links a `driver`; no Driver DocPerm, so pure
    project scope through Salis Driver."""
    return _driver_chain_condition(user, with_owner=False)


def vehicle_incident_query(user=None):
    """Vehicle Incident links a `driver`; no Driver DocPerm -> pure project scope."""
    return _driver_chain_condition(user, with_owner=False)


def driver_clearance_query(user=None):
    """Driver Clearance links a `driver`; no Driver DocPerm -> pure project scope."""
    return _driver_chain_condition(user, with_owner=False)


def vehicle_stop_query(user=None):
    """Vehicle Stop reaches its tenant through `related_driver` (not `driver`); no
    Driver DocPerm -> pure project scope through Salis Driver."""
    return _driver_chain_condition(user, column="`related_driver`", with_owner=False)


def movement_cost_transfer_query(user=None):
    """Movement Cost Transfer carries TWO direct project Links (`from_project`,
    `to_project`) rather than a single `project`. A scoped user may see a transfer
    touching EITHER a from- or a to-project they are permitted for, so the fragment
    admits a row whose either endpoint is in scope. "" for oversight; "1=0" when a
    scoped user has no allowed projects. (Consistency with the other tenant docs;
    no Driver DocPerm, so no owner clause.)"""
    user = _resolve_user(user)
    if _is_unscoped(user):
        return ""

    projects = _allowed_projects(user)
    if not projects:
        return "1=0"

    escaped = ", ".join(frappe.db.escape(p) for p in projects)
    return "(`from_project` in ({v}) or `to_project` in ({v}))".format(v=escaped)


# [#2huj0w]

def _doc_project(doc):
    """Resolve the project a document belongs to, including the docs that reach
    their project through a Route Plan (Dispatch Trip, Trip Start Log, Passenger
    Manifest)."""
    project = getattr(doc, "project", None)
    if project:
        return project

    doctype = getattr(doc, "doctype", None)
    if doctype in ("Dispatch Trip", "Trip Start Log"):
        route_plan = getattr(doc, "route_plan", None)
        if route_plan:
            return frappe.db.get_value("Route Plan", route_plan, "project")

    if doctype == "Passenger Manifest":
        # [#qiimpb]
        route_plan = getattr(doc, "route_plan", None)
        if not route_plan:
            dispatch_trip = getattr(doc, "dispatch_trip", None)
            if dispatch_trip:
                route_plan = frappe.db.get_value(
                    "Dispatch Trip", dispatch_trip, "route_plan"
                )
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
        # [#n18ea0]
        if getattr(doc, "owner", None) == user:
            return None
        # [#kmesp4]
        return False

    if project not in _allowed_projects(user):
        return False

    return None


def salis_driver_has_permission(doc, ptype, user=None):
    """Project-scope direct Salis Driver document access, but never block a
    Driver from reading their OWN profile.

    Salis Driver carries a direct ``project`` Link AND grants the Driver role an
    ``if_owner`` read DocPerm, while Fleet Supervisor / Fleet Project Manager get
    an unconditional read across every row. ``salis_driver_query`` scopes the
    list/report view (project OR owner), but without a matching ``has_permission``
    hook the form view / REST resource / link reads were governed only by those
    role DocPerms, letting a project-scoped supervisor open any other project's
    driver record directly. This closes that direct-access leak.

    It mirrors ``salis_driver_query`` exactly: ownership is an independent, valid
    access basis (the if_owner self-profile), so the acting user's own row is
    always allowed; everything else is confined to the user's allowed projects.
    Using the shared ``scoped_has_permission`` here would be wrong — it denies a
    project-BEARING doc outside scope, which would block a Driver (who holds no
    Project User Permission) from reading their own project-tagged row.
    """
    user = _resolve_user(user)
    if _is_unscoped(user):
        return None

    # [#jc6moa]
    if getattr(doc, "owner", None) == user:
        return None

    project = _doc_project(doc)
    if not project:
        # [#kk3lw5]
        return False

    if project not in _allowed_projects(user):
        return False

    return None


def trip_start_log_has_permission(doc, ptype, user=None):
    """Project-scope direct Trip Start Log document access, but never block a
    Driver from acting on their OWN log.

    Trip Start Log reaches its project through the Dispatch Trip -> Route Plan
    chain (resolved by ``_doc_project``) AND grants the Driver role an
    ``if_owner`` DocPerm, while Fleet Supervisor / Fleet Project Manager get an
    unconditional read across every row. ``trip_start_log_query`` scopes the
    list/report view (project OR owner), so this hook mirrors it for the
    form view / REST resource / link reads.

    It mirrors ``salis_driver_has_permission`` exactly: ownership is an
    independent, valid access basis (the if_owner self record), so the acting
    user's own row is always allowed; everything else is confined to the user's
    allowed projects. Using the shared ``scoped_has_permission`` here would be
    wrong — it denies a project-BEARING doc outside scope, which would block a
    Driver (who holds no Project User Permission) from opening their own
    project-tagged log.
    """
    user = _resolve_user(user)
    if _is_unscoped(user):
        return None

    # [#dz5z4x]
    if getattr(doc, "owner", None) == user:
        return None

    project = _doc_project(doc)
    if not project:
        # [#ocig5t]
        return False

    if project not in _allowed_projects(user):
        return False

    return None


def dispatch_trip_has_permission(doc, ptype, user=None):
    """Project-scope direct Dispatch Trip access, but never block a Driver from
    reading their OWN trip.

    Dispatch Trip reaches its project through the Route Plan chain (resolved by
    ``_doc_project``); the prior hook (``scoped_has_permission``) enforced that
    project boundary alone, which would deny a Driver opening a trip dispatched to
    them — a Driver holds no Project User Permission and does not own the trip
    (dispatchers create it). This mirrors ``dispatch_trip_query``: a trip whose
    ``driver`` resolves to the acting user's Salis Driver is always allowed; every
    other doc is confined to the user's allowed projects. The driver-own basis is
    independent and valid, exactly like the if_owner basis on Trip Start Log /
    Salis Driver.

    Returns False to block, else None to defer to Frappe's default resolution.
    """
    user = _resolve_user(user)
    if _is_unscoped(user):
        return None

    # Driver-own: the trip is dispatched to this user's Salis Driver.
    own_driver = get_driver_for_user(user)
    if own_driver and getattr(doc, "driver", None) == own_driver:
        return None

    project = _doc_project(doc)
    if not project:
        return False

    if project not in _allowed_projects(user):
        return False

    return None


# has_permission mirrors for the indirect-tenant DocTypes (form view / REST
# resource / link reads), matching the permission_query_conditions above so the
# direct-access path enforces the same project boundary as the list/report view.
# [#dr2hpm]

def _driver_chain_project(doc, driver_field="driver"):
    """Resolve a doc's project through its Salis Driver link, or None."""
    driver = getattr(doc, driver_field, None)
    if not driver:
        return None
    return frappe.db.get_value("Salis Driver", driver, "project")


def _driver_chain_has_permission(doc, user=None, driver_field="driver", with_owner=False):
    """Deny a scoped user acting on a `driver`-linked doc outside their projects.

    Resolves the doc's project through ``driver_field -> Salis Driver -> project``.
    When ``with_owner`` is True (the doc grants the Driver role an if_owner perm),
    the acting user's own row is always allowed — mirroring the OR-owner clause in
    the matching query. Returns False to block, else None to defer to Frappe's
    default resolution. Not folded into ``scoped_has_permission`` because that helper
    reads ``doc.project`` directly, which these indirect-tenant docs do not carry.
    """
    user = _resolve_user(user)
    if _is_unscoped(user):
        return None

    # [#dr3own]
    if with_owner and getattr(doc, "owner", None) == user:
        return None

    project = _driver_chain_project(doc, driver_field=driver_field)
    if not project:
        # [#dr4nul]
        return None if with_owner and getattr(doc, "owner", None) == user else False

    if project not in _allowed_projects(user):
        return False

    return None


def driver_attendance_has_permission(doc, ptype, user=None):
    """Mirror driver_attendance_query: project via driver, OR the Driver's own row."""
    return _driver_chain_has_permission(doc, user=user, with_owner=True)


def driver_stop_has_permission(doc, ptype, user=None):
    """Mirror driver_stop_query: project via driver, OR the Driver's own row."""
    return _driver_chain_has_permission(doc, user=user, with_owner=True)


def boarding_scan_log_has_permission(doc, ptype, user=None):
    """Mirror boarding_scan_log_query: project via driver, OR the Driver's own row."""
    return _driver_chain_has_permission(doc, user=user, with_owner=True)


def vehicle_damage_write_off_has_permission(doc, ptype, user=None):
    """Mirror vehicle_damage_write_off_query: pure project scope via driver."""
    return _driver_chain_has_permission(doc, user=user, with_owner=False)


def vehicle_incident_has_permission(doc, ptype, user=None):
    """Mirror vehicle_incident_query: pure project scope via driver."""
    return _driver_chain_has_permission(doc, user=user, with_owner=False)


def driver_clearance_has_permission(doc, ptype, user=None):
    """Mirror driver_clearance_query: pure project scope via driver."""
    return _driver_chain_has_permission(doc, user=user, with_owner=False)


def vehicle_stop_has_permission(doc, ptype, user=None):
    """Mirror vehicle_stop_query: pure project scope via the related_driver link."""
    return _driver_chain_has_permission(doc, user=user, driver_field="related_driver", with_owner=False)


def movement_cost_transfer_has_permission(doc, ptype, user=None):
    """Mirror movement_cost_transfer_query: allow if EITHER from/to project is in
    the scoped user's allowed set; deny otherwise. A transfer with neither endpoint
    set is treated as project-less and deferred (no tenant to enforce)."""
    user = _resolve_user(user)
    if _is_unscoped(user):
        return None

    from_project = getattr(doc, "from_project", None)
    to_project = getattr(doc, "to_project", None)
    if not from_project and not to_project:
        # [#dr5nul]
        return None

    allowed = _allowed_projects(user)
    if (from_project and from_project in allowed) or (to_project and to_project in allowed):
        return None
    return False


# [#m6o851]

# [#6wflvq]
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

    # [#9u08t6]
    if scoped_has_permission(doc, ptype, user=user) is False:
        return False

    # [#n6cjcu]
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
