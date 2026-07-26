# Copyright (c) 2026, AFMCO Support Services Co. Ltd
# [#a7e2jk]

import frappe

from apex.apex_core.utils import permission_scope
from apex.salis.utils import get_driver_for_session_user

UNSCOPED_ROLES = {
    "System Manager",
    "Fleet Manager",
    "Internal Auditor",
    # [#m3bfwj]
    "Finance Manager",
    # A-171: an oversight viewer, same shape as Internal Auditor. Its two Salis
    # Notifications alert it company-wide, so a project-scoped list would show
    # zero rows for the very vehicles it was just emailed about.
    "Government Relations Officer",
}


def _resolve_user(user=None):
    """Return the effective user, defaulting to the session user."""
    return permission_scope.resolve_user(user)


def _allowed_projects(user):
    """Project names the given user has an explicit User Permission for (cached).

    Thin wrapper over ``permission_scope.allowed_for`` binding the Project
    ``allow`` doctype and the ``apex_allowed_projects`` cache namespace. That
    namespace is DISTINCT from Habitat's ``apex_allowed_buildings`` so a Project
    scope and a Building scope can never collide in ``frappe.local.cache`` for the
    same user in one request. See ``permission_scope.allowed_for`` for the
    request-cache + no-cross-user-bleed invariant. Kept as a module-level function
    because the scoped permission test-suite (and the driver-chain fragments)
    resolve it by name.
    """
    return permission_scope.allowed_for(user, "Project", "apex_allowed_projects")


