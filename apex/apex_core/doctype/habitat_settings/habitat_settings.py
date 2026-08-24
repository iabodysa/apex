# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, getdate, today

from apex.apex_core.payment_router import (
    get_target_doctype,
    validate_field_map,
    validate_target_doctype,
)

RETENTION_DEFAULTS = {
    "snapshot_retention_days": 365,
    "depreciation_snapshot_retention_days": 730,
}

SETTINGS_DOCTYPE = "Habitat Settings"


class HabitatSettings(Document):
    def validate(self):
        target = get_target_doctype(self)
        validate_target_doctype(target)
        validate_field_map(target, self.field_map or [])
        if self.backdating_role and not cint(self.backdating_days):
            frappe.msgprint(
                _("A backdating role has no effect while the window is zero days."),
                indicator="orange",
            )


def before_save(doc, method=None):
    roles = frappe.get_roles(frappe.session.user)
    doc.last_modified_by_role = roles[0] if roles else ""


def retention_days(key: str) -> int:
    if key not in RETENTION_DEFAULTS:
        raise KeyError(key)
    value = frappe.db.get_single_value(SETTINGS_DOCTYPE, key)
    return cint(value) if value else RETENTION_DEFAULTS[key]


def effective_retention_days(key: str, days: int | None = None) -> int:
    if key not in RETENTION_DEFAULTS:
        raise KeyError(key)
    if days is None or cint(days) == RETENTION_DEFAULTS[key]:
        return retention_days(key)
    return cint(days)


def policy() -> dict:
    doc = frappe.get_cached_doc(SETTINGS_DOCTYPE)
    return {
        "enabled": bool(cint(doc.enable_stock_engine)),
        "allow_negative": bool(cint(doc.allow_negative_stock)),
        "backdating_days": cint(doc.backdating_days),
        "backdating_role": doc.backdating_role,
        "frozen_upto": doc.stock_frozen_upto,
        "require_active_store": bool(cint(doc.require_active_store)),
    }


def validate_posting_allowed(building: str, posting_date=None) -> None:
    p = policy()
    if not p["enabled"]:
        frappe.throw(_("The stock engine is switched off in Habitat Settings."))

    date = getdate(posting_date or today())
    if date > getdate(today()):
        frappe.throw(_("A posting cannot be dated in the future."))

    if p["frozen_upto"] and date <= getdate(p["frozen_upto"]):
        frappe.throw(
            _("Stock is frozen up to {0}. Nothing can be posted on or before that date.").format(
                frappe.format(p["frozen_upto"], {"fieldtype": "Date"})
            )
        )

    earliest = frappe.utils.add_days(getdate(today()), -p["backdating_days"])
    if date < earliest and not _holds_role(p["backdating_role"]):
        frappe.throw(
            _("A posting cannot be dated before {0}. Ask a {1} to post it.").format(
                frappe.format(earliest, {"fieldtype": "Date"}),
                _(p["backdating_role"]) if p["backdating_role"] else _("System Manager"),
            )
        )
    if p["require_active_store"] and building and not store_is_open(building):
        frappe.throw(
            _("The store at {0} is closed, so nothing can be posted to it.").format(building)
        )


def _holds_role(role) -> bool:
    roles = frappe.get_roles(frappe.session.user)
    return "System Manager" in roles or (bool(role) and role in roles)


def store_is_open(building: str) -> bool:
    if not building:
        return False
    row = frappe.get_cached_value(
        "Building", building, ["is_procurement_store", "store_is_active"], as_dict=True
    )
    return bool(row and cint(row.is_procurement_store) and cint(row.store_is_active))
