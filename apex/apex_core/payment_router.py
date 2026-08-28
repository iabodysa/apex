# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import erpnext
import frappe
from frappe import _
from frappe.model import default_fields
from frappe.utils import cint

SETTINGS_DOCTYPE = "Habitat Settings"

SOURCE_DOCTYPE = "Salis Payment Request"

DEFAULT_TARGET_DOCTYPE = "Payment Request"

LINK_DOCTYPE_FIELD = "linked_payment_doctype"
LINK_NAME_FIELD = "linked_payment_entry"

def get_target_doctype(settings=None) -> str:
    settings = settings or frappe.get_single(SETTINGS_DOCTYPE)
    return settings.target_payment_doctype or DEFAULT_TARGET_DOCTYPE

@frappe.whitelist()
def get_target_payment_doctype() -> str:
    return get_target_doctype()

def validate_configured_target(built_doctype: str) -> None:
    configured = get_target_doctype()
    if configured == built_doctype:
        return
    frappe.throw(
        _(
            "This site is configured to raise payments as {0}, but this action can only create a {1} allocated against the supplier's invoice. Raise this payment from a {2}, which builds the configured target, or set Target Payment DocType to {1} in Habitat Settings."
        ).format(_(configured), _(built_doctype), _(SOURCE_DOCTYPE)),
        title=_("Payment Target Mismatch"),
    )

def validate_target_doctype(target_doctype) -> None:
    target_doctype = (target_doctype or "").strip()
    if not target_doctype:
        frappe.throw(
            _("No payment target is set and no default could be resolved, so no payment can be created."),
            title=_("Invalid Payment Target"),
        )
    if not frappe.db.exists("DocType", target_doctype):
        frappe.throw(
            _(
                "Payment target {0} is not installed on this site. Choose a payment DocType that exists here, or clear the Target Payment DocType to use the native {1}."
            ).format(target_doctype, DEFAULT_TARGET_DOCTYPE),
            title=_("Invalid Payment Target"),
        )
    meta = frappe.get_meta(target_doctype)
    if meta.issingle:
        frappe.throw(
            _(
                "Payment target {0} is a Single settings record, so creating a payment would overwrite it instead of adding one. Choose a normal payment DocType."
            ).format(target_doctype),
            title=_("Invalid Payment Target"),
        )
    if meta.istable:
        frappe.throw(
            _(
                "Payment target {0} is a child table row, which cannot exist on its own. Choose the parent payment DocType instead."
            ).format(target_doctype),
            title=_("Invalid Payment Target"),
        )

def validate_field_map(target_doctype, field_map) -> None:
    target_meta = frappe.get_meta(target_doctype)
    writable = set(target_meta.get_valid_columns())
    source_meta = frappe.get_meta(SOURCE_DOCTYPE)
    seen = set()
    for row in field_map or []:
        target_field = (row.target_fieldname or "").strip()
        if not target_field:
            frappe.throw(
                _("Field Map row {0}: Target Fieldname is required.").format(row.idx)
            )
        if target_field in seen:
            frappe.throw(
                _("Field Map row {0}: Target Fieldname {1} is mapped more than once.").format(
                    row.idx, target_field
                )
            )
        seen.add(target_field)
        if target_field not in writable:
            frappe.throw(
                _(
                    "Field Map row {0}: {1} is not a field on the target payment DocType {2}, so it would be dropped and the payment created without it. Fix the fieldname."
                ).format(row.idx, target_field, target_doctype),
                title=_("Invalid Payment Field Map"),
            )
        if row.is_static:
            if (row.source_fieldname or "").strip():
                frappe.throw(
                    _("Field Map row {0}: clear Source Fieldname on a Static row.").format(
                        row.idx
                    )
                )
            continue
        source_field = (row.source_fieldname or "").strip()
        if not source_field:
            frappe.throw(
                _("Field Map row {0}: Source Fieldname is required when the row is not Static.").format(
                    row.idx
                )
            )
        if not (source_meta.has_field(source_field) or source_field in default_fields):
            frappe.throw(
                _(
                    "Field Map row {0}: {1} is not a field on {2}, so the target field would be written blank. Fix the fieldname."
                ).format(row.idx, source_field, SOURCE_DOCTYPE),
                title=_("Invalid Payment Field Map"),
            )

def _default_currency(source) -> str:
    company = source.get("company")
    if company:
        currency = frappe.get_cached_value("Company", company, "default_currency")
        if currency:
            return currency
    return erpnext.get_default_currency() or ""

def _ensure_target_currency(target, source) -> None:
    if not target.meta.has_field("currency"):
        return
    if target.get("currency"):
        return
    target.currency = _default_currency(source)

def _is_finance_approved(source) -> bool:
    return bool(source.get("finance_approved_by"))

def _apply_field_map(target, source, field_map) -> None:
    for row in field_map:
        target_field = (row.target_fieldname or "").strip()
        if not target_field:
            continue
        if row.is_static:
            value = row.static_value
        else:
            source_field = (row.source_fieldname or "").strip()
            value = source.get(source_field) if source_field else None
        target.set(target_field, value)

def route_payment(payment_request: str) -> str:
    settings = frappe.get_single(SETTINGS_DOCTYPE)
    target_doctype = get_target_doctype(settings)

    source = frappe.get_doc(SOURCE_DOCTYPE, payment_request, for_update=True)

    frappe.has_permission(SOURCE_DOCTYPE, "write", doc=source, throw=True)
    frappe.has_permission(SOURCE_DOCTYPE, "submit", doc=source, throw=True)

    if not _is_finance_approved(source):
        frappe.throw(
            _("This payment request is not finance-approved yet; it cannot be paid.")
        )

    if not source.docstatus.is_submitted():
        frappe.throw(
            _("Payment request {0} is {1}; only a submitted, finance-approved request can be paid.").format(
                source.name, _(source.get("status") or "not submitted")
            )
        )

    if source.linked_payment_entry:
        return source.linked_payment_entry

    validate_target_doctype(target_doctype)
    validate_field_map(target_doctype, settings.field_map or [])

    target = frappe.new_doc(target_doctype)
    _apply_field_map(target, source, settings.field_map or [])
    _ensure_target_currency(target, source)
    frappe.has_permission(target_doctype, "create", throw=True)
    target.insert()

    if (
        settings.auto_submit_target
        and target.meta.is_submittable
        and bool(cint(frappe.db.get_single_value("Habitat Settings", "enable_gl_posting")))
    ):
        target.submit()

    source.db_set(
        {LINK_DOCTYPE_FIELD: target.doctype, LINK_NAME_FIELD: target.name}
    )

    return target.name

@frappe.whitelist(methods=["POST"])
def create_routed_payment(payment_request: str) -> str:
    return route_payment(payment_request)