def _is_unscoped(user):
    """True when the user holds any oversight role that sees all projects."""
    return permission_scope.is_unscoped(user, UNSCOPED_ROLES)


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
    user is scoped but has no allowed projects, so they see nothing. Delegates
    the shared fragment logic to ``permission_scope.scope_condition``, injecting
    this module's own project resolvers so the Project oversight set + cache
    namespace stay bound here.
    """
    return permission_scope.scope_condition(
        user, _is_unscoped, _allowed_projects, column
    )


# [#iecjvo]
def report_project_scope(user=None):
    """Return ``(restrict, allowed_projects)`` for report-side project scoping.

    ``restrict`` is False for unscoped oversight roles (the report applies no extra
    filter — they see everything). When True the report must confine its rows to
    ``allowed_projects`` (an empty list means a scoped user with no permitted
    project, i.e. the report should return no rows). Thin wrapper over
    ``permission_scope.report_scope`` with this module's project resolvers.
    """
    return permission_scope.report_scope(user, _is_unscoped, _allowed_projects)


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
        # [#fdplqh]
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


# [#1hud7u]
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
    """Driver Suspension links a `driver`; the Driver role reads its own via if_owner."""
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
    """Vehicle Suspension reaches its tenant through `related_driver` (not `driver`); no
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
    Manifest).

    Trip Start Log resolves through ``dispatch_trip`` as well as its own ``route_plan``:
    that field is ``fetch_from`` ``dispatch_trip.route_plan``, and ``Document.insert``
    runs ``check_permission("create")`` (document.py:300) BEFORE ``_validate_links()``
    (:302) applies ``fetch_from`` — so at the create check it is EMPTY while the
    mandatory, never-fetched ``dispatch_trip`` is already set. Passenger Manifest needs
    the same fallback for a different reason (a manifest may be keyed by
    ``dispatch_trip`` alone), so the two share one branch. Dispatch Trip carries no
    ``dispatch_trip`` link, so the fallback is inert for it.
    """
    project = getattr(doc, "project", None)
    if project:
        return project

    doctype = getattr(doc, "doctype", None)
    if doctype in ("Dispatch Trip", "Trip Start Log", "Passenger Manifest"):
        route_plan = getattr(doc, "route_plan", None)
        if not route_plan:
            # [#qiimpb]
            dispatch_trip = getattr(doc, "dispatch_trip", None)
            if dispatch_trip:
                route_plan = frappe.db.get_value(
                    "Dispatch Trip", dispatch_trip, "route_plan"
                )
        if route_plan:
            return frappe.db.get_value("Route Plan", route_plan, "project")

    return None


def _is_unsaved(doc):
    """True when ``doc`` does not exist yet — i.e. this IS the create check.

    ``Document.insert`` sets ``__islocal`` (document.py:295) BEFORE
    ``check_permission("create")`` (:300) and deletes it once the row is written (:338),
    so the flag is the framework's own statement that this row is not stored yet. A doc
    read back from the database never carries it.

    Read INSTEAD OF ``ptype`` on purpose. The Salis ``has_permission`` handlers are
    deny-only and ptype-agnostic by contract — the same denial applies to every action —
    and this keeps that intact: what is being distinguished is the DOCUMENT, not the
    verb. A branch on ``ptype`` would have broken the contract; a branch on the
    document's storage state does not.
    """
    return bool(getattr(doc, "__islocal", False))


def _own_driver_basis(doc, user, driver_field="driver"):
    """True when the doc's driver — its own link, else its parent trip's — is ``user``'s.

    The create-time stand-in for ownership on the driver-owned DocTypes: a link to the
    acting user's own Salis Driver is a durable, verifiable fact about the row, which
    ``owner`` at the create check is not. Falls back to the parent Dispatch Trip's driver
    because Trip Start Log and Boarding Scan Log both fetch their own ``driver`` from it,
    so that link is still empty when the create check runs. Same basis
    ``dispatch_trip_has_permission`` already applies to the parent itself.
    """
    own_driver = get_driver_for_session_user(user)
    if not own_driver:
        return False
    if getattr(doc, driver_field, None) == own_driver:
        return True
    dispatch_trip = getattr(doc, "dispatch_trip", None)
    if dispatch_trip:
        return (
            frappe.db.get_value("Dispatch Trip", dispatch_trip, "driver") == own_driver
        )
    return False


# A-250 — the DocTypes among the eleven this handler governs whose OWN model makes
# `project` mandatory, so no legitimate create can ever be project-less. Deliberately
# a named set and not a blanket rule: a project-less create is a modelled business
# state on the other ten (see the A-250 survey note on
# ``_unanchored_create_is_denied``), and denying it there would blackout an ordinary
# flow rather than close a leak.
PROJECT_MANDATORY_ON_CREATE = frozenset({"Fuel Claim"})


def _unanchored_create_is_denied(doc):
    """True when ``doc`` is an UNSAVED row of a DocType that cannot be project-less.

    A-250 — the same tautology A-233 closed, in the project-less branch below.
    ``Document.insert`` stamps ``owner`` with the acting user (document.py:298) two
    statements before ``check_permission("create")`` (:300), so at the create check
    ``owner == user`` is always true: the ownership escape admitted EVERY project-less
    create. The discriminator is ``_is_unsaved`` (``__islocal``, document.py:295,
    deleted at :338), reused from A-233 rather than a second mechanism, so this handler
    stays deny-only and ptype-agnostic — what is distinguished is the document's storage
    state, not the action.

    IT IS APPLIED PER DOCTYPE ON PURPOSE. Applying it to all eleven would deny creates
    the business genuinely makes: a Transport Request is project-less for two of its
    three transport types (``TransportRequest.validate`` demands a project only for the
    Accommodation-to-Project Shuttle), a Route Plan fulfils such a request, a Passenger
    Manifest inherits that Route Plan, ``RentalSettlement.create_payment_request``
    raises a rental Salis Payment Request that belongs to an office and not a project,
    Issue is a shared core DocType whose non-fleet tickets have no project at all, an
    unallocated Salis Vehicle and a platform-level Fuel Exception Case both precede any
    project, and Vehicle Assignment / Fuel Request / Fuel Quota carry an OPTIONAL
    ``project`` beside a mandatory ``vehicle`` — a desk user who leaves that optional
    field blank would get "not permitted" instead of a field error.

    Where ``project`` is ``reqd`` the desk cannot produce a project-less create at all
    (``frappe.ui.form.check_mandatory`` gates the save call, save.js:20), so the only
    thing denied here is a programmatic insert that skips the mandatory check —
    ``ignore_mandatory``, or a caller that never populates the field. Nothing a human
    can reach is affected.
    """
    return (
        getattr(doc, "doctype", None) in PROJECT_MANDATORY_ON_CREATE
        and _is_unsaved(doc)
    )


def scoped_has_permission(doc, ptype, user=None):
    """Deny a scoped user acting on a doc outside their allowed projects.

    Returns False to block, or None to defer to Frappe's default permission
    resolution (which keeps standard role-based checks intact).

    A-250: on a project-less doc, ownership is still a valid basis for a row that
    ALREADY EXISTS, but not for an unsaved row of a DocType whose model forbids a
    project-less record — see ``_unanchored_create_is_denied`` for why that is a named
    set rather than a rule over every DocType wired here.
    """
    user = _resolve_user(user)
    if _is_unscoped(user):
        return None

    project = _doc_project(doc)
    if not project:
        # [#n18ea0]
        if getattr(doc, "owner", None) == user and not _unanchored_create_is_denied(doc):
            return None
        # [#kmesp4]
        return False

    if project not in _allowed_projects(user):
        return False

    return None


def _owner_or_project_has_permission(doc, user=None):
    """Project-scope a doc, treating OWNERSHIP as an independent access basis ON A ROW
    THAT ALREADY EXISTS.

    The rule behind every ``if_owner`` DocPerm in Salis: an unscoped oversight user
    defers to Frappe, the acting user's own STORED row is always allowed, and every other
    doc is confined to the user's allowed projects (a doc that anchors to no project
    fails closed). Returns False to block, else None to defer to Frappe's default
    resolution.

    Deliberately NOT ``scoped_has_permission``: that one denies a project-BEARING doc
    outside scope before any ownership test, which would block a Driver (who holds no
    Project User Permission) from opening their own project-tagged record.

    A-233 — OWNERSHIP IS NOT AN ACCESS BASIS ON AN UNSAVED ROW. ``Document.insert``
    stamps ``owner`` with the acting user (document.py:298) two statements before
    ``check_permission("create")`` (:300), so at the create check ``owner == user`` is a
    tautology: it records who is asking, not anything about the row. Testing it first
    therefore returned None for EVERY create and the project test below was never
    reached, letting a scoped user create a record under another scope's parent. Frappe's
    own core draws exactly this line — when User Permissions do not match a document it
    falls back to the if_owner permission set and forces ``create`` to 0
    (permissions.py:236-238, "if_owner does not come with create rights").

    So on an unsaved row the ownership branch is skipped and the row must anchor itself:
    its project must be in scope, or its driver link must resolve to the acting user's
    own Salis Driver (``_own_driver_basis``), which stays true after the insert. Once
    stored, ownership is a durable historical fact and is sufficient again, exactly as
    the ``if_owner`` DocPerms and the matching query fragments require.
    """
    user = _resolve_user(user)
    if _is_unscoped(user):
        return None

    unsaved = _is_unsaved(doc)

    # [#jc6moa]
    if not unsaved and getattr(doc, "owner", None) == user:
        return None

    project = _doc_project(doc)
    if project and project in _allowed_projects(user):
        return None

    if unsaved and _own_driver_basis(doc, user):
        return None

    # [#kk3lw5]
    return False


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
    access basis (the if_owner self-profile), so the acting user's own STORED row is
    always allowed; everything else is confined to the user's allowed projects.
    Using the shared ``scoped_has_permission`` here would be wrong — it denies a
    project-BEARING doc outside scope, which would block a Driver (who holds no
    Project User Permission) from reading their own project-tagged row.

    A-233: ownership is not a basis on an UNSAVED row (see
    ``_owner_or_project_has_permission``), so a scoped user's create must carry a
    ``project`` they are permitted for. Salis Driver's ``project`` is optional and never
    fetched, so an empty one at the create check is a real choice by the creator, not the
    ordering artefact it is on the fetched links — and a scoped user may no longer create
    an unanchored driver record that only they can then see. The Driver role holds no
    create DocPerm here, so no self-service path is affected.
    """
    return _owner_or_project_has_permission(doc, user)


