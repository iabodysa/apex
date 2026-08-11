# Copyright (c) 2026, afmcoltd
"""Building row-scoping for Habitat.

Every scoped Habitat DocType is confined to the estate it belongs to. The estate is
reached one of five ways, and WHICH WAY IS A PROPERTY OF THE DOCTYPE, not of a
function:

    column   the doc stores the estate itself (``building``, or ``name`` on Building)
    dual     the doc has two endpoints (``from_building`` / ``to_building``)
    hop      the estate is one link away (Housing Checkout -> Bed -> building)
    child    the estate is a row set in a child table (Audit Remediation Plan)
    owner    not a building axis at all (Maintenance Request: owner / assignee)

``BUILDING_SCOPE`` maps DocType to that property. ``building_scope_query`` reads the
table and emits the list fragment; ``building_scoped_has_permission`` reads the SAME
table and answers the form / REST / submit check, so the two can never disagree about
what is in scope. Frappe hands the DocType to both hooks, so one registration each in
``hooks.py`` covers every DocType.

Adding a scoped DocType is a row in ``BUILDING_SCOPE`` plus its two ``hooks.py``
entries. It is deliberately not a new function: the previous shape carried one
hand-written function per DocType, and threading a single new argument through them
(commit 7bd58d09, the ``applicable_for`` narrowing) had to edit all thirty-four.

Two invariants hold on every path and are the reason the edge cases look asymmetric:

* "" (no restriction at all) for the Administrator and the ``HOUSING_UNSCOPED_ROLES``
  oversight roles; "1=0" (matches nothing) for a scoped user holding no building.
  Never the other way round — inverted, it blacks out oversight and leaks every
  estate to a supervisor.
* Fail closed. A doc whose estate cannot be resolved is DENIED, never deferred.

``_allowed_buildings``, ``_building_is_unscoped`` and ``_building_condition`` stay
module-level functions: ``apex.habitat.api`` and the Habitat reports import those
three names directly, and the scoped-permission suite stubs the first two.

The block at the foot of this file is COMPATIBILITY ONLY. Those wrappers hold no rule
— each forwards to the dispatcher with its own ``scope_for`` — and ``hooks.py`` does
not route through them. They exist because callers outside this module resolve a
fragment by FUNCTION NAME; a wrapper is the whole cost of keeping such a caller
working, and none of them has to be edited when the rule changes.
"""

import frappe
from frappe import _

from apex.apex_core.utils import permission_scope

PRIVILEGED_ROLES = {
    "System Manager",
    "Accommodation Manager",
    "Resident Supervisor",
    "Resident Request Coordinator",
}

HOUSING_UNSCOPED_ROLES = {
    "System Manager",
    "Accommodation Manager",
    "Internal Auditor",
    "Finance Manager",
}

BUILDING = "building"


def _resolve_user(user=None):
    """Return the effective user, defaulting to the session user."""
    return permission_scope.resolve_user(user)


def _is_privileged(user):
    """True when the user is the Administrator or holds any privileged role.

    Guest is never privileged.
    """
    if user in ("Administrator", "Guest"):
        return user == "Administrator"
    return bool(set(frappe.get_roles(user)) & PRIVILEGED_ROLES)


def _allowed_buildings(user):
    """Building names the user has an explicit User Permission for (request-cached).

    Thin wrapper over ``permission_scope.allowed_for`` binding the Building ``allow``
    doctype and the ``apex_allowed_buildings`` cache namespace. That namespace is
    DISTINCT from Salis' ``apex_allowed_projects`` and Logistay's
    ``apex_allowed_companies`` so two scopes can never collide in
    ``frappe.local.cache`` for the same user in one request. Kept as a module-level
    function because the scoped permission test-suite stubs this name directly.
    """
    return permission_scope.allowed_for(user, "Building", "apex_allowed_buildings")


