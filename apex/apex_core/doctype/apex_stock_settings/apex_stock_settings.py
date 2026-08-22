# Copyright (c) 2026, afmcoltd
"""The stock engine's policy, and the one place that answers whether a posting may land.

The engine is a no-GL quantity ledger over buildings. ERPNext's Stock Ledger Entry ships
three controls this one did not have — negative-stock refusal
(``erpnext/stock/stock_ledger.py:2174``), a period freeze
(``erpnext/stock/doctype/stock_ledger_entry/stock_ledger_entry.py:247``) and a backdating
role gate (``:308``) — and their absence was a real defect: ``get_store_balance`` carries no
date predicate, so a posting dated before the goods arrived passed every write-time check
while the date-scoped balance report showed the store negative for that day.

So the controls live here as settings rather than as three more checks scattered through
the callers, and ``assert_posting_allowed`` is called from the ledger's WRITE path. A guard
in the write path is an invariant; a guard in the caller is a convention the next voucher
type will not inherit.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, getdate, today

SETTINGS = "Apex Stock Settings"


class ApexStockSettings(Document):

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        allow_negative_stock: DF.Check
        backdating_days: DF.Int
        backdating_role: DF.Link | None
        enable_stock_engine: DF.Check
        require_active_store: DF.Check
        stock_frozen_upto: DF.Date | None

    def validate(self):
        if self.backdating_role and not cint(self.backdating_days):
            frappe.msgprint(
                _("A backdating role has no effect while the window is zero days."),
                indicator="orange",
            )


def policy() -> dict:
    """The engine's settings as plain values, cached for the request.

    Read through ``get_cached_doc`` so a posting loop does not fetch the Single per row.
    """
    doc = frappe.get_cached_doc(SETTINGS)
    return {
        "enabled": bool(cint(doc.enable_stock_engine)),
        "allow_negative": bool(cint(doc.allow_negative_stock)),
        "backdating_days": cint(doc.backdating_days),
        "backdating_role": doc.backdating_role,
        "frozen_upto": doc.stock_frozen_upto,
        "require_active_store": bool(cint(doc.require_active_store)),
    }


def assert_posting_allowed(building: str, posting_date=None) -> None:
    """Refuse a posting the policy does not allow, before any row is written.

    Three refusals, in the order that tells the operator the most: the engine is off, the
    period is frozen, the date is further back than the window allows. The store check is
    last because it is the one a supervisor can fix themselves.
    """
    p = policy()
    if not p["enabled"]:
        frappe.throw(_("The stock engine is switched off in Apex Stock Settings."))

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
    if date < earliest and not _may_backdate(p["backdating_role"]):
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


def _may_backdate(role) -> bool:
    """True when the session may post outside the window. System Manager always may."""
    roles = frappe.get_roles(frappe.session.user)
    return "System Manager" in roles or (bool(role) and role in roles)


def store_is_open(building: str) -> bool:
    """True when this building's store accepts a posting.

    The store IS the Building. A separate store record was built and then refused: the
    building already carries ``is_procurement_store``, the ledger already denormalises
    company and cost centre from it, and one active store per building would have made a
    second entity 1:1 with the first — a table of attributes wearing an entity's name.
    """
    if not building:
        return False
    row = frappe.get_cached_value(
        "Building", building, ["is_procurement_store", "store_is_active"], as_dict=True
    )
    return bool(row and cint(row.is_procurement_store) and cint(row.store_is_active))
