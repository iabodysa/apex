# Copyright (c) 2026, afmcoltd
"""Accommodation Stock Ledger — read-only, system-written quantity ledger for the
decentralized internal-store engine. Each Accommodation Building is its own store.

``post_stock_entry`` inserts with ``ignore_permissions`` for the subledger reason: the DocType is
``in_create`` with no role holding create or write, so this is the only path a row can take, and
the permission that mattered was checked on the receipt or transfer that triggered it.
Rows are posted only through the helpers below (never created manually); a blank
holder means the stock sits unassigned in the building's store, a set holder means
it is in that holder's custody. The holder is ``party_type``/``party`` so a
Temporary Worker can hold stock as well as an Employee, and ``employee`` is still
written for Employee rows — the composite index and the oversight grant below both
read it. Reversals are negative mirror entries, and
are refused outright when the mirror would drive a store or a custody holding
negative — the stock has already moved on and must be unwound in order.

WHY THE OVERSIGHT ROLES READ EVERY BUILDING'S CUSTODY
----------------------------------------------------
Read this before re-raising the estate-wide grant; it is deliberate.

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
permission levels, so a level-0 read is every field. Give the record permission levels and
this grant narrows to the fields finance actually needs, without touching either role's
scope at all. The decision was taken against today's all-or-nothing shape,
not against a considered one. ``test_accommodation_stock_ledger`` asserts the three grants
and the flat level, so a change to either forces this paragraph to be revisited."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, today

from apex.apex_core.doctype.habitat_settings.habitat_settings import policy, validate_posting_allowed
from apex.apex_core.utils.ledger_index import add_index_guarded
from apex.habitat.utils.item_master import resolve_item

class AccommodationStockLedger(Document):
    pass

def on_doctype_update():
    """Composite index (is_cancelled, item_type, employee) serving the custody /
    stock-balance access path (active rows of an item type for an employee). Added
    here — not only via a patch — so fresh installs, which mark patches complete
    without running them, also get it. Runs on app sync + every migrate; idempotent."""
    add_index_guarded(
        "Accommodation Stock Ledger",
        ["is_cancelled", "item_type", "employee"],
        "idx_asl_cancel_type_emp",
    )
    add_index_guarded(
        "Accommodation Stock Ledger",
        ["is_cancelled", "item_type", "party"],
        "idx_asl_cancel_type_party",
    )

def _resolve_holder(employee, party_type, party):
    """The holder of a row as the (party_type, party, employee) triple every column
    needs. A caller may name the holder either way round: ``employee`` is the older
    Employee-only argument and is still honoured, ``party_type``/``party`` carry a
    Temporary Worker as well. Employee rows keep writing ``employee`` so the composite
    index and the permlevel-0 oversight grant described above still see them."""
    if party and not party_type:
        party_type = "Employee"
    if not party and employee:
        party_type, party = "Employee", employee
    if party_type == "Employee":
        employee = party
    elif party:
        employee = None
    return party_type or None, party or None, employee or None

def post_stock_entry(*, item_type, item, qty, building, voucher_type, voucher_no,
                     voucher_detail_no=None, employee=None, party_type=None, party=None,
                     posting_date=None, from_building=None, to_building=None,
                     remarks=None, reversal_of=None):
    """Insert one signed-quantity Stock Ledger row. Denormalises item name/uom/cost,
    company and cost center from the source masters/building."""
    party_type, party, employee = _resolve_holder(employee, party_type, party)
    if not reversal_of:
        _assert_policy_allows(item_type, item, qty, building, party_type, party, posting_date)
    item_name, uom, unit_cost = resolve_item(item_type, item)
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
        "party_type": party_type,
        "party": party,
        "from_building": from_building,
        "to_building": to_building,
        "voucher_type": voucher_type,
        "voucher_no": voucher_no,
        "voucher_detail_no": voucher_detail_no,
        "reversal_of": reversal_of,
        "remarks": remarks,
    })
    doc.insert(ignore_permissions=True)
    return doc.name

def _assert_policy_allows(item_type, item, qty, building, party_type, party, posting_date) -> None:
    """The engine's policy, applied where the row is WRITTEN rather than in each caller.

    A guard in the caller is a convention the next voucher type does not inherit — four of
    the five callers checked availability and one did not, which is how a check-in could
    drive a store below zero. Habitat Settings owns the three rules ERPNext ships and
    this ledger lacked: a period freeze, a backdating window, and negative-stock refusal.

    Reversals are exempt and pass ``reversal_of``: a mirror row must be able to unwind a
    posting whose date has since fallen outside the window, and its own positivity rule
    already lives in ``_assert_reversal_keeps_stock_positive``.
    """
    validate_posting_allowed(building, posting_date)

    if flt(qty) >= 0 or policy()["allow_negative"]:
        return
    available = get_store_balance(
        item_type, item, building, party_type=party_type, party=party, for_update=True
    )
    if abs(flt(qty)) > available:
        holder = party or _("the building store")
        frappe.throw(
            _("Cannot move {0} unit(s) of {1} out of {2}: {3} holds only {4}.").format(
                abs(flt(qty)), item, building, holder, available
            )
        )

def get_store_balance(item_type: str, item: str, building: str, employee=None,
                      for_update: bool = False, party_type=None, party=None) -> float:
    """Live signed-quantity balance for one item in a building's store (employee
    unset) or in an employee's custody (employee set). Sums non-cancelled rows.

    Built with ``frappe.qb`` (frappe/query_builder) because two things
    ``frappe.get_all`` cannot do are needed together: SUM the signed quantities in the
    database, and take a row lock on what it summed.

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
    holder_type, holder, _ = _resolve_holder(employee, party_type, party)
    if holder:
        q = q.where(Ledger.party == holder).where(Ledger.party_type == holder_type)
    else:
        q = q.where(Ledger.party.isnull())
    if for_update:
        q = q.for_update()
    rows = q.run(as_dict=True)
    return flt(sum(flt(r.signed_qty) for r in rows))