def _allowed_buildings_for(user, doctype):
    """``_allowed_buildings`` narrowed to the permissions that apply to ``doctype``.

    A User Permission carrying ``applicable_for`` grants its building for that one
    DocType; without this narrowing it would unlock every building-scoped DocType.
    See ``permission_scope.for_doctype``.
    """
    return permission_scope.for_doctype(user, "Building", doctype, _allowed_buildings(user))


def _building_is_unscoped(user):
    """True when the user is the Administrator or holds a building-oversight role."""
    return permission_scope.is_unscoped(user, HOUSING_UNSCOPED_ROLES)


def assert_building_scope(user=None, doctype=None):
    """Refuse a building-scoped user who holds NO building, naming that as the cause.

    An empty allowed set can never match any document, so every action fails with
    Frappe's generic 'not permitted for <doctype> - <docname>' — which names a docname
    that may not even exist yet and sends the reader hunting for missing data or a
    broken DocPerm. The scope layer is the only place that knows the real reason, so
    it says it here. Callers invoke this BEFORE acting; the deny-only hook stays
    deny-only, since a permission hook that throws would break list rendering.
    """
    user = _resolve_user(user)
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
    """SQL WHERE fragment restricting ``column`` to the user's allowed buildings.

    "" for unscoped users (no restriction); "1=0" when the user is scoped but has no
    allowed buildings (so they see nothing). Retained as a public name because
    ``apex.habitat.api.dashboard`` composes it into its own aggregate SQL, where there
    is no DocType-scoped hook to read the strategy table.

    """
    return permission_scope.scope_condition(
        user, _building_is_unscoped, _allowed_buildings, column, allow="Building", doctype=doctype
    )


def _column(field):
    """Estate stored on the doc itself."""
    return ("column", {"field": field})


def _dual(first, second):
    """Estate at either of two endpoints."""
    return ("dual", {"first": first, "second": second})


def _hop(field, doctype):
    """Estate one link away, reached through ``field`` -> ``doctype``.``building``.

    NEITHER hop DocType has a ``building`` column, and a ``building`` ATTRIBUTE on the
    doc itself is never consulted: on a stored row it is always empty, and on an
    UNSAVED doc a caller controls every key in the payload — accepting one would let a
    caller name their own estate and be granted on it.
    """
    return ("hop", {"field": field, "doctype": doctype})


def _child(child_doctype, parent_doctype):
    """Estate held as a row set in a child table."""
    return ("child", {"child": child_doctype, "parent": parent_doctype})


def _quote(field):
    """Backtick-quote one column name. The only place this module writes a quote."""
    return "`{0}`".format(field)


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


def _render_column(spec, escaped):
    """``building in (...)`` — the estate stored on the row."""
    return "{column} in ({values})".format(column=_quote(spec["field"]), values=escaped)


def _render_dual(spec, escaped):
    """Either endpoint in scope.

    """
    return "({first} in ({values}) or {second} in ({values}))".format(
        first=_quote(spec["first"]), second=_quote(spec["second"]), values=escaped
    )


def _render_hop(spec, escaped):
    """The estate one link away, as a subquery on the linked DocType."""
    return "{column} in (select `name` from `tab{doctype}` where `building` in ({values}))".format(
        column=_quote(spec["field"]), doctype=spec["doctype"], values=escaped
    )


def _render_child(spec, escaped):
    """A row matches when ANY building named in its child table is the user's."""
    return (
        "`name` in (select `parent` from `tab{child}` "
        "where `parenttype` = {parent} and `building` in ({values}))".format(
            child=spec["child"], parent=frappe.db.escape(spec["parent"]), values=escaped
        )
    )


FRAGMENTS = {
    "column": _render_column,
    "dual": _render_dual,
    "hop": _render_hop,
    "child": _render_child,
}


def _fragment(kind, spec, values):
    """Render one scope strategy against the user's allowed buildings.

    ``values`` is non-empty — the caller has already answered the unscoped and
    no-building cases, so every renderer emits a real restriction. An unrecognised
    kind renders "1=0" rather than falling through to no restriction: an unknown
    strategy must fail CLOSED.
    """
    render = FRAGMENTS.get(kind)
    if not render:
        return "1=0"
    return render(spec, ", ".join(frappe.db.escape(value) for value in values))


