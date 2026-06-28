# Copyright (c) 2026, AFMCO and contributors
"""Shared company resolver.

One defaulting chain for the company applied to a transaction when it is not set
explicitly, shared by Habitat and Salis so both modules resolve a company the same
way:

    explicit module setting  ->  user company default  ->  global company default

Pure refactor of the chain that was duplicated across the two settings controllers
(and partly re-implemented at call sites such as ``arrivals_desk``). The
per-module setting is read with ``get_single_value`` so this util does not import,
load, or edit the Habitat/Salis Settings DocTypes — it only reads their stored
value through the field whose name each module uses.

Returns ``None`` when no company is configured anywhere; callers treat that as
"no company known" and post nothing that requires one.
"""

from __future__ import annotations

import frappe

# Per-module explicit-default field: (Single DocType, fieldname). The fieldname
# differs by module by historical design (Habitat: ``company``; Salis:
# ``default_company``) — read each through its own field, do not rename either.
_MODULE_COMPANY_FIELD = {
    "Habitat": ("Habitat Settings", "company"),
    "Salis": ("Salis Settings", "default_company"),
}


def resolve_company(module: str | None = None) -> str | None:
    """Resolve a company via explicit module setting -> user default -> global default.

    ``module`` (``"Habitat"`` / ``"Salis"``) selects which Single's explicit
    company field to consult first; ``None`` skips the module step and starts at
    the user default. Returns ``None`` when nothing is configured.
    """
    company = None
    if module:
        single, field = _MODULE_COMPANY_FIELD[module]
        company = frappe.db.get_single_value(single, field)
    if not company:
        company = frappe.defaults.get_user_default("Company")
    if not company:
        company = frappe.defaults.get_global_default("company")
    return company or None
