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


def _is_unscoped(user):
    return permission_scope.is_unscoped(user, UNSCOPED_ROLES)


def _company_condition(user, column="`company`"):
    """SQL WHERE fragment confining ``column`` to the user's allowed companies.

    "" for oversight roles, "1=0" for a scoped user with no company (sees
    nothing), ``company in (...)`` otherwise.
    """
    return permission_scope.scope_condition(user, _is_unscoped, _allowed_companies, column)


def report_company_scope(user=None):
    """``(restrict, allowed_companies)`` for report-side company scoping."""
    return permission_scope.report_scope(user, _is_unscoped, _allowed_companies)


# permission_query_conditions (list / report / link scoping)


def telecom_contract_query(user=None):
    return _company_condition(user)


def sim_card_query(user=None):
    return _company_condition(user)


def sim_custody_assignment_query(user=None):
    return _company_condition(user)


# has_permission (form / REST / direct-access scoping)


def company_scoped_has_permission(doc, ptype, user=None):
    """Deny a company-scoped user acting on a SIM record outside their companies.

    Returns None to defer to Frappe's default role/DocPerm resolution (oversight
    users and in-scope docs), or False to block. Deny-only and ptype-agnostic: an
    out-of-company doc is blocked for every action — read, write, submit, export —
    so a scoped user can neither open nor mutate another company's record directly
    through the form view or the REST resource, not just in list view. A doc with
    no company fails closed.
    """
    user = _resolve_user(user)
    if _is_unscoped(user):
        return None

    company = getattr(doc, "company", None)
    if not company:
        return False
    return None if company in _allowed_companies(user) else False