def building_scope_query(user=None, doctype=None, scope_for=None):
    """WHERE fragment scoping ``doctype``'s list/report view to the user's estate.

    ``doctype`` MUST stay in this signature: ``frappe.call`` drops any keyword the
    callee does not declare, so a signature without it would receive no DocType,
    silently skip the ``applicable_for`` narrowing in ``_allowed_buildings_for``, and
    widen every scope on the tenant axis.

    ``scope_for`` is never passed by frappe. It exists for the named compatibility
    wrappers at the foot of this module, which must select their own DocType's strategy
    while leaving ``doctype`` — the ``applicable_for`` narrowing key — exactly as their
    caller supplied it.

    An unknown DocType falls back to the plain ``building`` column, which is what the
    hand-written per-DocType functions did (all of them delegated to
    ``_building_condition``) and the shape 29 of the 36 scoped DocTypes use.

    """
    user = _resolve_user(user)
    if _building_is_unscoped(user):
        return ""

    buildings = _allowed_buildings_for(user, doctype)
    if not buildings:
        return "1=0"

    kind, spec = BUILDING_SCOPE.get(scope_for or doctype) or _column(BUILDING)
    return _fragment(kind, spec, buildings)


def _estate_from_anchor(doc, doctype):
    """Re-read the estate from the doc's own parent link.

    Marking ``building`` ``reqd`` does not help: mandatory fields are enforced in
    ``_validate()`` (``:310``), long after the permission check. The anchor must be a
    real link on the doc, not a promise about the fetched field.

    """
    anchor = BUILDING_FETCH_ANCHOR.get(doctype)
    if not anchor:
        return None
    fieldname, parent_doctype = anchor
    parent = getattr(doc, fieldname, None)
    if not parent:
        return None
    return frappe.db.get_value(parent_doctype, parent, "building")


def _estates_column(doc, spec):
    """The estate stored on the row — ``name`` on Building, ``building`` elsewhere."""
    stored = getattr(doc, spec["field"], None)
    return [stored] if stored else []


def _estates_dual(doc, spec):
    """Both endpoints; the caller treats the doc as in scope when EITHER is the user's."""
    endpoints = (getattr(doc, spec["first"], None), getattr(doc, spec["second"], None))
    return [value for value in endpoints if value]


def _estates_child(doc, spec):
    """Every building named in the child table."""
    rows = getattr(doc, "buildings_in_scope", None) or []
    return [value for value in (getattr(row, "building", None) for row in rows) if value]


def _estates_hop(doc, spec):
    """The hop link the fragment subqueries through, so form and list agree.

    Load-bearing for Housing Checkout: the fragment reaches its estate through ``bed``,
    so the form check must prefer ``bed`` too, or a stored row whose ``bed`` and
    ``assignment`` disagree would be readable in the list and denied on the form. The
    doc's own ``building`` attribute is never consulted — see ``_hop``.
    """
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
    """Every building this doc touches, as a list; empty when none resolves.

    Mirrors the strategy the list fragment used for the same DocType, so the form view
    can never disagree with the list view about what is in scope.

    Only ``column`` and ``hop`` fall back to ``BUILDING_FETCH_ANCHOR``, and that
    restriction is deliberate. ``child`` rows arrive with the payload and are built in
    ``Document.__init__``, so unlike a ``fetch_from`` field they ARE populated when
    ``check_permission("create")`` runs; ``dual``'s two endpoints are direct,
    never-fetched links. Neither is ever empty for the ordering reason the anchor
    exists to answer, so neither may borrow another DocType's estate.
    """
    doctype = getattr(doc, "doctype", None)
    kind, spec = BUILDING_SCOPE.get(doctype) or _column(BUILDING)

    estates = ESTATES[kind](doc, spec)
    if estates or kind not in ANCHORED_KINDS:
        return estates

    anchor = _estate_from_anchor(doc, doctype)
    return [anchor] if anchor else []


