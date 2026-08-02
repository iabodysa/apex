# Copyright (c) 2026, AFMCO and contributors
"""Shared low-level primitives for tenant row-scoping.

Habitat scopes on Building, Salis on Project, Logistay on Company, but the
underlying mechanics are identical: resolve the acting user, decide whether an
oversight role sees everything, read the user's allowed values from frappe's own
User Permission resolver, narrow them to the doctype being queried, and turn that
into a SQL WHERE fragment or a report-scope tuple. Those primitives live here ONCE;
``apex.habitat.permissions``, ``apex.salis.permissions`` and
``apex.logistay.permissions`` keep thin wrappers that bind their own oversight-role
set and ``allow`` doctype.

What is deliberately NOT here: the per-doctype ``*_query`` / ``*_has_permission``
wrappers and the scope-value resolution inside each ``has_permission`` (habitat's
``doc.building``/``doc.name``; salis' multi-hop ``_doc_project`` /
driver-chain / vehicle-chain). Those encode domain-specific knowledge and stay
local to each module.

Use ``allowed_for()`` / ``scope_condition()`` / ``report_scope()`` here instead of
re-implementing the pluck / fragment / tuple logic in a third scoping module.
"""

import frappe
from frappe import permissions as frappe_permissions


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

    ``hide_descendants`` on a row is never read here, and does not need to be: for a
    nested-set ``allow`` doctype it has ALREADY decided, inside
    ``get_user_permissions`` itself, which ``doc`` rows exist in ``rows`` below.
    ``user_permission.py:130`` unconditionally adds the permitted node; ``:132-135``
    — only when ``meta.is_nested_set()`` and ``not perm.hide_descendants`` — then
    adds one further row per descendant from ``frappe.db.get_descendants``. So a
    ``hide_descendants=1`` permission never had its descendants added in the first
    place, and this function returning every row's ``doc`` verbatim already carries
    that narrowing through untouched. Of apex's three scoped axes only ``Company``
    is a tree (``frappe.get_meta("Company").is_tree`` / ``is_nested_set()`` are
    True; Building and Project carry no ``lft``/``rgt``), so this only bites there —
    verified against a real Company parent/child on a live site and pinned by
    ``test_permission_scope_hide_descendants.py``.
    """
    del cache_key
    rows = frappe_permissions.get_user_permissions(user).get(allow) or []
    return [row.get("doc") for row in rows]


def for_doctype(user, allow, doctype, values):
    """Drop values whose User Permission rows ALL name a DIFFERENT doctype.

    A User Permission carrying ``applicable_for`` restricts that permission to one
    doctype; frappe applies it exactly this way when it builds its own match
    conditions (``frappe/model/db_query.py:1095-1109``): a row with no
    ``applicable_for`` counts for every doctype, a row naming this doctype counts
    for it, and a row naming another doctype counts for nothing here. Without this,
    a Building permission granted for Safety Round alone would also unlock every
    other Building-scoped doctype for that user.

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

    ``is_unscoped_fn`` / ``allowed_fn`` are the calling MODULE's own single-arg
    resolvers (``_building_is_unscoped`` / ``_allowed_buildings`` for Building;
    ``_is_unscoped`` / ``_allowed_projects`` for Project). They are injected — not
    re-derived here from raw config — so each module's oversight-role set and cache
    namespace stay bound in that module, and so those module-level resolvers remain
    the single override/stub point the scoped permission test-suite drives.

    ``allow`` + ``doctype`` narrow the resolved values to the permissions that apply
    to the doctype being queried (see ``for_doctype``). Frappe hands the doctype to
    every ``permission_query_conditions`` hook that declares the argument
    (``frappe/model/db_query.py:1130``), so the caller has it; when it is absent the
    values are used as resolved.
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
