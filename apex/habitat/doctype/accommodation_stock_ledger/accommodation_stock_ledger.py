# Copyright (c) 2026, AFMCO Support Services Co. Ltd and contributors
# [#j03s5a]
"""Accommodation Stock Ledger — read-only, system-written quantity ledger for the
decentralized internal-store engine. Each Accommodation Building is its own store.
Rows are posted only through the helpers below (never created manually); a blank
employee means the stock sits unassigned in the building's store, a set employee
means it is in that employee's custody. Reversals are negative mirror entries, and
are refused outright when the mirror would drive a store or a custody holding
negative — the stock has already moved on and must be unwound in order.

WHY THE OVERSIGHT ROLES READ EVERY BUILDING'S CUSTODY (owner decision, 2026-07-27)
---------------------------------------------------------------------------------
Read this before re-raising the estate-wide grant; it has been raised and settled.

Finance Manager and Internal Auditor each hold a permlevel-0 row here granting read,
report, export, print, email and share, and both are named in ``HOUSING_UNSCOPED_ROLES``
(``habitat/permissions.py``), so ``accommodation_stock_ledger_query`` returns "" and
neither role is row-filtered to a building. Because ``employee`` ("Employee (Custodian)"),
``signed_qty`` and ``unit_cost`` sit at level 0, that is per-worker custody holdings with
a per-person value, estate-wide and exportable — the same figures ``Custody Outstanding by
Worker`` computes. This is KEPT DELIBERATELY: three matching grants across two records and
two roles (both roles here, Finance Manager again on Occupancy Snapshot) is a design, not
a slip, and oversight of custody value is the job these roles exist for. The scope decision
lives in the DocPerm row and in ``HOUSING_UNSCOPED_ROLES`` — never in a report's roles
table, which only clears ``Report.is_permitted``.

What makes the decision REVIEWABLE rather than permanent: this record carries ZERO
permission levels, so a level-0 read is every field. Under the field sensitivity model
(``apex_core/utils/field_sensitivity.py``) it is a first-tier candidate — once the levels
exist, this grant can be narrowed to the fields finance actually needs without touching
either role's scope at all. The decision was taken against today's all-or-nothing shape,
not against a considered one. ``test_accommodation_stock_ledger`` asserts the three grants
and the flat level, so a change to either forces this paragraph to be revisited."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, today


class AccommodationStockLedger(Document):
    pass


def on_doctype_update():
    """Composite index (is_cancelled, item_type, employee) serving the custody /
    stock-balance access path (active rows of an item type for an employee). Added
    here — not only via a patch — so fresh installs, which mark patches complete
    without running them, also get it. Runs on app sync + every migrate; idempotent."""
    # [#asl9cx]
    from apex.apex_core.utils.ledger_index import add_index_guarded

    add_index_guarded(
        "Accommodation Stock Ledger",
        ["is_cancelled", "item_type", "employee"],
        "idx_asl_cancel_type_emp",
    )


# [#swxhdr]
_MASTER_FIELDS = {
    "Custody Article": ("article_name", "unit_of_measure", "standard_unit_cost"),
    "Maintenance Material": ("material_name", "default_uom", "estimated_unit_cost"),
}


def _resolve_item(item_type: str, item: str):
    fields = _MASTER_FIELDS.get(item_type)
    if not fields:
        return (item, "", 0.0)
    vals = frappe.db.get_value(item_type, item, list(fields), as_dict=True) or {}
    return (vals.get(fields[0]) or item, vals.get(fields[1]) or "", flt(vals.get(fields[2])))


def post_stock_entry(*, item_type, item, qty, building, voucher_type, voucher_no,
                     voucher_detail_no=None, employee=None, posting_date=None,
                     from_building=None, to_building=None, remarks=None, reversal_of=None):
    """Insert one signed-quantity Stock Ledger row. Denormalises item name/uom/cost,
    company and cost center from the source masters/building."""
    item_name, uom, unit_cost = _resolve_item(item_type, item)
    company, cost_center = frappe.db.get_value(
        "Building", building, ["company", "default_cost_center"]
    ) or (None, None)
    doc = frappe.get_doc({
        "doctype": "Accommodation Stock Ledger",
        "posting_date": posting_date or today(),
        "company": company,
        "item_type": item_type,
        "item": item,
        "item_name": item_name,
        "uom": uom,
        "signed_qty": flt(qty),
        "unit_cost": unit_cost,
        "building": building,
        "cost_center": cost_center,
        "employee": employee,
        "from_building": from_building,
        "to_building": to_building,
        "voucher_type": voucher_type,
        "voucher_no": voucher_no,
        "voucher_detail_no": voucher_detail_no,
        "reversal_of": reversal_of,
        "remarks": remarks,
    })
    doc.insert(ignore_permissions=True)  # audit-ok
    return doc.name


def get_store_balance(item_type: str, item: str, building: str, employee=None,
                      for_update: bool = False) -> float:
    """Live signed-quantity balance for one item in a building's store (employee
    unset) or in an employee's custody (employee set). Sums non-cancelled rows.

    for_update: take a SELECT ... FOR UPDATE on the summed rows so the balance read
    is a locking current-read. A draining caller passes for_update=True to close the
    TOCTOU race where two concurrent transfers/handovers both read the same balance,
    both pass the availability check, and both post ship legs that drive the store
    negative. The locking read serializes the second drain behind the first commit;
    InnoDB predicate locking also blocks it from racing in a new mirror row."""
    Ledger = frappe.qb.DocType("Accommodation Stock Ledger")
    q = (
        frappe.qb.from_(Ledger)
        .select(Ledger.signed_qty)
        .where(Ledger.item_type == item_type)
        .where(Ledger.item == item)
        .where(Ledger.building == building)
        .where(Ledger.is_cancelled == 0)
    )
    q = q.where(Ledger.employee == employee) if employee else q.where(Ledger.employee.isnull())
    if for_update:
        q = q.for_update()
    rows = q.run(as_dict=True)
    return flt(sum(flt(r.signed_qty) for r in rows))


def has_stock_entries(voucher_type: str, voucher_no: str) -> bool:
    """Idempotency guard: True if this voucher already has live (non-cancelled) rows."""
    return bool(frappe.db.exists(
        "Accommodation Stock Ledger",
        {"voucher_type": voucher_type, "voucher_no": voucher_no, "is_cancelled": 0},
    ))


def _assert_reversal_keeps_stock_positive(rows) -> None:
    """A reversal moves real stock, it does not erase history: withdrawing a voucher
    whose goods have already left the store would drive that store negative. Refuse
    before writing any mirror row, so a blocked cancel leaves the ledger untouched."""
    drained: dict[tuple, float] = {}
    for r in rows:
        # A mirror posts -signed_qty, so a positive original DRAINS its bucket.
        key = (r.item_type, r.item, r.building, r.employee or None)
        drained[key] = drained.get(key, 0.0) + flt(r.signed_qty)
    for (item_type, item, building, employee), qty in drained.items():
        if flt(qty) <= 0:
            continue
        available = get_store_balance(item_type, item, building, employee, for_update=True)
        if flt(qty) <= available:
            continue
        # Two whole sentences rather than an interpolated fragment: Arabic word
        # order will not survive a translated clause dropped into a template.
        if employee:
            frappe.throw(
                _(
                    "Cannot reverse {0} unit(s) of {1} in {2}: employee {3} now holds only {4}. "
                    "Reverse the later movements first."
                ).format(flt(qty), item, building, employee, available)
            )
        frappe.throw(
            _(
                "Cannot reverse {0} unit(s) of {1} in {2}: only {3} left in the building store. "
                "Reverse the later movements first."
            ).format(flt(qty), item, building, available)
        )


def _live_rows(voucher_type: str, voucher_no: str):
    """The rows a reversal of this voucher would mirror: its not-yet-cancelled
    entries. One query shape shared by the refusal check and the reversal itself."""
    return frappe.get_all(
        "Accommodation Stock Ledger",
        filters={"voucher_type": voucher_type, "voucher_no": voucher_no, "is_cancelled": 0},
        fields=["name", "item_type", "item", "signed_qty", "building", "employee",
                "from_building", "to_building"],
    )


def assert_reversal_allowed(voucher_type: str, voucher_no: str) -> None:
    """REFUSAL half of a stock voucher's cancel — call from ``before_cancel``.

    Frappe runs before_cancel from run_before_save_methods() BEFORE db_update()
    stamps docstatus 2 (frappe/model/document.py:414 vs :428), while on_cancel runs
    after it from run_post_save_methods() (:431). A refusal raised from on_cancel
    therefore leaves docstatus 2 written in the open transaction, so everything that
    reads the voucher later in the same request sees it as cancelled and only the
    request-level rollback undoes it. Raised from here nothing is written at all:
    this function only reads, so a throw leaves the ledger AND the voucher untouched.

    The RESTORATION half (writing the mirror rows) stays in reverse_stock_entries,
    which on_cancel still runs."""
    _assert_reversal_keeps_stock_positive(_live_rows(voucher_type, voucher_no))


def reverse_stock_entries(voucher_type: str, voucher_no: str) -> None:
    """RESTORATION half: reverse (do not delete) all live rows of a voucher — post
    negative mirror entries and mark the originals cancelled. Idempotent.

    The positivity check runs again here rather than trusting the caller's
    before_cancel: this is also the entry point for reject_handover, which is not a
    docstatus transition and so has no before_cancel to hook, and re-reading inside
    the same transaction is free (the locking read already holds the rows)."""
    rows = _live_rows(voucher_type, voucher_no)
    _assert_reversal_keeps_stock_positive(rows)
    for r in rows:
        rev = post_stock_entry(
            item_type=r.item_type, item=r.item, qty=-flt(r.signed_qty), building=r.building,
            employee=r.employee, voucher_type=voucher_type, voucher_no=voucher_no,
            from_building=r.from_building, to_building=r.to_building,
            reversal_of=r.name, remarks="Reversal",
        )
        # [#4eui8g]
        frappe.db.set_value("Accommodation Stock Ledger", r.name, "is_cancelled", 1)
        frappe.db.set_value("Accommodation Stock Ledger", rev, "is_cancelled", 1)


def reverse_and_mark_cancelled(doc, voucher_type: str) -> None:
    """The whole on_cancel routine every stock voucher shares: reverse each ledger
    row this voucher posted, then stamp the voucher Cancelled. Reversal is keyed on
    voucher_type/voucher_no only, so it never reads the doc and the two steps are
    order-independent.

    Pair this with assert_reversal_allowed() in the voucher's before_cancel: that is
    where a voucher whose stock has already moved on is refused, early enough that
    docstatus 2 is never written. The re-check inside reverse_stock_entries stays as
    the backstop for callers that reach the ledger without a cancel."""
    reverse_stock_entries(voucher_type, doc.name)
    doc.db_set("status", "Cancelled")
