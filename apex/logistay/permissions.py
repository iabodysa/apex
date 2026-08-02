# Copyright (c) 2026, AFMCO and contributors
"""Company-scoped row security for SIM Operations.

Habitat scopes on Building and Salis on Project; SIM Operations scopes on
**Company**. Every SIM Operations record (Telecom Contract, SIM Card, SIM Custody
Assignment) carries a ``company`` Link, so one uniform condition/permission pair
scopes them all. Oversight roles (System Manager, Finance Manager, Internal
Auditor) see every company; a SIM Operations User is confined to the companies it
holds a User Permission for. The five scoping primitives are shared from
``apex.apex_core.utils.permission_scope`` — this module only binds the SIM
oversight-role set, the ``Company`` allow-doctype, and a cache namespace that is
DISTINCT from Habitat's buildings and Salis' projects so scopes never collide in
one request.
"""

from __future__ import annotations

import frappe

from apex.apex_core.utils import permission_scope

# Roles that see every company's SIM records (no company confinement).
UNSCOPED_ROLES = {
    "System Manager",
    "Finance Manager",
    "Internal Auditor",
}


def _resolve_user(user=None):
    return permission_scope.resolve_user(user)


def _allowed_companies(user):
    """Companies the user holds an explicit User Permission for (request-cached).

    Own cache namespace ``apex_allowed_companies`` — never shared with Habitat's
    ``apex_allowed_buildings`` or Salis' ``apex_allowed_projects`` — so a Company
    scope can never be served where a Building/Project scope was expected for the
    same user in one request.
    """
    return permission_scope.allowed_for(user, "Company", "apex_allowed_companies")


def _allowed_companies_for(user, doctype):
    """``_allowed_companies`` narrowed to the permissions that apply to ``doctype``.

    See ``permission_scope.for_doctype``: a User Permission carrying
    ``applicable_for`` grants its company for that one DocType only.
    """
    return permission_scope.for_doctype(user, "Company", doctype, _allowed_companies(user))


def _is_unscoped(user):
    return permission_scope.is_unscoped(user, UNSCOPED_ROLES)


def _company_condition(user, column="`company`", doctype=None):
    """SQL WHERE fragment confining ``column`` to the user's allowed companies.

    "" for oversight roles, "1=0" for a scoped user with no company (sees
    nothing), ``company in (...)`` otherwise.
    """
    return permission_scope.scope_condition(
        user, _is_unscoped, _allowed_companies, column, allow="Company", doctype=doctype
    )


def report_company_scope(user=None, doctype=None):
    """``(restrict, allowed_companies)`` for report-side company scoping."""
    return permission_scope.report_scope(
        user, _is_unscoped, _allowed_companies, allow="Company", doctype=doctype
    )


# permission_query_conditions (list / report / link scoping)


def telecom_contract_query(user=None, doctype=None):
    return _company_condition(user, doctype=doctype)


def sim_card_query(user=None, doctype=None):
    return _company_condition(user, doctype=doctype)


def sim_custody_assignment_query(user=None, doctype=None):
    return _company_condition(user, doctype=doctype)


# has_permission (form / REST / direct-access scoping)


COMPANY_FETCH_ANCHOR = {
    "SIM Card": ("telecom_contract", "Telecom Contract"),
    "SIM Custody Assignment": ("sim_card", "SIM Card"),
}


def _doc_company(doc):
    """Resolve the company a SIM record belongs to, or None.

    ``company`` is ``fetch_from`` on both child records (``telecom_contract.company`` /
    ``sim_card.company``), and ``Document.insert`` runs ``check_permission("create")``
    (document.py:300) BEFORE ``_validate_links()`` (:302) applies ``fetch_from`` — so at
    the create check it is EMPTY and reading it alone would deny a scoped SIM Operations
    User the creation of a card in their OWN company. Each anchor is the mandatory,
    never-fetched parent link the payload always carries; the company is re-read from it.

    Returns None when nothing resolves, so the caller still fails CLOSED.
    """
    company = getattr(doc, "company", None)
    if company:
        return company

    anchor = COMPANY_FETCH_ANCHOR.get(getattr(doc, "doctype", None))
    if not anchor:
        return None
    fieldname, parent_doctype = anchor
    parent = getattr(doc, fieldname, None)
    if not parent:
        return None
    return frappe.db.get_value(parent_doctype, parent, "company")


def company_scoped_has_permission(doc, ptype, user=None):
    """Deny a company-scoped user acting on a SIM record outside their companies.

    Returns None to defer to Frappe's default role/DocPerm resolution (oversight
    users and in-scope docs), or False to block. Deny-only and ptype-agnostic: an
    out-of-company doc is blocked for every action — read, write, submit, export —
    so a scoped user can neither open nor mutate another company's record directly
    through the form view or the REST resource, not just in list view. A doc whose
    company resolves through neither its own field nor its anchor link fails closed.
    """
    user = _resolve_user(user)
    if _is_unscoped(user):
        return None

    company = _doc_company(doc)
    if not company:
        return False
    return None if company in _allowed_companies_for(user, doc.doctype) else False