def trip_start_log_has_permission(doc, ptype, user=None):
    """Project-scope direct Trip Start Log document access, but never block a
    Driver from acting on their OWN log.

    Trip Start Log reaches its project through the Dispatch Trip -> Route Plan
    chain (resolved by ``_doc_project``) AND grants the Driver role an
    ``if_owner`` DocPerm, while Fleet Supervisor / Fleet Project Manager get an
    unconditional read across every row. ``trip_start_log_query`` scopes the
    list/report view (project OR owner), so this hook mirrors it for the
    form view / REST resource / link reads.

    It mirrors ``salis_driver_has_permission`` exactly — same rule, so both now
    call the SAME ``_owner_or_project_has_permission`` and can never drift apart.
    Using the shared ``scoped_has_permission`` here would still be wrong: it
    denies a project-BEARING doc outside scope, which would block a Driver (who
    holds no Project User Permission) from opening their own project-tagged log.

    A-233: ownership is not a basis on an UNSAVED row (see
    ``_owner_or_project_has_permission``), so a create is decided by the mandatory
    ``dispatch_trip`` link instead — its Route Plan's project must be in scope, or the
    trip must be one dispatched to the acting user's own Salis Driver. That keeps the
    Driver's own create working (their ``driver`` link is still unfetched at the check,
    so the parent trip's driver is what resolves) while a scoped supervisor can no longer
    open a log against another project's trip.
    """
    return _owner_or_project_has_permission(doc, user)


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

    # [#daxlu1]
    own_driver = get_driver_for_session_user(user)
    if own_driver and getattr(doc, "driver", None) == own_driver:
        return None

    project = _doc_project(doc)
    if not project:
        return False

    if project not in _allowed_projects(user):
        return False

    return None


