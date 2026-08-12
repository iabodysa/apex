# Copyright (c) 2026, afmcoltd
"""Project row-scoping for Salis.

Every scoped Salis DocType is confined to its project, reached one of five ways, and
WHICH WAY IS A PROPERTY OF THE DOCTYPE rather than of a function:

    column    the doc stores the project itself (``project``)
    dual      the doc has two endpoints (``from_project`` / ``to_project``)
    hop       the project is one link away (Dispatch Trip -> Route Plan -> project)
    manifest  the project is reachable by EITHER of two links (Passenger Manifest)
    driver    the project hangs off a Salis Driver link (``driver``/``related_driver``)

and, orthogonally, a DocType may carry an OWN-ROW BASIS — a route that bypasses the
project entirely, because a Driver holds no Project User Permission yet must reach
their own rows:

    own="owner"    the DocType grants the Driver role an ``if_owner`` DocPerm
    own="driver"   the row names the acting user's Salis Driver (Dispatch Trip)

``SALIS_SCOPE`` maps DocType to that pair plus the document-level rule. The list
fragment and the document check both dispatch off that SAME table, so they can never
disagree about what is in scope, and adding a scoped DocType is a table row rather than
a new function per hook.

Three invariants hold on every path and are why the edge cases look asymmetric:

The document rules NEVER return True and never branch on ``ptype`` (one exception, named
on ``payment_sod_has_permission``): deny-only, so they narrow and never widen.

The block at the foot of this file is COMPATIBILITY ONLY: wrappers holding no rule, each
forwarding to a dispatcher with its own ``scope_for``, which ``hooks.py`` does not route
through. They exist so callers outside this module can still resolve by FUNCTION NAME.
"""

import frappe

from apex.apex_core.utils import permission_scope
from apex.salis.utils import get_driver_for_session_user

UNSCOPED_ROLES = {
    "System Manager",
    "Fleet Manager",
    "Internal Auditor",
    "Finance Manager",
    "Government Relations Officer",
}

PROJECT = "project"


def _resolve_user(user=None):
    """Return the effective user, defaulting to the session user."""
    return permission_scope.resolve_user(user)


def _allowed_projects(user):
    """Project names the given user has an explicit User Permission for (cached).

    Thin wrapper over ``permission_scope.allowed_for`` binding the Project ``allow``
    doctype and the ``apex_allowed_projects`` cache namespace. That namespace is
    DISTINCT from Habitat's ``apex_allowed_buildings`` and Logistay's
    ``apex_allowed_companies`` so two scopes can never collide in
    ``frappe.local.cache`` for the same user in one request. Kept as a module-level
    function because ``apex.salis.api.dispatch_board`` imports it directly and the
    scoped permission test-suite resolves it by name.
    """
    return permission_scope.allowed_for(user, "Project", "apex_allowed_projects")


def _allowed_projects_for(user, doctype):
    """``_allowed_projects`` narrowed to the permissions that apply to ``doctype``.

    A User Permission carrying ``applicable_for`` grants its project for that one
    DocType; without this narrowing it would unlock every project-scoped DocType.
    See ``permission_scope.for_doctype``.
    """
    return permission_scope.for_doctype(user, "Project", doctype, _allowed_projects(user))


def _is_unscoped(user):
    """True when the user holds any oversight role that sees all projects."""
    return permission_scope.is_unscoped(user, UNSCOPED_ROLES)


def report_project_scope(user=None, doctype=None):
    """Return ``(restrict, allowed_projects)`` for report-side project scoping.

    ``restrict`` is False for unscoped oversight roles (the report applies no extra
    filter — they see everything). When True the report must confine its rows to
    ``allowed_projects``; an empty list means a scoped user with no permitted project,
    i.e. the report should return no rows.
    """
    return permission_scope.report_scope(
        user, _is_unscoped, _allowed_projects, allow="Project", doctype=doctype
    )


def _column(rule="scoped", own=None):
    """Project stored on the doc itself."""
    return ("column", {"field": PROJECT, "own": own, "rule": rule})


def _dual():
    """Project at either of two endpoints."""
    return (
        "dual",
        {"first": "from_project", "second": "to_project", "own": None, "rule": "dual"},
    )


