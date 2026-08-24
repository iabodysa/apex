# Copyright (c) 2026, afmcoltd

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
    return permission_scope.allowed_for(user, "Company", "apex_allowed_companies")


def _allowed_companies_for(user, doctype):
    return permission_scope.for_doctype(user, "Company", doctype, _allowed_companies(user))


def _is_unscoped(user):
    return permission_scope.is_unscoped(user, UNSCOPED_ROLES)


def report_company_scope(user=None, doctype=None):
    return permission_scope.report_scope(
        user, _is_unscoped, _allowed_companies, allow="Company", doctype=doctype
    )


COMPANY_SCOPE = {
    "Telecom Contract": None,
    "SIM Card": ("telecom_contract", "Telecom Contract"),
    "SIM Custody Assignment": ("sim_card", "SIM Card"),
}


def company_scope_query(user=None, doctype=None):
    return permission_scope.scope_condition(
        user, _is_unscoped, _allowed_companies, "`company`", allow="Company", doctype=doctype
    )


def _doc_company(doc):
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
    user = permission_scope.resolve_user(user)
    if _is_unscoped(user):
        return None

    company = _doc_company(doc)
    if not company:
        return False
    return None if company in _allowed_companies_for(user, doc.doctype) else False
