# Copyright (c) 2026, afmcoltd
"""Shared low-level primitives for tenant row-scoping.

Habitat scopes on Building, Salis on Project, Logistay on Company, but the
underlying mechanics are identical: resolve the acting user, decide whether an
oversight role sees everything, read the user's allowed values from frappe's own
User Permission resolver, narrow them to the doctype being queried, and turn that
into a SQL WHERE fragment or a report-scope tuple. Those primitives live here ONCE;
``apex.habitat.permissions``, ``apex.salis.permissions`` and
``apex.logistay.permissions`` bind their own oversight-role
set and ``allow`` doctype.

What is deliberately NOT here: the per-doctype ``*_query`` / ``*_has_permission``
wrappers and the scope-value resolution inside each ``has_permission`` (habitat's
``doc.building``/``doc.name``; salis' multi-hop ``_doc_project`` /
driver-chain / vehicle-chain). Those encode domain-specific knowledge and stay
local to each module.

Use ``allowed_for()`` / ``scope_condition()`` / ``report_scope()`` here instead of
re-implementing the pluck / fragment / tuple logic in a third scoping module.

``is_portal_capacity()`` / ``portal_capacity_verdict()`` are here for the same reason:
the portal capacity identity is an app-wide fact, not a Building/Project/Company one,
and all three modules have to answer it the same way.
"""

import frappe
from frappe import permissions as frappe_permissions

from apex.apex_core.utils.portal_identity import CAPACITY_USERS

PORTAL_CAPACITY_USERS = frozenset(CAPACITY_USERS.values())

PORTAL_CAPACITY_PTYPES = frozenset({"create", "write", "submit"})


def resolve_user(user=None):
    """Return the effective user, defaulting to the session user.

    Every scope resolver in Habitat, Salis and Logistay enters through this one call.
    A module-local copy makes "who is asking" answerable two ways on one request, which
    is how a scope silently widens for one DocType and not its sibling.
    """
    return user or frappe.session.user


def is_unscoped(user, unscoped_roles):
    """True when the user is the Administrator or holds an oversight role.

    ``frappe.get_roles`` (frappe/permissions.py:497) does the membership itself and
    already answers correctly for both edge users — every Role for Administrator,
    only the Guest role for Guest — so the explicit branch here states that contract
    rather than repairing the primitive. The one thing the primitive cannot do is
    know WHICH roles count as oversight: ``unscoped_roles`` is the module-specific
    set, the only thing that differs between Building and Project scoping, so it is
    passed in explicitly and never defaulted. A shared default would silently apply
    one domain's oversight set to the other.
    """
    if user in ("Administrator", "Guest"):
        return user == "Administrator"
    return bool(set(frappe.get_roles(user)) & unscoped_roles)


def is_portal_capacity(user):
    """True when ``user`` is a seeded portal capacity identity rather than a person.

    Read from ``portal_identity.CAPACITY_USERS`` — the very mapping
    ``as_capacity`` switches the session to — so the permission layer and the session
    switch can never disagree about who a capacity is.

    Keyed on the IDENTITY and never on the Driver or Worker role, because real people
    hold the Driver role and a role-keyed answer would apply to every one of them. The
    identity itself has no door: ``portal_identity_seed`` sets no password and leaves
    ``simultaneous_sessions`` at 0, so the only way to become it is ``frappe.set_user``
    inside ``as_capacity``, which runs after a token has already been verified.
    """
    return user in PORTAL_CAPACITY_USERS


def portal_capacity_verdict(ptype):
    """The document verdict for a portal capacity: defer on a write, deny anything else.

    One capacity user stands in for EVERY worker or driver in the estate, so it can hold
    no tenant User Permission — there is no single Building, Project or Company to name
    — and the tenant axis therefore cannot decide it. What decides it instead is the
    capacity role's own DocPerm, which is the wall the capacity was created to carry, on
    a document the endpoint already bound to the token holder before opening
    ``as_capacity``. Deferring says exactly that: the acting tenant is the document's.

    Everything outside ``PORTAL_CAPACITY_PTYPES`` — read above all — is still DENIED, so
    the deferral cannot widen into a cross-tenant read. The portal never needs it: it
    reads with ``frappe.get_doc`` and ``frappe.get_all``, neither of which consults this
    layer, and the list fragment stays shut for a capacity on both axes.
    """
    return None if ptype in PORTAL_CAPACITY_PTYPES else False


def allowed_for(user, allow, cache_key):
    """Values (Building/Project names) the user has an explicit User Permission for.

    Reads frappe's own resolver rather than the ``User Permission`` table:
    ``frappe_permissions.get_user_permissions`` returns one row per permission with
    ``doc`` / ``applicable_for`` / ``is_default`` / ``hide_descendants``, caches the
    whole set in Redis under the user (not per request), and short-circuits
    Administrator and Guest before any query. ``cache_key`` is kept in the signature
    because every call site names its scope with it and the tests stub on it; it no
    longer selects a cache, since the framework owns that.

    The values are returned UNFILTERED by ``applicable_for``. Filtering needs the
    target doctype, which this function does not receive — ``for_doctype()`` below
    applies it where the doctype is known.

    """
    del cache_key
    rows = frappe_permissions.get_user_permissions(user).get(allow) or []
    return [row.get("doc") for row in rows]