def _hop(field, doctype, rule, own=None):
    """Project one link away, reached through ``field`` -> ``doctype``.``project``."""
    return ("hop", {"field": field, "doctype": doctype, "own": own, "rule": rule})


def _manifest():
    """Project reachable through ``route_plan`` OR ``dispatch_trip`` -> ``route_plan``."""
    return ("manifest", {"own": None, "rule": "scoped"})


def _driver(field="driver", own=None):
    """Project hanging off a Salis Driver link."""
    return ("driver", {"field": field, "own": own, "rule": "driver_chain"})


def _quote(field):
    """Backtick-quote one column name. The only place this module writes a quote."""
    return "`{0}`".format(field)


SALIS_SCOPE = {
    "Vehicle Assignment": _column(),
    "Fuel Request": _column(rule="owner_or_project", own="owner"),
    "Transport Request": _column(),
    "Route Plan": _column(),
    "Issue": _column(rule="owner_or_project", own="owner"),
    "Fuel Claim": _column(),
    "Fuel Quota": _column(),
    "Fuel Exception Case": _column(),
    "Salis Vehicle": _column(),
    "Salis Payment Request": _column(rule="payment_sod"),
    "Salis Driver": _column(rule="owner_or_project", own="owner"),
    "Dispatch Trip": _hop("route_plan", "Route Plan", rule="dispatch_trip", own="driver"),
    "Trip Start Log": _hop("route_plan", "Route Plan", rule="owner_or_project", own="owner"),
    "Passenger Manifest": _manifest(),
    "Driver Attendance": _driver(own="owner"),
    "Driver Suspension": _driver(own="owner"),
    "Boarding Scan Log": _driver(own="owner"),
    "Vehicle Damage Write-Off": _driver(),
    "Vehicle Incident": _driver(own="owner"),
    "Driver Clearance": _driver(),
    "Vehicle Suspension": _driver(field="related_driver"),
    "Movement Cost Transfer": _dual(),
}

ROUTE_PLAN_ANCHORED = frozenset(
    doctype
    for doctype, (kind, spec) in SALIS_SCOPE.items()
    if kind == "manifest" or (kind == "hop" and spec["doctype"] == "Route Plan")
)

PROJECT_MANDATORY_ON_CREATE = frozenset({"Fuel Claim"})


def _own_driver_trips_condition(user):
    """SQL fragment matching rows whose ``driver`` is the acting user's own.

    Resolves the user -> Employee -> Salis Driver chain in SQL so the fragment holds
    the row's ``driver`` column to a driver linked to ``user``. A Driver reads the
    trips dispatched to them without needing a Project User Permission.
    """
    return (
        "`driver` in ("
        "select `name` from `tabSalis Driver` where `employee` in ("
        "select `name` from `tabEmployee` where `user_id` = {user}"
        "))".format(user=frappe.db.escape(user))
    )


def _own_clause(spec, user):
    """SQL fragment for the DocType's own-row basis, or None when it has none.

    This is what keeps a Driver's own rows reachable when they hold no project at all.
    Frappe AND-s its own ``owner = me`` match onto the fragment for an ``if_owner``
    DocPerm, so a bare project restriction would collapse such a user's list to
    nothing; the OR here is what survives that join.
    """
    own = spec.get("own")
    if own == "owner":
        return "`owner` = {0}".format(frappe.db.escape(user))
    if own == "driver":
        return _own_driver_trips_condition(user)
    return None


def _render_column(spec, escaped):
    """``project in (...)`` — the project stored on the row."""
    return "{column} in ({values})".format(column=_quote(spec["field"]), values=escaped)


def _render_dual(spec, escaped):
    """Either endpoint in scope, as ONE fragment (Frappe AND-joins separate ones)."""
    return "({first} in ({values}) or {second} in ({values}))".format(
        first=_quote(spec["first"]), second=_quote(spec["second"]), values=escaped
    )


def _render_hop(spec, escaped):
    """The project one link away, as a subquery on the linked DocType."""
    return "{column} in (select `name` from `tab{doctype}` where `project` in ({values}))".format(
        column=_quote(spec["field"]), doctype=spec["doctype"], values=escaped
    )