def building_scoped_has_permission(doc, ptype, user=None):
    """Deny a building-scoped user acting on a doc outside their estate.

    Returns None to defer to Frappe's default resolution — unscoped users and in-scope
    docs, so the DocPerms govern unwidened — or False to block. It NEVER returns True,
    so it can only narrow.

    Deny-only and ptype-agnostic: it never branches on ``ptype``, so an out-of-estate
    doc is blocked for every action including ``submit``. A doc whose estate cannot be
    resolved at all is DENIED rather than deferred — fail closed, matching the
    fragment, which hides the same row from the list.
    """
    user = _resolve_user(user)
    if _building_is_unscoped(user):
        return None

    estates = _doc_estates(doc)
    if not estates:
        return False

    allowed = _allowed_buildings_for(user, doc.doctype)
    return None if any(estate in allowed for estate in estates) else False


def report_building_scope(user=None, doctype=None):
    """Return ``(restrict, allowed_buildings)`` for report-side building scoping.

    ``restrict`` is False for unscoped oversight roles (the report applies no extra
    filter — they see everything). When True the report must confine its rows to
    ``allowed_buildings``; an empty list means a scoped user with no permitted
    building, i.e. the report should return no rows.
    """
    return permission_scope.report_scope(
        user, _building_is_unscoped, _allowed_buildings, allow="Building", doctype=doctype
    )


def maintenance_request_query(user=None, doctype=None):
    """Owner-scope the Maintenance Request list/report view.

    Maintenance Request is NOT on the building axis — a ticket belongs to the person
    who raised it and the technician it went to — so it is absent from
    ``BUILDING_SCOPE`` and keeps its own fragment and its own ``hooks.py`` entry.

    Returns "" (no restriction) for the Administrator and the privileged oversight
    roles. Returns "1=0" for Guest, who must see nothing. For every other user the
    fragment confines the view to the tickets they raised (``owner``) or were assigned
    (``assigned_to``).

    NOTE on the ``if_owner`` interaction: when a user's ONLY read on Maintenance
    Request is the universal "All" role's ``if_owner`` DocPerm, Frappe AND-s its own
    ``owner = me`` match onto this fragment, so their LIST view collapses to
    owner-only. The ``assigned_to`` branch therefore surfaces assigned rows in the list
    only for users who also hold a plain (non-``if_owner``) read — the operational
    roles such as Maintenance Technician, the realistic assignee. Any assignee can
    still OPEN an assigned ticket via ``maintenance_request_has_permission``.
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

    Mirrors ``maintenance_request_query`` for the form view, REST resource and link
    reads. Returns None to defer to Frappe's default permission resolution for the
    Administrator and the privileged oversight roles, so their DocPerms govern
    unwidened. For every other user it returns True only when the user raised the
    ticket (``owner``) or is its ``assigned_to`` technician, and False otherwise —
    never exposing a ticket the user neither raised nor was assigned.

    This is the ONE handler in this module that returns True: the owner/assignee basis
    is an independent grant, not a narrowing of the building axis.
    """
    user = _resolve_user(user)
    if _is_privileged(user):
        return None

    if getattr(doc, "owner", None) == user:
        return True
    if getattr(doc, "assigned_to", None) == user:
        return True
    return False


def report_maintenance_request_scope(user=None):
    """Return ``(restrict, user)`` for report-side maintenance-request scoping.

    ``restrict`` is False for the Administrator and the privileged oversight roles (the
    report applies no extra filter — they see every ticket). When True the report must
    confine its rows to ``owner == user OR assigned_to == user`` (e.g. via get_all's
    ``or_filters``), matching the owner/assignee fragment in
    ``maintenance_request_query``.
    """
    user = _resolve_user(user)
    if _is_privileged(user):
        return False, user
    return True, user
