# Copyright (c) 2026, afmcoltd
"""Custody Issue controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, getdate

from apex.apex_core.utils.party_link import sync_party_employee
from apex.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import (
    get_store_balance,
    has_stock_entries,
    post_stock_entry,
    reverse_and_mark_cancelled,
    validate_reversal_allowed,
)


class CustodyIssue(Document):
    pass


def validate(doc, method=None):
    """Syncs holder user, requires positive-qty items, checks serials, and defaults return date."""
    sync_party_employee(doc, employee_field="issued_to_employee")
    _set_holder_user(doc)
    for row in doc.items:
        if (row.qty or 0) <= 0:
            frappe.throw(_("Row {0}: Qty must be greater than zero.").format(row.idx))
    validate_serialized_rows(doc)
    _snapshot_unit_values(doc)
    _set_expected_return_date(doc)


def _snapshot_unit_values(doc):
    """Freeze each line's unit value from the article master the first time it is written.

    The worker signs the receipt against the value printed beside each article, so a later
    edit to the article's standard cost must not move what he signed. Only a blank value is
    filled, which leaves an operator override and every already-issued line untouched.
    """
    for row in doc.items:
        if row.unit_value or not row.article:
            continue
        row.unit_value = frappe.db.get_value("Custody Article", row.article, "standard_unit_cost") or 0


def _set_holder_user(doc):
    """Mirror the holder's login user from the employee so receipt notifications
    have a real address to send to (a notification recipient field must hold an
    email/user, not an Employee docname). Runs after the employee is synced; the
    declarative fetch_from on the form path can lag the controller-set employee."""
    doc.issued_to_user = (
        frappe.db.get_value("Employee", doc.issued_to_employee, "user_id")
        if doc.issued_to_employee
        else None
    )


def validate_serialized_rows(doc):
    """A serialized article is one physical unit per line: it needs a serial_no
    and qty must be 1. Shared by Custody Issue and Custody Return."""
    articles = [row.article for row in doc.items if row.article]
    if not articles:
        return
    serialized = set(frappe.get_all(
        "Custody Article",
        filters={"name": ["in", articles], "is_serialized": 1},
        pluck="name",
    ))
    for row in doc.items:
        if row.article not in serialized:
            continue
        if not (row.serial_no or "").strip():
            frappe.throw(_("Row {0}: Serial No is required for serialized article {1}.").format(row.idx, row.article))
        if (row.qty or 0) != 1:
            frappe.throw(_("Row {0}: Qty must be 1 for serialized article {1}.").format(row.idx, row.article))


def _set_expected_return_date(doc):
    """Default the return due date from the most conservative category window.
    Only fills when blank so a manual override is preserved; uses the maximum
    default_custody_days across the issued articles' categories."""
    if doc.expected_return_date or not doc.issue_date:
        return
    max_days = 0
    for row in doc.items:
        if not row.article:
            continue
        category = frappe.db.get_value("Custody Article", row.article, "category")
        if not category:
            continue
        days = frappe.db.get_value("Custody Asset Category", category, "default_custody_days") or 0
        max_days = max(max_days, int(days))
    if max_days > 0:
        doc.expected_return_date = add_days(getdate(doc.issue_date), max_days)


def on_submit(doc, method=None):
    """Blocks submission when store stock is short, marks the issue Issued, and posts custody stock."""
    _assert_source_availability(doc)
    doc.db_set("issued_by", frappe.session.user)
    doc.db_set("status", "Issued")
    _post_custody_stock(doc)


def _assert_source_availability(doc):
    """Reject the issue if the building store cannot cover the requested quantity
    for any article (aggregated per article, in case of duplicate rows).

    Mirrors Custody Handover's source-availability gate: issuing must
    not drive the store balance negative. Only the case where stock is actually
    posted is checked — an issue naming no holder at all moves no stock
    (see ``_post_custody_stock``), so it has nothing to verify."""
    if not _holder(doc)[1]:
        return
    needed = {}
    for row in doc.items:
        if not row.article:
            continue
        needed[row.article] = needed.get(row.article, 0) + (row.qty or 0)
    for article, qty in needed.items():
        available = get_store_balance("Custody Article", article, doc.building, for_update=True)
        if qty > available:
            frappe.throw(
                _("Cannot issue {0} unit(s) of {1} from {2}: only {3} available in the store.").format(
                    qty, article, doc.building, available
                )
            )


def _holder(doc):
    """The (party_type, party) this issue hands stock to. ``issued_to_employee`` is the
    older Employee-only field and still wins where it is set; otherwise the document's
    own party pair carries the holder, which is how a Temporary Worker is named."""
    if doc.get("issued_to_employee"):
        return "Employee", doc.issued_to_employee
    return doc.get("party_type"), doc.get("party")


def _post_custody_stock(doc):
    """Move stock from the building store into the holder's custody (same building) on
    the Accommodation Stock Ledger. Skipped for a free-text issue naming no holder."""
    party_type, party = _holder(doc)
    if not party or has_stock_entries("Custody Issue", doc.name):
        return
    for row in doc.items:
        post_stock_entry(item_type="Custody Article", item=row.article, qty=-(row.qty or 0),
                         building=doc.building, voucher_type="Custody Issue",
                         voucher_no=doc.name, voucher_detail_no=row.name, posting_date=doc.issue_date)
        post_stock_entry(item_type="Custody Article", item=row.article, qty=(row.qty or 0),
                         building=doc.building, party_type=party_type, party=party,
                         voucher_type="Custody Issue",
                         voucher_no=doc.name, voucher_detail_no=row.name, posting_date=doc.issue_date)


def before_cancel(doc, method=None):
    """Every refusal a cancel can raise lives here, before db_update() stamps
    docstatus 2 — so a refused issue is left submitted rather than reading as
    cancelled for the rest of the request. Read-only; writes nothing."""
    returned = frappe.get_all(
        "Custody Return",
        filters={"custody_issue": doc.name, "docstatus": 1},
        limit=1
    )
    if returned:
        frappe.throw(
            _("Cannot cancel Custody Issue {0} because it is referenced by active Custody Return {1}.").format(
                doc.name, returned[0].name
            )
        )
    validate_reversal_allowed("Custody Issue", doc.name)


def on_cancel(doc, method=None):
    """Reverses the posted custody stock movement, unnames the issuer, and marks the issue cancelled."""
    doc.db_set("issued_by", None)
    reverse_and_mark_cancelled(doc, "Custody Issue")