def _render_driver(spec, escaped):
    """The project hanging off the row's Salis Driver link."""
    return (
        "{column} in ("
        "select `name` from `tabSalis Driver` where `project` in ({values})"
        ")".format(column=_quote(spec["field"]), values=escaped)
    )


def _render_manifest(spec, escaped):
    """A manifest keyed by ``route_plan`` directly OR only by ``dispatch_trip``.

    Neither field is mandatory and there is no fetch between them, so the fragment
    admits a row whose Route Plan — reached by EITHER path — is in scope. The OR is
    inside this one fragment for the reason recorded on ``_render_dual``.
    """
    del spec
    route_plans = "select `name` from `tabRoute Plan` where `project` in ({values})".format(
        values=escaped
    )
    return (
        "(`route_plan` in ({rp}) or `dispatch_trip` in ("
        "select `name` from `tabDispatch Trip` where `route_plan` in ({rp})"
        "))".format(rp=route_plans)
    )


FRAGMENTS = {
    "column": _render_column,
    "dual": _render_dual,
    "hop": _render_hop,
    "driver": _render_driver,
    "manifest": _render_manifest,
}


def _fragment(kind, spec, values):
    """Render one scope strategy against the user's allowed projects.

    ``values`` is non-empty — the caller has already answered the unscoped and
    no-project cases, so every renderer emits a real restriction. An unrecognised kind
    renders "1=0" rather than falling through to no restriction: an unknown strategy
    must fail CLOSED.
    """
    render = FRAGMENTS.get(kind)
    if not render:
        return "1=0"
    return render(spec, ", ".join(frappe.db.escape(value) for value in values))


def project_scope_query(user=None, doctype=None, scope_for=None):
    """WHERE fragment scoping ``doctype``'s list/report view to the user's projects.

    ``doctype`` MUST stay in this signature: ``frappe.call`` drops any keyword the
    callee does not declare, so a signature without it would receive no DocType,
    silently skip the ``applicable_for`` narrowing in ``_allowed_projects_for``, and
    widen every scope on the tenant axis.

    ``scope_for`` is never passed by frappe. It exists for the named compatibility
    wrappers at the foot of this module, which must select their own DocType's strategy
    while leaving ``doctype`` — the ``applicable_for`` narrowing key — exactly as their
    caller supplied it.

    THE NO-PROJECT BRANCH IS NOT UNIFORMLY "1=0". A DocType carrying an own-row basis
    returns that clause ALONE, because the users who reach those rows without a project
    (Drivers) are exactly the ones the DocType exists for. Only a DocType with no own
    basis blacks out.

    An unknown DocType falls back to the plain ``project`` column, which is what the
    hand-written per-DocType functions did and the shape 10 of the 23 scoped DocTypes
    use.

    """
    user = _resolve_user(user)
    if _is_unscoped(user):
        return ""

    kind, spec = SALIS_SCOPE.get(scope_for or doctype) or _column()
    own = _own_clause(spec, user)

    projects = _allowed_projects_for(user, doctype)
    if not projects:
        return own or "1=0"

    in_scope = _fragment(kind, spec, projects)
    if own:
        return "({in_scope} or {own})".format(in_scope=in_scope, own=own)
    return in_scope


def _doc_project(doc):
    """Resolve the project a document belongs to, including the route-plan chain.

    ``ROUTE_PLAN_ANCHORED`` is derived from ``SALIS_SCOPE`` itself, so the set of
    DocTypes that reach their project through a Route Plan cannot drift from the
    strategy the list fragment uses for them.

    """
    project = getattr(doc, PROJECT, None)
    if project:
        return project

    doctype = getattr(doc, "doctype", None)
    if doctype in ROUTE_PLAN_ANCHORED:
        route_plan = getattr(doc, "route_plan", None)
        if not route_plan:
            dispatch_trip = getattr(doc, "dispatch_trip", None)
            if dispatch_trip:
                route_plan = frappe.db.get_value("Dispatch Trip", dispatch_trip, "route_plan")
        if route_plan:
            return frappe.db.get_value("Route Plan", route_plan, PROJECT)

    return None