def for_doctype(user, allow, doctype, values):
    """Drop values whose User Permission rows ALL name a DIFFERENT doctype.

    ``values`` (rather than a re-read) is what the caller's own resolver returned,
    so a module that overrides its resolver keeps control of the scope and only the
    doctype restriction is applied on top. A value with no row at all is left
    untouched: nothing is known to restrict it.

    ``hide_descendants`` survives this filter for free, for the same reason it
    needs no code in ``allowed_for`` above: a descendant hidden by that flag was
    never added to ``rows`` in the first place, so it cannot enter ``granted`` or
    ``restricted`` here either, and it was already absent from ``values`` before
    this function ran.

    """
    if not values or not doctype:
        return list(values)
    rows = frappe_permissions.get_user_permissions(user).get(allow) or []
    granted, restricted = set(), set()
    for row in rows:
        applicable_for = row.get("applicable_for")
        if not applicable_for or applicable_for == doctype:
            granted.add(row.get("doc"))
        else:
            restricted.add(row.get("doc"))
    blocked = restricted - granted
    return [value for value in values if value not in blocked]


def scope_condition(user, is_unscoped_fn, allowed_fn, column, allow=None, doctype=None):
    """SQL WHERE fragment restricting ``column`` to the user's allowed values.

    "" for unscoped users (no restriction); "1=0" when the user is scoped but has
    no allowed values (so they see nothing); ``column in (v1, v2, ...)`` otherwise.

    Values reach the SQL through ``frappe.db.escape``
    (frappe/database/database.py:1371); no identifier is interpolated, only literals.

    ``is_unscoped_fn`` / ``allowed_fn`` are the calling MODULE's own single-arg
    resolvers (``_building_is_unscoped`` / ``_allowed_buildings`` for Building;
    ``_is_unscoped`` / ``_allowed_projects`` for Project). They are injected — not
    re-derived here from raw config — so each module's oversight-role set and cache
    namespace stay bound in that module, and so those module-level resolvers remain
    the single override/stub point the scoped permission test-suite drives.

    """
    user = resolve_user(user)
    if is_unscoped_fn(user):
        return ""
    values = for_doctype(user, allow, doctype, allowed_fn(user))
    if not values:
        return "1=0"
    escaped = ", ".join(frappe.db.escape(v) for v in values)
    return "{column} in ({values})".format(column=column, values=escaped)


def report_scope(user, is_unscoped_fn, allowed_fn, allow=None, doctype=None):
    """Return ``(restrict, allowed_values)`` for report-side row scoping.

    ``restrict`` is False for unscoped oversight roles (the report applies no extra
    filter). When True the report must confine its rows to ``allowed_values`` (an
    empty list = a scoped user with no permitted tenant, i.e. the report returns no
    rows). Injected resolvers, same rationale as ``scope_condition``; ``allow`` +
    ``doctype`` apply the same ``applicable_for`` narrowing, with ``doctype`` naming
    the DocType whose rows the report reads.
    """
    user = resolve_user(user)
    if is_unscoped_fn(user):
        return False, []
    return True, for_doctype(user, allow, doctype, allowed_fn(user))


def quote_column(field):
    """Backtick-quote one column name — the one place a scope fragment writes a quote."""
    return "`{0}`".format(field)


def render_column(spec, escaped):
    """``<column> in (...)`` — the tenant stored directly on the row."""
    return "{column} in ({values})".format(column=quote_column(spec["field"]), values=escaped)


def render_dual(spec, escaped):
    """Either endpoint in scope, as ONE fragment.

    Frappe AND-joins the conditions it collects, so a scope satisfied by EITHER of
    two columns has to arrive already OR-ed. Splitting it into two fragments would
    demand both endpoints be in scope and hide every row that crosses the boundary.
    """
    return "({first} in ({values}) or {second} in ({values}))".format(
        first=quote_column(spec["first"]), second=quote_column(spec["second"]), values=escaped
    )


def render_fragment(kind, spec, values, fragments):
    """Render one scope strategy from ``fragments`` against the user's allowed values.

    ``values`` is non-empty — the caller has already answered the unscoped and
    empty-scope cases, so every renderer emits a real restriction. Each value is
    passed through ``frappe.db.escape`` (frappe/database/database.py:1371) before it
    reaches a renderer, so a renderer never has to decide about quoting.

    An unrecognised kind renders "1=0" rather than falling through to no
    restriction: an unknown strategy must fail CLOSED.
    """
    render = fragments.get(kind)
    if not render:
        return "1=0"
    return render(spec, ", ".join(frappe.db.escape(value) for value in values))
