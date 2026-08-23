# Copyright (c) 2026, afmcoltd
"""Company row-scoping for SIM Operations.

Habitat scopes on Building and Salis on Project; SIM Operations scopes on **Company**.
Every SIM Operations record (Telecom Contract, SIM Card, SIM Custody Assignment) stores
a ``company`` Link, so ONE strategy serves them all and ``COMPANY_SCOPE`` records only
which DocTypes are on the axis and which parent link re-reads the company at the create
check. Oversight roles (System Manager, Finance Manager, Internal Auditor) see every
company; a SIM Operations User is confined to the companies it holds a User Permission
for.

``company_scope_query`` emits the list fragment and ``company_scoped_has_permission``
answers the form / REST / submit check; Frappe hands the DocType to both hooks, so one
registration each in ``hooks.py`` covers every DocType, and adding a scoped DocType is
a row in ``COMPANY_SCOPE`` plus its two ``hooks.py`` entries.

The five scoping primitives are shared from ``apex.apex_core.utils.permission_scope`` —
this module only binds the SIM oversight-role set, the ``Company`` allow-doctype, and a
cache namespace that is DISTINCT from Habitat's buildings and Salis' projects so scopes
never collide in one request.

Two invariants hold on every path: "" (no restriction) for the Administrator and the
``UNSCOPED_ROLES`` oversight roles versus "1=0" (matches nothing) for a scoped user
holding no company — never the other way round — and fail closed, so a doc whose
company resolves through neither its own field nor its anchor link is DENIED.
"""

from __future__ import annotations

import frappe

from apex.apex_core.utils import permission_scope

UNSCOPED_ROLES = {
    "System Manager",
    "Finance Manager",
    "Internal Auditor",
}

COMPANY = "company"


def _allowed_companies(user):
    """Companies the user holds an explicit User Permission for (request-cached).

    Own cache namespace ``apex_allowed_companies`` — never shared with Habitat's
    ``apex_allowed_buildings`` or Salis' ``apex_allowed_projects`` — so a Company scope
    can never be served where a Building/Project scope was expected for the same user
    in one request.
    """
    return permission_scope.allowed_for(user, "Company", "apex_allowed_companies")


def _allowed_companies_for(user, doctype):
    """``_allowed_companies`` narrowed to the permissions that apply to ``doctype``.

    See ``permission_scope.for_doctype``: a User Permission carrying ``applicable_for``
    grants its company for that one DocType only.
    """
    return permission_scope.for_doctype(user, "Company", doctype, _allowed_companies(user))


def _is_unscoped(user):
    """True when the user is the Administrator or holds a company-oversight role."""
    return permission_scope.is_unscoped(user, UNSCOPED_ROLES)


def report_company_scope(user=None, doctype=None):
    """``(restrict, allowed_companies)`` for report-side company scoping.

    ``restrict`` is False for unscoped oversight roles (the report applies no extra
    filter). When True the report must confine its rows to ``allowed_companies``; an
    empty list means a scoped user with no permitted company, i.e. no rows.
    """
    return permission_scope.report_scope(
        user, _is_unscoped, _allowed_companies, allow="Company", doctype=doctype
    )


COMPANY_SCOPE = {
    "Telecom Contract": None,
    "SIM Card": ("telecom_contract", "Telecom Contract"),
    "SIM Custody Assignment": ("sim_card", "SIM Card"),
}


def company_scope_query(user=None, doctype=None):
    """WHERE fragment confining ``doctype``'s list/report view to the user's companies.

    Registered in ``hooks.py`` for every company-scoped DocType. "" for oversight
    roles, "1=0" for a scoped user with no company, ``company in (...)`` otherwise.
    """
    return permission_scope.scope_condition(
        user, _is_unscoped, _allowed_companies, "`company`", allow="Company", doctype=doctype
    )


def _doc_company(doc):
    """Resolve the company a SIM record belongs to, or None.

    Returns None when nothing resolves, so the caller still fails CLOSED.

    """
    company = getattr(doc, COMPANY, None)
    if company:
        return company

    anchor = COMPANY_SCOPE.get(getattr(doc, "doctype", None))
    if not anchor:
        return None
    fieldname, parent_doctype = anchor
    parent = getattr(doc, fieldname, None)
    if not parent:
        return None
    return frappe.db.get_value(parent_doctype, parent, COMPANY)


def company_scoped_has_permission(doc, ptype, user=None):
    """Deny a company-scoped user acting on a SIM record outside their companies.

    Returns None to defer to Frappe's default role/DocPerm resolution (oversight users
    and in-scope docs), or False to block. Never True.

    Deny-only and ptype-agnostic: an out-of-company doc is blocked for every action —
    read, write, submit, export — so a scoped user can neither open nor mutate another
    company's record directly through the form view or the REST resource, not just in
    list view. A doc whose company resolves through neither its own field nor its
    anchor link fails closed.
    """
    user = permission_scope.resolve_user(user)
    if _is_unscoped(user):
        return None

    company = _doc_company(doc)
    if not company:
        return False
    return None if company in _allowed_companies_for(user, doc.doctype) else False