# [#oyj21f]
# [#dr2hpm]

def _driver_chain_project(doc, driver_field="driver"):
    """Resolve a doc's project through its Salis Driver link, or None.

    Falls back to the doc's ``vehicle`` link and then to its ``dispatch_trip`` link: both
    reach the project where the driver link cannot yet. ``Document.insert`` runs
    ``check_permission("create")`` (document.py:300) BEFORE ``_validate_links()`` (:302)
    applies ``fetch_from``, so at the create check every fetched driver link is EMPTY
    while the link it is fetched FROM is already set — ``vehicle.current_driver`` on
    Vehicle Incident / Vehicle Damage Write-Off / Vehicle Suspension, and
    ``dispatch_trip.driver`` on Boarding Scan Log. Without the vehicle fallback a scoped
    supervisor could not raise an incident on their own project's vehicle at all; without
    the trip fallback, once ownership stopped rescuing an unsaved row (A-233), they could
    not record a boarding scan on their own project's trip either.

    Still a no-op for Driver Attendance and Driver Suspension: both make ``driver``
    mandatory and never fetch it, and neither carries a ``vehicle`` or ``dispatch_trip``
    link, so nothing extra resolves and the caller's fail-closed branch is unchanged.
    """
    driver = getattr(doc, driver_field, None)
    if driver:
        project = frappe.db.get_value("Salis Driver", driver, "project")
        if project:
            return project

    vehicle = getattr(doc, "vehicle", None)
    if vehicle:
        return frappe.db.get_value("Salis Vehicle", vehicle, "project")

    dispatch_trip = getattr(doc, "dispatch_trip", None)
    if dispatch_trip:
        route_plan = frappe.db.get_value("Dispatch Trip", dispatch_trip, "route_plan")
        if route_plan:
            return frappe.db.get_value("Route Plan", route_plan, "project")
    return None


def _driver_chain_has_permission(doc, user=None, driver_field="driver", with_owner=False):
    """Deny a scoped user acting on a `driver`-linked doc outside their projects.

    Resolves the doc's project through ``driver_field -> Salis Driver -> project``.
    When ``with_owner`` is True (the doc grants the Driver role an if_owner perm),
    the acting user's own STORED row is always allowed — mirroring the OR-owner clause in
    the matching query. Returns False to block, else None to defer to Frappe's
    default resolution. Not folded into ``scoped_has_permission`` because that helper
    reads ``doc.project`` directly, which these indirect-tenant docs do not carry.

    A-233 — OWNERSHIP IS NOT AN ACCESS BASIS ON AN UNSAVED ROW. ``Document.insert``
    stamps ``owner`` with the acting user (document.py:298) two statements before
    ``check_permission("create")`` (:300), so at the create check ``owner == user`` is a
    tautology and the ``with_owner`` branch deferred EVERY create — a scoped user could
    attach an attendance, a suspension or a boarding scan to another project's driver.
    Frappe's own core draws the same line, forcing ``create`` to 0 in the if_owner
    fallback (permissions.py:236-238).

    On an unsaved row the ownership branch is therefore skipped and the driver chain
    decides. The Driver's own create is not collateral: ``_own_driver_basis`` accepts a
    row whose driver link — or whose parent trip's driver — is the acting user's own
    Salis Driver, which is durable where ``owner`` is not, so a Driver still records their
    own attendance while holding no Project User Permission. Still deny-only, and still
    never reads ``ptype``: the discriminator is the document's storage state, not the
    action.
    """
    user = _resolve_user(user)
    if _is_unscoped(user):
        return None

    unsaved = _is_unsaved(doc)

    # [#dr3own]
    if with_owner and not unsaved and getattr(doc, "owner", None) == user:
        return None

    project = _driver_chain_project(doc, driver_field=driver_field)
    if project and project in _allowed_projects(user):
        return None

    if with_owner and unsaved and _own_driver_basis(doc, user, driver_field=driver_field):
        return None

    # [#dr4nul]
    return False