def _driver_chain_project(doc, driver_field="driver"):
    """Resolve a doc's project through its Salis Driver link, or None.

    Still a no-op for Driver Attendance and Driver Suspension: both make ``driver``
    mandatory and never fetch it, and neither carries a ``vehicle`` or
    ``dispatch_trip`` link, so nothing extra resolves and the caller's fail-closed
    branch is unchanged.

    """
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
        route_plan = frappe.db.get_value("Dispatch Trip", dispatch_trip, "route_plan")
        if route_plan:
            return frappe.db.get_value("Route Plan", route_plan, PROJECT)
    return None


def _is_unsaved(doc):
    """True when ``doc`` does not exist yet — i.e. this IS the create check.

    Read INSTEAD OF ``ptype`` on purpose. The Salis document rules are deny-only and
    ptype-agnostic by contract — the same denial applies to every action — and this
    keeps that intact: what is being distinguished is the DOCUMENT, not the verb. A
    branch on ``ptype`` would have broken the contract; a branch on the document's
    storage state does not.

    """
    return bool(getattr(doc, "__islocal", False))


def _own_driver_basis(doc, user, driver_field="driver"):
    """True when the doc's driver — its own link, else its parent trip's — is ``user``'s.

    The create-time stand-in for ownership on the driver-owned DocTypes: a link to the
    acting user's own Salis Driver is a durable, verifiable fact about the row, which
    ``owner`` at the create check is not. Falls back to the parent Dispatch Trip's
    driver because Trip Start Log and Boarding Scan Log both fetch their own ``driver``
    from it, so that link is still empty when the create check runs. Same basis the
    Dispatch Trip rule already applies to the parent itself.
    """
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
    """True when ``doc`` is an UNSAVED row of a DocType that cannot be project-less.

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

    """
    return getattr(doc, "doctype", None) in PROJECT_MANDATORY_ON_CREATE and _is_unsaved(doc)


def scoped_has_permission(doc, ptype, user=None):
    """Deny a scoped user acting on a doc outside their allowed projects.

    Returns False to block, or None to defer to Frappe's default permission resolution
    (which keeps standard role-based checks intact). Never True.

    On a project-less doc, ownership is still a valid basis for a row that ALREADY
    EXISTS, but not for an unsaved row of a DocType whose model forbids a project-less
    record — see ``_unanchored_create_is_denied`` for why that is a named set rather
    than a rule over every DocType wired here. This ownership escape is the one place
    the module deliberately does NOT fail closed on an unresolvable project, and the
    named set is what bounds it.
    """
    user = _resolve_user(user)
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
    """Project-scope a doc, treating OWNERSHIP as an independent access basis ON A ROW
    THAT ALREADY EXISTS.

    The rule behind every ``if_owner`` DocPerm in Salis (Salis Driver, Trip Start Log):
    an unscoped oversight user defers to Frappe, the acting user's own STORED row is
    always allowed, and every other doc is confined to the user's allowed projects (a
    doc that anchors to no project fails closed).

    Deliberately NOT ``scoped_has_permission``: that one denies a project-BEARING doc
    outside scope before any ownership test, which would block a Driver (who holds no
    Project User Permission) from opening their own project-tagged record.

    So on an unsaved row the ownership branch is skipped and the row must anchor
    itself: its project must be in scope, or its driver link must resolve to the acting
    user's own Salis Driver (``_own_driver_basis``), which stays true after the insert.
    Once stored, ownership is a durable historical fact and is sufficient again,
    exactly as the ``if_owner`` DocPerms and the matching query fragments require.

    """
    user = _resolve_user(user)
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
    """Project-scope Dispatch Trip access, but never block a Driver from their OWN trip.

    Dispatch Trip reaches its project through the Route Plan chain (resolved by
    ``_doc_project``); enforcing that project boundary alone would deny a Driver
    opening a trip dispatched to them — a Driver holds no Project User Permission and
    does not own the trip (dispatchers create it). This mirrors the list fragment's
    ``own="driver"`` clause: a trip whose ``driver`` resolves to the acting user's
    Salis Driver is always allowed; every other doc is confined to the user's allowed
    projects. The driver-own basis is independent and valid, exactly like the if_owner
    basis on Trip Start Log / Salis Driver.

    Returns False to block, else None to defer to Frappe's default resolution.
    """
    user = _resolve_user(user)
    if _is_unscoped(user):
        return None

    own_driver = get_driver_for_session_user(user)
    if own_driver and getattr(doc, "driver", None) == own_driver:
        return None

    project = _doc_project(doc)
    if not project:
        return False

    if project not in _allowed_projects_for(user, doc.doctype):
        return False

    return None


