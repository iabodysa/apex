# Copyright (c) 2026, afmcoltd

import frappe
from frappe import permissions as frappe_permissions

from apex.apex_core.utils.portal_identity import CAPACITY_USERS

PORTAL_CAPACITY_USERS = frozenset(CAPACITY_USERS.values())

PORTAL_CAPACITY_PTYPES = frozenset({"create", "write", "submit"})


def resolve_user(user=None):
    return user or frappe.session.user


def is_unscoped(user, unscoped_roles):
    if user in ("Administrator", "Guest"):
        return user == "Administrator"
    return bool(set(frappe.get_roles(user)) & unscoped_roles)


def is_portal_capacity(user):
    return user in PORTAL_CAPACITY_USERS


def portal_capacity_verdict(ptype):
    return None if ptype in PORTAL_CAPACITY_PTYPES else False


def allowed_for(user, allow, cache_key):
    del cache_key
    rows = frappe_permissions.get_user_permissions(user).get(allow) or []
    return [row.get("doc") for row in rows]


def for_doctype(user, allow, doctype, values):
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
    user = resolve_user(user)
    if is_unscoped_fn(user):
        return ""
    values = for_doctype(user, allow, doctype, allowed_fn(user))
    if not values:
        return "1=0"
    escaped = ", ".join(frappe.db.escape(v) for v in values)
    return "{column} in ({values})".format(column=column, values=escaped)


def report_scope(user, is_unscoped_fn, allowed_fn, allow=None, doctype=None):
    user = resolve_user(user)
    if is_unscoped_fn(user):
        return False, []
    return True, for_doctype(user, allow, doctype, allowed_fn(user))


def quote_column(field):
    return "`{0}`".format(field)


def render_column(spec, escaped):
    return "{column} in ({values})".format(column=quote_column(spec["field"]), values=escaped)


def render_dual(spec, escaped):
    return "({first} in ({values}) or {second} in ({values}))".format(
        first=quote_column(spec["first"]), second=quote_column(spec["second"]), values=escaped
    )


def render_fragment(kind, spec, values, fragments):
    render = fragments.get(kind)
    if not render:
        return "1=0"
    return render(spec, ", ".join(frappe.db.escape(value) for value in values))
