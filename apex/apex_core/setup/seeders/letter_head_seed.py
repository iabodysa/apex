# Copyright (c) 2026, afmcoltd
import frappe

from apex.apex_core.utils.addresses import get_address_text
from apex.apex_core.utils.company import resolve_company
from apex.apex_core.utils.system_write import system_insert

LETTER_HEAD_NAME = "Apex"


def _company_identity(company):
    """Name, address line, tax id and contact of the company, as printable text."""
    row = frappe.db.get_value(
        "Company", company, ["company_name", "tax_id", "phone_no", "email"], as_dict=True
    ) or frappe._dict()
    return frappe._dict(
        name=row.get("company_name") or company,
        address=get_address_text("Company", company),
        tax_id=row.get("tax_id") or "",
        phone=row.get("phone_no") or "",
        email=row.get("email") or "",
    )


def _header_html(identity):
    """Letterhead banner: company name, address line, and tax id when registered."""
    lines = [f'<div style="font-size:15pt;font-weight:700;color:#072b1a">{identity.name}</div>']
    if identity.address:
        lines.append(
            f'<div style="font-size:8.5pt;color:#47584f;margin-top:2px">{identity.address}</div>'
        )
    if identity.tax_id:
        lines.append(
            f'<div style="font-size:8.5pt;color:#47584f">{frappe._("Tax ID")}: {identity.tax_id}</div>'
        )
    body = "".join(lines)
    return (
        '<div style="padding:0 0 8px;border-bottom:2px solid #00844e;'
        f'font-family:inherit">{body}</div>'
    )


def _footer_html(identity):
    """Letterhead footer: how to reach the company, kept to one printed line."""
    parts = [p for p in (identity.phone, identity.email) if p]
    contact = " · ".join(parts)
    return (
        '<div style="padding-top:6px;border-top:1px solid #ddd5c2;font-size:8pt;'
        f'color:#6f7e76;text-align:center">{contact}</div>'
    )


def seed_letter_head():
    """Create the Apex letter head from the configured company and make it default.

    Frappe renders a letter head on every print view, so a site without one prints
    documents that carry no company identity at all. Existing records are left
    alone: a customer who edited theirs keeps it.
    """
    company = resolve_company()
    if not company or frappe.db.exists("Letter Head", LETTER_HEAD_NAME):
        return

    identity = _company_identity(company)
    system_insert(frappe.get_doc(
        {
            "doctype": "Letter Head",
            "letter_head_name": LETTER_HEAD_NAME,
            "source": "HTML",
            "content": _header_html(identity),
            "footer_source": "HTML",
            "footer": _footer_html(identity),
            "is_default": 1,
            "disabled": 0,
        }
    ))

    if not frappe.db.get_value("Company", company, "default_letter_head"):
        frappe.db.set_value("Company", company, "default_letter_head", LETTER_HEAD_NAME)
