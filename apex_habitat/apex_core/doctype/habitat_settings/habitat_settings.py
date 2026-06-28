# Copyright (c) 2026, AFMCO and contributors
"""Habitat Settings controller.

Single DocType holding global integration toggles. All defaults are
conservative: no financial posting unless explicitly enabled.
"""

from __future__ import annotations

import frappe
from frappe.model.document import Document


class HabitatSettings(Document):
    pass


def before_save(doc, method=None):
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw("Only System Manager can modify Habitat Settings.")

    # Salary-deduction config (housing/damage) moved to the Salary Deduction Policy;
    # its authorization gate is enforced there, not here.

    roles = frappe.get_roles(frappe.session.user)
    doc.last_modified_by_role = roles[0] if roles else ""


def get_settings() -> Document:
    """Return the Habitat Settings single document."""
    return frappe.get_single("Habitat Settings")


def get_default_company() -> str | None:
    """Resolve the company applied to Habitat transactions when not set explicitly.

    Thin wrapper over the shared resolver (explicit Habitat Settings ``company``
    -> user company default -> global company default), so Habitat resolves a
    company the same way Salis does. Returns ``None`` when none is configured.
    """
    from apex_habitat.apex_core.utils.company import resolve_company

    return resolve_company("Habitat")


def get_default_currency() -> str | None:
    """Return the default currency from Habitat Settings (fetched from Company)."""
    return frappe.db.get_single_value("Habitat Settings", "default_currency") or None


def validate_posting_period(company: str, posting_date: str) -> None:
    """Raise if posting_date falls inside a closed ERPNext Accounting Period.

    Only checked when the Accounting Period DocType exists (ERPNext is present)
    and a company is known. Silently passes if ERPNext is not installed.
    """
    if not company or not posting_date:
        return
    if not frappe.db.exists("DocType", "Accounting Period"):
        return
    closed = frappe.db.get_value(
        "Accounting Period",
        {
            "company": company,
            "start_date": ["<=", posting_date],
            "end_date": [">=", posting_date],
            "closed": 1,
        },
        "name",
    )
    if closed:
        frappe.throw(
            frappe._(
                "Posting date {0} falls inside closed Accounting Period {1} for company {2}."
            ).format(posting_date, closed, company)
        )
