# Copyright (c) 2026, AFMCO and contributors

import frappe

from apex.apex_core.utils import permission_scope

PRIVILEGED_ROLES = {
    "System Manager",
    "Accommodation Manager",
    "Resident Supervisor",
    "Resident Request Coordinator",
}


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


def report_maintenance_request_scope(user=None):
    """Return ``(restrict, user)`` for report-side maintenance-request scoping.

    ``restrict`` is False for the Administrator and privileged oversight roles (the
    report applies no extra filter — they see every ticket). When True the report must
    confine its rows to ``owner == user OR assigned_to == user`` (e.g. via get_all's
    ``or_filters``), matching the owner/assignee fragment in maintenance_request_query.
    """
    user = _resolve_user(user)
    if _is_privileged(user):
        return False, user
    return True, user


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


HOUSING_UNSCOPED_ROLES = {
    "System Manager",
    "Accommodation Manager",
    "Internal Auditor",
    "Finance Manager",
}


def _allowed_buildings(user):
    """Building names the user has an explicit User Permission for (request-cached).

    Thin wrapper over ``permission_scope.allowed_for`` binding the Building
    ``allow`` doctype and the ``apex_allowed_buildings`` cache namespace. That
    namespace is DISTINCT from Salis' ``apex_allowed_projects`` so a Building scope
    and a Project scope can never collide in ``frappe.local.cache`` for the same
    user in one request. See ``permission_scope.allowed_for`` for the
    request-cache + no-cross-user-bleed invariant. Kept as a module-level function
    because the scoped permission test-suite stubs this name directly.
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


def _building_condition(user=None, column="`building`", doctype=None):
    """SQL WHERE fragment restricting ``column`` to the user's allowed buildings.

    "" for unscoped users (no restriction); "1=0" when the user is scoped but has
    no allowed buildings (so they see nothing). Delegates the shared fragment
    logic to ``permission_scope.scope_condition``, injecting this module's own
    building resolvers so the Building oversight set + cache namespace stay bound
    here.

    Every safety and cleaning record below carries exactly ONE Building link of its own,
    so this shared fragment serves them with no anchor hop. They still need a fragment
    even though a Building User Permission already narrows the list: frappe's native
    match (db_query.py:1090) is ``ifnull(building,'')='' or building in (...)``, so an
    empty-building row stays visible and a scoped user holding NO Building permission
    gets no condition at all. This closes both.
    """
    return permission_scope.scope_condition(
        user, _building_is_unscoped, _allowed_buildings, column, allow="Building", doctype=doctype
    )


def accommodation_assignment_query(user=None, doctype=None):
    return _building_condition(user, doctype=doctype)


def custody_issue_query(user=None, doctype=None):
    return _building_condition(user, doctype=doctype)


def cleaning_log_query(user=None, doctype=None):
    return _building_condition(user, doctype=doctype)


def accommodation_building_query(user=None, doctype=None):
    return _building_condition(user, column="`name`", doctype=doctype)


def safety_round_query(user=None, doctype=None):
    return _building_condition(user, doctype=doctype)


def safety_task_execution_query(user=None, doctype=None):
    return _building_condition(user, doctype=doctype)


def scheduled_task_instance_query(user=None, doctype=None):
    return _building_condition(user, doctype=doctype)


def safety_incident_query(user=None, doctype=None):
    return _building_condition(user, doctype=doctype)


def safety_inspection_report_query(user=None, doctype=None):
    return _building_condition(user, doctype=doctype)


def safety_finding_ledger_query(user=None, doctype=None):
    return _building_condition(user, doctype=doctype)


def cleaning_compliance_ledger_query(user=None, doctype=None):
    return _building_condition(user, doctype=doctype)


def accommodation_resident_request_query(user=None, doctype=None):
    return _building_condition(user, doctype=doctype)


def idle_resident_report_query(user=None, doctype=None):
    return _building_condition(user, doctype=doctype)


def housing_checkout_query(user=None, doctype=None):
    """Scope Housing Checkout to the user's buildings through its ``bed``.

    The DocType carries no ``building`` column, so ``_building_condition`` cannot serve
    it: the estate is one hop away as ``bed`` -> ``Bed.building``. The fragment is
    therefore a subquery on ``tabBed``, the shape ``salis.permissions.dispatch_trip_query``
    uses to reach a Route Plan's project.

    Renders the two edge cases exactly like every sibling housing fragment: "" (no
    restriction at all) for the Administrator and the oversight roles in
    ``HOUSING_UNSCOPED_ROLES``, and "1=0" (matches nothing) for a scoped user holding no
    building — never the other way round, which would blackout oversight and leak to a
    supervisor. A checkout whose ``bed`` is NULL matches no subquery row and so stays
    hidden from a scoped user: fail closed. Stored rows always carry one, because ``bed``
    is fetched from ``assignment.bed`` and Housing Assignment makes ``bed`` mandatory.
    """
    user = _resolve_user(user)
    if _building_is_unscoped(user):
        return ""
    buildings = _allowed_buildings_for(user, doctype)
    if not buildings:
        return "1=0"
    escaped = ", ".join(frappe.db.escape(b) for b in buildings)
    return "`bed` in (select `name` from `tabBed` where `building` in ({values}))".format(
        values=escaped
    )


def room_bed_transfer_query(user=None, doctype=None):
    """Scope Room Bed Transfer to the user's buildings through its ``assignment``.

    The DocType carries no ``building`` column, so ``_building_condition`` cannot
    serve it: the estate is one hop away as ``assignment`` ->
    ``Housing Assignment.building``, the same subquery shape
    ``housing_checkout_query`` uses for its ``bed`` hop.

    One anchor is enough BECAUSE the controller rejects a cross-building move: the
    source and target buildings of a valid transfer are the same building, so the
    assignment's estate is the whole estate the record touches. Were that rule ever
    relaxed, this fragment would have to widen to both endpoints (the
    ``_dual_building_condition`` shape) or it would leak.

    Renders the two edge cases exactly like every sibling housing fragment: "" for
    the Administrator and the oversight roles, "1=0" for a scoped user holding no
    building. A transfer whose ``assignment`` is somehow unset matches no subquery
    row and stays hidden: fail closed.
    """
    user = _resolve_user(user)
    if _building_is_unscoped(user):
        return ""
    buildings = _allowed_buildings_for(user, doctype)
    if not buildings:
        return "1=0"
    escaped = ", ".join(frappe.db.escape(b) for b in buildings)
    return (
        "`assignment` in (select `name` from `tabHousing Assignment` "
        "where `building` in ({values}))".format(values=escaped)
    )


def audit_remediation_plan_query(user=None, doctype=None):
    """Scope Audit Remediation Plan to the user's buildings through its child scope.

    The plan carries NO ``building`` column at all — the estate it touches is the set
    of buildings listed in its ``buildings_in_scope`` child table — so neither
    ``_building_condition`` nor the single-hop shape serves it. The fragment is a
    subquery on ``tabAudit Remediation Building Scope`` keyed on ``parent``, the same
    shape ``housing_checkout_query`` uses for its bed hop, widened from one link to a
    row set: a plan matches when ANY building it names is one of the user's.

    Because the plan has no Building Link of its own, frappe's native User Permission
    match (db_query.py:1079) emits NOTHING for this DocType — a Building User
    Permission alone leaves every plan visible. This fragment is the only row scope
    there is here, not a tightening of a native one.

    Renders the two edge cases exactly like every sibling housing fragment: "" (no
    restriction) for the Administrator and the oversight roles in
    ``HOUSING_UNSCOPED_ROLES``, and "1=0" for a scoped user holding no building. A plan
    whose scope table is EMPTY names no building, matches no subquery row, and so stays
    hidden from a scoped user while oversight still sees it: fail closed.
    """
    user = _resolve_user(user)
    if _building_is_unscoped(user):
        return ""
    buildings = _allowed_buildings_for(user, doctype)
    if not buildings:
        return "1=0"
    escaped = ", ".join(frappe.db.escape(b) for b in buildings)
    return (
        "`name` in (select `parent` from `tabAudit Remediation Building Scope` "
        "where `parenttype` = 'Audit Remediation Plan' and `building` in ({values}))"
        .format(values=escaped)
    )


def audit_remediation_plan_has_permission(doc, ptype, user=None):
    """Deny a scoped user acting on a plan that names none of their buildings.

    ``building_scoped_has_permission`` cannot be reused: it resolves the estate from
    ``doc.building``, a field this DocType does not have, so it would read None for
    every plan and return False — blacking out a scoped supervisor's OWN plans too. A
    guard that denies the role it is meant to bound reviews as correct and is not.

    So this mirrors ``audit_remediation_plan_query``'s hop instead, reading the child
    rows directly. No create-path anchor is owed: child tables arrive with the payload
    and are built in ``Document.__init__``, so unlike a ``fetch_from`` field the scope
    rows ARE populated when ``check_permission("create")`` runs at document.py:300.

    Deny-only and ptype-agnostic, like its siblings: returns None to defer to the
    DocPerms, False to block every action including submit. A plan naming no building
    at all is denied rather than deferred — fail closed, matching the fragment.
    """
    user = _resolve_user(user)
    if _building_is_unscoped(user):
        return None

    buildings = [
        getattr(row, "building", None)
        for row in (getattr(doc, "buildings_in_scope", None) or [])
    ]
    buildings = [b for b in buildings if b]
    if not buildings:
        return False
    allowed = _allowed_buildings_for(user, doc.doctype)
    return None if any(b in allowed for b in buildings) else False


def housing_checkout_has_permission(doc, ptype, user=None):
    """Deny a scoped user acting on a checkout outside their buildings.

    ``building_scoped_has_permission`` cannot be reused here. It resolves the estate from
    ``doc.building``, a field Housing Checkout does not have, so it would read None for
    every checkout and return False — denying a building-scoped supervisor their OWN
    building's records too. A guard that blacks out the role it is meant to bound reviews
    as correct and is not.

    So this mirrors ``housing_checkout_query``'s hop instead: ``bed`` -> ``Bed.building``.
    It falls back to ``assignment`` -> ``Housing Assignment.building`` because
    ``Document.insert`` runs ``check_permission("create")`` (document.py:300) BEFORE
    ``_validate_links()`` (:302) applies ``fetch_from``, so on a server-side create ``bed``
    is not populated yet while the mandatory ``assignment`` always is. Without the
    fallback a scoped supervisor could not create a checkout at all.

    Deny-only and ptype-agnostic, like its siblings: returns None to defer to the
    DocPerms, False to block every action including submit.
    """
    user = _resolve_user(user)
    if _building_is_unscoped(user):
        return None

    building = None
    bed = getattr(doc, "bed", None)
    if bed:
        building = frappe.db.get_value("Bed", bed, "building")
    if not building:
        assignment = getattr(doc, "assignment", None)
        if assignment:
            building = frappe.db.get_value("Housing Assignment", assignment, "building")
    if not building:
        return False
    return None if building in _allowed_buildings_for(user, doc.doctype) else False


def report_building_scope(user=None, doctype=None):
    """Return ``(restrict, allowed_buildings)`` for report-side building scoping.

    ``restrict`` is False for unscoped oversight roles (the report applies no extra
    filter — they see everything). When True the report must confine its rows to
    ``allowed_buildings`` (an empty list means a scoped user with no permitted
    building, i.e. the report should return no rows). Thin wrapper over
    ``permission_scope.report_scope`` with this module's building resolvers.
    """
    return permission_scope.report_scope(
        user, _building_is_unscoped, _allowed_buildings, allow="Building", doctype=doctype
    )


BUILDING_FETCH_ANCHOR = {
    "Bed": ("room", "Room"),
    "Custody Acknowledgment": ("custody_issue", "Custody Issue"),
    "Custody Damage Assessment": ("custody_return", "Custody Return"),
    "Custody Return": ("custody_issue", "Custody Issue"),
    "Housing Assignment": ("bed", "Bed"),
    "Housing Inventory": ("room", "Room"),
    "Maintenance Inspection Report": (
        "maintenance_work_order",
        "Maintenance Work Order",
    ),
    "Maintenance Work Order": ("maintenance_request", "Maintenance Request"),
    "Resident Request": ("bed", "Bed"),
    "Room Bed Transfer": ("assignment", "Housing Assignment"),
    "Scheduled Task Instance": ("assignment", "Scheduled Task Assignment"),
}


def _doc_building(doc):
    """Resolve the estate a Habitat doc belongs to, or None.

    ``Document.insert`` runs ``check_permission("create")`` (document.py:300) BEFORE
    ``_validate_links()`` (:302) applies ``fetch_from``, so on a server-side create every
    ``building`` in ``BUILDING_FETCH_ANCHOR`` is still EMPTY at the create check. Reading
    it alone would deny a scoped supervisor the creation of records in their OWN estate.
    Each entry therefore names the link that is populated at that moment — the doc's own
    parent link, which the payload always carries and which is never itself fetched — and
    the estate is re-read from THAT document.

    Marking ``building`` ``reqd`` does not help: mandatory fields are enforced in
    ``_validate()`` (:310), long after the permission check. The anchor must be a real
    link on the doc, not a promise about the fetched field.

    Returns None when nothing resolves, so the caller still fails CLOSED — a doc whose
    estate cannot be established is denied, never deferred.
    """
    doctype = getattr(doc, "doctype", None)
    if doctype == "Building":
        return getattr(doc, "name", None)

    building = getattr(doc, "building", None)
    if building:
        return building

    anchor = BUILDING_FETCH_ANCHOR.get(doctype)
    if not anchor:
        return None
    fieldname, parent_doctype = anchor
    parent = getattr(doc, fieldname, None)
    if not parent:
        return None
    return frappe.db.get_value(parent_doctype, parent, "building")


def building_scoped_has_permission(doc, ptype, user=None):
    """Deny a building-scoped user acting on a doc outside their buildings.

    Returns None to defer to Frappe's default resolution (unscoped users / in-scope
    docs — keeps DocPerms intact), or False to block. The Building doc
    is scoped on its own name; the transactions are scoped on their `building` field,
    falling back to the anchor link in ``BUILDING_FETCH_ANCHOR`` when that field is a
    ``fetch_from`` not yet applied at the create check.

    Deny-only + ptype-agnostic: it never branches on ``ptype``, so an out-of-building
    doc is blocked for every action including ``submit`` — a scoped user can neither
    read nor submit another estate's record.
    """
    user = _resolve_user(user)
    if _building_is_unscoped(user):
        return None

    building = _doc_building(doc)

    if not building:
        return False
    return None if building in _allowed_buildings_for(user, doc.doctype) else False



def facility_asset_custody_assignment_query(user=None, doctype=None):
    return _building_condition(user, doctype=doctype)


def non_financial_depreciation_snapshot_query(user=None, doctype=None):
    return _building_condition(user, doctype=doctype)


def custody_return_query(user=None, doctype=None):
    return _building_condition(user, doctype=doctype)


def custody_damage_assessment_query(user=None, doctype=None):
    return _building_condition(user, doctype=doctype)


def facility_asset_movement_query(user=None, doctype=None):
    return _dual_building_condition(user, doctype=doctype)


def custody_acknowledgment_query(user=None, doctype=None):
    return _building_condition(user, doctype=doctype)


def custody_handover_query(user=None, doctype=None):
    return _dual_building_condition(user, doctype=doctype)


def material_transfer_query(user=None, doctype=None):
    return _dual_building_condition(user, doctype=doctype)


def facility_asset_delivery_query(user=None, doctype=None):
    return _dual_building_condition(user, doctype=doctype)


def facility_asset_query(user=None, doctype=None):
    return _building_condition(user, doctype=doctype)


def housing_inventory_query(user=None, doctype=None):
    return _building_condition(user, doctype=doctype)


def building_license_query(user=None, doctype=None):
    return _building_condition(user, doctype=doctype)


def maintenance_work_order_query(user=None, doctype=None):
    return _building_condition(user, doctype=doctype)


def maintenance_inspection_report_query(user=None, doctype=None):
    """Scope Maintenance Inspection Report on its own stored ``building``.

    The column is populated on every stored row — ``reqd`` plus a ``fetch_from``
    on ``maintenance_work_order.building`` — so the shared column fragment serves
    the LIST view with no hop. Only the CREATE check needs the work-order anchor
    (``BUILDING_FETCH_ANCHOR``), because ``fetch_from`` has not run yet at that
    point; a row that reaches this fragment has already been written.
    """
    return _building_condition(user, doctype=doctype)


def accommodation_occupancy_snapshot_query(user=None, doctype=None):
    return _building_condition(user, doctype=doctype)


def temporary_worker_query(user=None, doctype=None):
    return _building_condition(user, doctype=doctype)


def arrival_batch_query(user=None, doctype=None):
    return _building_condition(user, doctype=doctype)


def accommodation_room_query(user=None, doctype=None):
    return _building_condition(user, doctype=doctype)


def accommodation_bed_query(user=None, doctype=None):
    return _building_condition(user, doctype=doctype)


def accommodation_stock_ledger_query(user=None, doctype=None):
    return _building_condition(user, doctype=doctype)


def _dual_building_condition(user=None, doctype=None):
    """WHERE fragment scoping a from_building/to_building doc to the user's estate.

    A single fragment (pqc hooks AND-join, so the OR must live inside one fragment):
    matches a row when EITHER endpoint is one of the user's allowed buildings. "" for
    unscoped users; "1=0" when the user is scoped but has no allowed buildings.
    """
    user = _resolve_user(user)
    if _building_is_unscoped(user):
        return ""
    buildings = _allowed_buildings_for(user, doctype)
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

    allowed = _allowed_buildings_for(user, doc.doctype)
    endpoints = [
        getattr(doc, "from_building", None),
        getattr(doc, "to_building", None),
    ]
    endpoints = [b for b in endpoints if b]
    if not endpoints:
        return False
    return None if any(b in allowed for b in endpoints) else False
