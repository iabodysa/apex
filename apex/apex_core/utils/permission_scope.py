# Copyright (c) 2026, AFMCO Support Services Co. Ltd
"""Shared low-level primitives for tenant row-scoping.

Habitat scopes on Building, Salis on Project, but the underlying mechanics are
identical: resolve the acting user, decide whether an oversight role sees
everything, pluck the user's allowed values from User Permission (request-cached),
and turn that into a SQL WHERE fragment or a report-scope tuple. Those five
primitives live here ONCE; ``apex.habitat.permissions`` and
``apex.salis.permissions`` keep thin wrappers that bind their own oversight-role
set, ``allow`` doctype, and cache namespace.

What is deliberately NOT here: the per-doctype ``*_query`` / ``*_has_permission``
wrappers and the scope-value resolution inside each ``has_permission`` (habitat's
``doc.building``/``doc.name``; salis' multi-hop ``_doc_project`` /
driver-chain / vehicle-chain). Those encode domain-specific knowledge and stay
local to each module.

Use ``allowed_for()`` / ``scope_condition()`` / ``report_scope()`` here instead of
re-implementing the pluck / fragment / tuple logic in a third scoping module.
"""

import frappe


def resolve_user(user=None):
    """Return the effective user, defaulting to the session user."""
    return user or frappe.session.user


def is_unscoped(user, unscoped_roles):
    """True when the user is the Administrator or holds an oversight role.

    Guest is never unscoped (``user == "Administrator"`` is False for Guest, and
    Guest short-circuits before the role check). ``unscoped_roles`` is the
    MODULE-SPECIFIC oversight set — the ONE thing that differs between Building and
    Project scoping — so it is passed in explicitly and never defaulted; a shared
    default here would silently apply the wrong oversight set to one domain.
    """
    if user in ("Administrator", "Guest"):
        return user == "Administrator"
    return bool(set(frappe.get_roles(user)) & unscoped_roles)


def allowed_for(user, allow, cache_key):
    """Values (Building/Project names) the user has an explicit User Permission for.

    Request-scoped cache: every scoped check funnels through here, so one list /
    report render resolves the User Permission set with a single SQL per
    (request context, user). ``frappe.local_cache`` memoises it in
    ``frappe.local.cache`` for the life of ONE request context.

    ``cache_key`` MUST be distinct per scope kind ("apex_allowed_buildings" vs
    "apex_allowed_projects"): a shared namespace would let a Building scope be
    served where a Project scope was expected (or vice-versa) for the same user in
    one request — a cross-scope data leak. ``allow`` (the User Permission ``allow``
    doctype) always co-varies with ``cache_key`` at the call site, so the cached
    value can never disagree with the namespace.

    Security — why it cannot leak across users: the cache value is keyed on
    ``user``, so User A's scope is never returned for User B. ``frappe.local.cache``
    is per-request thread-local (no cross-request bleed), and ``frappe.set_user``
    resets ``local.cache = {}``, so a background job that switches users mid-run
    starts from an empty cache and re-resolves for the new user. The generator
    closes over the SAME ``user`` used as the key, so key and value can never
    disagree. A fresh ``list(...)`` is returned each call so a caller mutating the
    result cannot corrupt the cached scope.
    """
    return list(
        frappe.local_cache(
            cache_key,
            user,
            lambda: frappe.get_all(
                "User Permission",
                filters={"allow": allow, "user": user},
                pluck="for_value",
            ),
        )
    )


def scope_condition(user, is_unscoped_fn, allowed_fn, column):
    """SQL WHERE fragment restricting ``column`` to the user's allowed values.

    "" for unscoped users (no restriction); "1=0" when the user is scoped but has
    no allowed values (so they see nothing); ``column in (v1, v2, ...)`` otherwise.

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
    values = allowed_fn(user)
    if not values:
        return "1=0"
    escaped = ", ".join(frappe.db.escape(v) for v in values)
    return "{column} in ({values})".format(column=column, values=escaped)


def report_scope(user, is_unscoped_fn, allowed_fn):
    """Return ``(restrict, allowed_values)`` for report-side row scoping.

    ``restrict`` is False for unscoped oversight roles (the report applies no extra
    filter). When True the report must confine its rows to ``allowed_values`` (an
    empty list = a scoped user with no permitted tenant, i.e. the report returns no
    rows). Injected resolvers, same rationale as ``scope_condition``.
    """
    user = resolve_user(user)
    if is_unscoped_fn(user):
        return False, []
    return True, allowed_fn(user)