def driver_attendance_has_permission(doc, ptype, user=None):
    """Mirror driver_attendance_query: project via driver, OR the Driver's own STORED row.

    A-233: ownership is not a basis on an UNSAVED row (see
    ``_driver_chain_has_permission``), so a create is decided by the mandatory ``driver``
    link — its project must be in scope, or it must be the acting user's own driver.
    """
    return _driver_chain_has_permission(doc, user=user, with_owner=True)


def driver_stop_has_permission(doc, ptype, user=None):
    """Mirror driver_stop_query: project via driver, OR the Driver's own STORED row.

    A-233: ownership is not a basis on an UNSAVED row (see
    ``_driver_chain_has_permission``), so a create is decided by the mandatory ``driver``
    link — a scoped user can no longer suspend another project's driver.
    """
    return _driver_chain_has_permission(doc, user=user, with_owner=True)


def boarding_scan_log_has_permission(doc, ptype, user=None):
    """Mirror boarding_scan_log_query: project via driver, OR the Driver's own STORED row.

    A-233: ownership is not a basis on an UNSAVED row (see
    ``_driver_chain_has_permission``). ``driver`` here is fetched from
    ``dispatch_trip.driver`` and so is empty at the create check, which is why
    ``_driver_chain_project`` also resolves through ``dispatch_trip``; the scan must
    belong to a trip in the acting user's projects, or to their own driver.
    """
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


# [#9w8q9b]

def operations_alert_query(user=None):
    """List/report scope for Operations Alert via the vehicle's project.

    Returns "" (no restriction) for unscoped oversight roles. A scoped user is
    confined to alerts whose `vehicle` resolves to a permitted project; alerts with
    no vehicle (no project anchor) are excluded. A scoped user with no allowed
    project sees nothing.
    """
    user = _resolve_user(user)
    if _is_unscoped(user):
        return ""

    projects = _allowed_projects(user)
    if not projects:
        return "1=0"

    escaped = ", ".join(frappe.db.escape(p) for p in projects)
    return (
        "`vehicle` in ("
        "select `name` from `tabSalis Vehicle` where `project` in ({values})"
        ")".format(values=escaped)
    )


def operations_alert_has_permission(doc, ptype, user=None):
    """Mirror operations_alert_query for direct form/REST/link access.

    Resolves the alert's project through `vehicle -> Salis Vehicle -> project` and
    denies a scoped user acting on an alert outside their permitted projects. A
    vehicle-less alert (no project anchor) is denied for scoped users. Returns False
    to block, else None to defer to Frappe's default resolution.
    """
    user = _resolve_user(user)
    if _is_unscoped(user):
        return None

    vehicle = getattr(doc, "vehicle", None)
    project = frappe.db.get_value("Salis Vehicle", vehicle, "project") if vehicle else None
    if not project:
        return False

    if project not in _allowed_projects(user):
        return False

    return None


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

    A-233 — THE PTYPE GATE ON CONTROL 2 IS LOAD-BEARING, NOT A SHORTCUT. Both identities
    control 2 compares against are unset or meaningless at the create check:
    ``requested_by`` is written in ``before_insert`` (document.py:303) and ``owner`` is
    stamped at :298, while ``check_permission("create")`` runs at :300. So on a create
    ``requested_by`` is empty and ``owner`` is ALWAYS the acting user — control 2 would
    self-deny every create the moment it were reached. The only reason it is not reached
    is the ``ptype not in ("submit", "write")`` return below. Anyone making this handler
    ptype-agnostic (as the other Salis handlers are) must first give control 2 a
    create-safe basis; deleting the gate alone reopens this. Control 1 is unaffected:
    ``project`` is a direct, never-fetched Link and is already set at the create check.
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
