# Copyright (c) 2026, afmcoltd
"""Refuse a Report role its ``ref_doctype`` cannot grant ``report``.

That guard reads JSON off disk, so it cannot see a Report created in the DATABASE. This
hook is the runtime half. It is not a second copy of the static scan: the static scan
asks "does the app SHIP a broken link", this one asks "is this SAVE about to create a
broken audience", and only the second one sees a site-local report.
"""

from __future__ import annotations

import frappe

_APP = "apex"

_ALWAYS_PERMITTED = frozenset({"Administrator"})

_MESSAGE = (
    "{0} does not grant {1} the Report permission, so a user holding only {1} sees this "
    "report and gets a PermissionError on opening it. Either grant report on {0} to {1} "
    "in a permlevel-0 row that is not if_owner, or remove {1} from this report's Roles."
)

_TITLE = "Report Role Cannot Run This Report"

_MIGRATION_FLAGS = ("in_migrate", "in_install", "in_patch", "in_import")


def _roles_with_report_right(permissions, istable):
    """Roles for which ``has_permission(ref_doctype, "report")`` is True.

    ``permissions`` is any sequence of mapping-like DocPerm rows (``meta.permissions``
    under a bench, plain dicts under the colocated unit tests). Pure, so the refusal
    can be proven without a site."""
    if istable:
        return set()
    return {
        row.get("role")
        for row in permissions or []
        if row.get("role")
        and row.get("report")
        and not row.get("if_owner")
        and not int(row.get("permlevel") or 0)
    }


def denied_roles(permissions, istable, named_roles):
    """Roles named on a report that its ref_doctype would refuse ``report`` to."""
    allowed = _roles_with_report_right(permissions, istable)
    return sorted({role for role in named_roles if role} - allowed - _ALWAYS_PERMITTED)


def _named_roles(doc):
    """Returns the role names listed in a report's Roles child table."""
    return [row.get("role") for row in (doc.get("roles") or [])]


def _stored_roles(doc):
    """Roles already persisted on this report, so a pre-existing offender only warns."""
    previous = doc.get_doc_before_save()
    if not previous:
        return set()
    return {row.get("role") for row in (previous.get("roles") or []) if row.get("role")}


def _apex_owns(ref_doctype):
    """True only when apex ships the DocType whose DocPerms are being judged."""
    module = frappe.db.get_value("DocType", ref_doctype, "module")
    if not module:
        return False
    return frappe.local.module_app.get(frappe.scrub(module)) == _APP


def _in_migration():
    """Returns whether a migrate, install, patch, or import is currently in progress."""
    return any(frappe.flags.get(flag) for flag in _MIGRATION_FLAGS)


def validate(doc, method=None):
    """Refuse any role this report's ``ref_doctype`` cannot grant ``report``."""
    ref = doc.get("ref_doctype")
    if not ref or not _apex_owns(ref):
        return

    meta = frappe.get_meta(ref)
    offenders = denied_roles(meta.permissions, meta.istable, _named_roles(doc))
    if not offenders:
        return

    added = [role for role in offenders if role not in _stored_roles(doc)]
    if added and not _in_migration():
        frappe.throw(_message(ref, added), title=_TITLE)

    frappe.msgprint(_message(ref, offenders), title=_TITLE, indicator="orange")


def _message(ref_doctype, roles):
    """Formats the report-role-mismatch message once per denied role."""
    return "\n".join(frappe._(_MESSAGE).format(ref_doctype, role) for role in roles)