def has_stock_entries(voucher_type: str, voucher_no: str) -> bool:
    """Idempotency guard: True if this voucher already has live (non-cancelled) rows.

    Takes the SOURCE row's write lock before reading, so two callers posting the same
    voucher serialize and the second sees the first's rows. Without it the read is a
    check-then-insert that nothing enforces: both pass, both post, and a building's
    stock balance doubles with no error. The lock is here rather than in each caller
    because a guard the next voucher type does not inherit is not a guard.

    A unique index cannot do this job: one voucher legitimately posts many rows — a
    pair per detail line for the two ends of a movement, three where a checkout splits
    returned from missing — so no column tuple identifies a single posting.

    Callers hold the lock until their transaction ends, which is the point: it spans
    the read and the inserts that follow it."""
    frappe.db.get_value(voucher_type, voucher_no, "name", for_update=True)
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
        holder = r.party or r.employee or None
        holder_type = r.party_type or ("Employee" if r.employee else None)
        key = (r.item_type, r.item, r.building, holder_type, holder)
        drained[key] = drained.get(key, 0.0) + flt(r.signed_qty)
    for (item_type, item, building, holder_type, holder), qty in drained.items():
        if flt(qty) <= 0:
            continue
        available = get_store_balance(item_type, item, building, party_type=holder_type,
                                      party=holder, for_update=True)
        if flt(qty) <= available:
            continue
        if holder:
            frappe.throw(
                _(
                    "Cannot reverse {0} unit(s) of {1} in {2}: {3} now holds only {4}. "
                    "Reverse the later movements first."
                ).format(flt(qty), item, building, holder, available)
            )
        frappe.throw(
            _(
                "Cannot reverse {0} unit(s) of {1} in {2}: only {3} left in the building store. "
                "Reverse the later movements first."
            ).format(flt(qty), item, building, available)
        )

def validate_reversal_allowed(voucher_type: str, voucher_no: str) -> None:
    """REFUSAL half of a stock voucher's cancel — call from ``before_cancel``.

    The RESTORATION half (writing the mirror rows) stays in reverse_stock_entries,
    which on_cancel still runs.
    """
    _assert_reversal_keeps_stock_positive(frappe.get_all(
        "Accommodation Stock Ledger",
        filters={"voucher_type": voucher_type, "voucher_no": voucher_no, "is_cancelled": 0},
        fields=["name", "item_type", "item", "signed_qty", "building", "employee",
                "party_type", "party", "from_building", "to_building"],
    ))

def reverse_stock_entries(voucher_type: str, voucher_no: str) -> None:
    """RESTORATION half: reverse (do not delete) all live rows of a voucher — post
    negative mirror entries and mark the originals cancelled. Idempotent.

    The positivity check runs again here rather than trusting the caller's
    before_cancel: this is also the entry point for reject_handover, which is not a
    docstatus transition and so has no before_cancel to hook, and re-reading inside
    the same transaction is free (the locking read already holds the rows)."""
    rows = frappe.get_all(
        "Accommodation Stock Ledger",
        filters={"voucher_type": voucher_type, "voucher_no": voucher_no, "is_cancelled": 0},
        fields=["name", "item_type", "item", "signed_qty", "building", "employee",
                "party_type", "party", "from_building", "to_building"],
    )
    _assert_reversal_keeps_stock_positive(rows)
    for r in rows:
        rev = post_stock_entry(
            item_type=r.item_type, item=r.item, qty=-flt(r.signed_qty), building=r.building,
            party_type=r.party_type, party=r.party or r.employee,
            voucher_type=voucher_type, voucher_no=voucher_no,
            from_building=r.from_building, to_building=r.to_building,
            reversal_of=r.name, remarks="Reversal",
        )
        frappe.db.set_value("Accommodation Stock Ledger", r.name, "is_cancelled", 1)
        frappe.db.set_value("Accommodation Stock Ledger", rev, "is_cancelled", 1)

def reverse_and_mark_cancelled(doc, voucher_type: str) -> None:
    """The whole on_cancel routine every stock voucher shares: reverse each ledger
    row this voucher posted, then stamp the voucher Cancelled. Reversal is keyed on
    voucher_type/voucher_no only, so it never reads the doc and the two steps are
    order-independent.

    Pair this with validate_reversal_allowed() in the voucher's before_cancel: that is
    where a voucher whose stock has already moved on is refused, early enough that
    docstatus 2 is never written. The re-check inside reverse_stock_entries stays as
    the backstop for callers that reach the ledger without a cancel."""
    reverse_stock_entries(voucher_type, doc.name)
    doc.db_set("status", "Cancelled")