def _driver_chain_has_permission(doc, user=None, driver_field="driver", with_owner=False):
    """Deny a scoped user acting on a ``driver``-linked doc outside their projects.

    Resolves the doc's project through ``driver_field`` -> Salis Driver -> project.
    When ``with_owner`` is True (the doc grants the Driver role an if_owner perm), the
    acting user's own STORED row is always allowed — mirroring the OR-owner clause in
    the matching fragment. Returns False to block, else None to defer. Not folded into
    ``scoped_has_permission`` because that helper reads ``doc.project`` directly, which
    these indirect-tenant docs do not carry.

    On an unsaved row the ownership branch is therefore skipped and the driver chain
    decides. The Driver's own create is not collateral: ``_own_driver_basis`` accepts a
    row whose driver link — or whose parent trip's driver — is the acting user's own
    Salis Driver, which is durable where ``owner`` is not, so a Driver still records
    their own attendance while holding no Project User Permission. Still deny-only, and
    still never reads ``ptype``: the discriminator is the document's storage state, not
    the action.

    """
    user = _resolve_user(user)
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
    """Allow a transfer whose from- OR to-project is in the scoped user's set.

    A transfer with NEITHER endpoint set is treated as project-less and DEFERRED, not
    denied — the second of the module's two named departures from fail-closed. It is
    deliberate: there is no tenant to enforce, and the matching fragment's "1=0" hides
    such a row from the list rather than from the form.
    """
    user = _resolve_user(user)
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
    """Project-scope a payment request AND block self-approval of it.

    This single hook composes two independent denials for "Salis Payment Request":

      1. Project row-scoping (``scoped_has_permission``) — a scoped user may only act
         on documents in a project they hold a User Permission for; a project-less
         document they do not own is denied. This mirrors every other project-bearing
         Salis DocType and closes the hole the native User-Permission link match leaves
         open for NULL/blank ``project`` rows.
      2. Segregation of duties — when the action is a submit/write that moves the
         document into a Finance-exclusive state (Approved by Finance / Paid), deny it
         if the acting user is the requester or the original creator.

    The document is denied if EITHER control denies. Returns False to block; otherwise
    returns None to defer to Frappe's default permission resolution.

    """
    if getattr(doc, "doctype", None) != "Salis Payment Request":
        return None

    if scoped_has_permission(doc, ptype, user=user) is False:
        return False

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


def _rule_driver_chain(doc, ptype, user, spec):
    """Apply the driver-chain rule with the DocType's own link field and owner basis."""
    return _driver_chain_has_permission(
        doc, user=user, driver_field=spec["field"], with_owner=spec.get("own") == "owner"
    )


DOCUMENT_RULES = {
    "scoped": lambda doc, ptype, user, spec: scoped_has_permission(doc, ptype, user=user),
    "owner_or_project": lambda doc, ptype, user, spec: _owner_or_project_has_permission(doc, user),
    "dispatch_trip": lambda doc, ptype, user, spec: _dispatch_trip_has_permission(doc, user),
    "driver_chain": _rule_driver_chain,
    "dual": lambda doc, ptype, user, spec: movement_cost_transfer_has_permission(doc, ptype, user),
    "payment_sod": lambda doc, ptype, user, spec: payment_sod_has_permission(doc, ptype, user),
}


def project_scoped_has_permission(doc, ptype, user=None):
    """Dispatch the document check for ``doc``'s DocType to its rule in ``SALIS_SCOPE``.

    Registered in ``hooks.py`` for every project-scoped Salis DocType. Each rule is a
    distinct, separately documented denial — they are NOT variations of one condition,
    and merging them would invert a guard — so the table names which one applies and
    this function only routes. An unknown DocType falls back to ``scoped_has_permission``,
    the plain project rule, which is what the hand-written wrappers defaulted to.

    Every rule returns False to block or None to defer, never True.
    """
    kind, spec = SALIS_SCOPE.get(getattr(doc, "doctype", None)) or _column()
    del kind
    return DOCUMENT_RULES[spec["rule"]](doc, ptype, user, spec)
