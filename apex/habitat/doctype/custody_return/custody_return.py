# Copyright (c) 2026, afmcoltd
"""Custody Return controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from apex.apex_core.utils.party_link import sync_party_employee
from apex.habitat.doctype.custody_issue.custody_issue import validate_serialized_rows


class CustodyReturn(Document):
    pass


def validate(doc, method=None):
    """Blocks a return with no items, a non-positive qty, bad serials, or qty over what was issued."""
    sync_party_employee(doc, employee_field="returned_by_employee")
    for row in doc.items:
        if (row.qty or 0) <= 0:
            frappe.throw(_("Row {0}: Qty must be greater than zero.").format(row.idx))
    validate_serialized_rows(doc)
    _link_issue_lines(doc)
    _validate_return_quantities(doc)


def _link_issue_lines(doc):
    """Resolve every return line to the issue line it answers, once, on save.

    Without it the receipt re-matches article and serial each time it prints, so the
    reconciliation the paper shows depends on when it was printed rather than on what was
    agreed. A serial identifies its line outright; an unserialised article resolves only
    while exactly one issue line carries it, because a guess is worse than a blank. A line
    that resolves to nothing is cleared, so re-pointing a return never leaves a stale
    reference behind.
    """
    issue_rows = frappe.get_all(
        "Custody Issue Item",
        filters={"parent": doc.custody_issue, "parenttype": "Custody Issue"},
        fields=["name", "article", "serial_no"],
    ) if doc.custody_issue else []

    by_serial = {
        (row.article, (row.serial_no or "").strip()): row.name
        for row in issue_rows
        if (row.serial_no or "").strip()
    }
    by_article = {}
    for row in issue_rows:
        by_article.setdefault(row.article, []).append(row.name)

    for row in doc.items:
        serial = (row.serial_no or "").strip()
        match = by_serial.get((row.article, serial)) if serial else None
        if not match:
            candidates = by_article.get(row.article) or []
            match = candidates[0] if len(candidates) == 1 else None
        row.custody_issue_item = match


def _validate_return_quantities(doc):
    """Reject returning more than was issued, per article, across all submitted
    returns for the linked Custody Issue (prevents over-return and duplicate
    full returns)."""
    if not doc.custody_issue or not frappe.db.exists("Custody Issue", doc.custody_issue):
        return
    issue = frappe.get_doc("Custody Issue", doc.custody_issue)
    if issue.docstatus != 1:
        frappe.throw(_("The linked Custody Issue {0} must be submitted before returning.").format(issue.name))

    issued = {}
    for it in issue.items:
        issued[it.article] = issued.get(it.article, 0) + (it.qty or 0)

    prior_returns = frappe.get_all(
        "Custody Return",
        filters={"custody_issue": issue.name, "docstatus": 1, "name": ["!=", doc.name or ""]},
        pluck="name",
    )
    prior = {}
    if prior_returns:
        for r in frappe.get_all(
            "Custody Return Item",
            filters={"parent": ["in", prior_returns]},
            fields=["article", "qty"],
        ):
            prior[r.article] = prior.get(r.article, 0) + (r.qty or 0)

    this_doc = {}
    for row in doc.items:
        this_doc[row.article] = this_doc.get(row.article, 0) + (row.qty or 0)

    for article, qty in this_doc.items():
        issued_qty = issued.get(article, 0)
        if issued_qty == 0:
            frappe.throw(
                _("Article {0} was not issued on Custody Issue {1}, so it cannot be returned.").format(
                    article, issue.name
                )
            )
        already = prior.get(article, 0)
        if already + qty > issued_qty:
            frappe.throw(
                _("Cannot return {0} unit(s) of {1}: {2} were issued and {3} already returned.").format(
                    qty, article, issued_qty, already
                )
            )


def _progress_from(issued, returned):
    """The status a Custody Issue should carry given its per-article issued vs
    returned quantities. 'Returned' ONLY when every issued article is fully
    accounted for — the same per-article model the validator enforces, never a
    cross-article quantity SUM."""
    fully = bool(issued) and all(returned.get(a, 0) >= q for a, q in issued.items())
    any_returned = any(returned.get(a, 0) > 0 for a in issued)
    return "Returned" if fully else "Partially Returned" if any_returned else "Issued"


def _issue_return_progress(issue, exclude=None):
    """Per-article return progress of a Custody Issue across its SUBMITTED returns
    (optionally excluding one return being cancelled). Single source of truth shared
    by on_submit and on_cancel."""
    issued = {}
    for it in issue.items:
        issued[it.article] = issued.get(it.article, 0) + (it.qty or 0)
    submitted = [
        n for n in frappe.get_all(
            "Custody Return",
            filters={"custody_issue": issue.name, "docstatus": 1},
            pluck="name",
        ) if n != exclude
    ]
    returned = {}
    if submitted:
        for r in frappe.get_all(
            "Custody Return Item",
            filters={"parent": ["in", submitted]},
            fields=["article", "qty"],
        ):
            returned[r.article] = returned.get(r.article, 0) + (r.qty or 0)
    return _progress_from(issued, returned)


def on_submit(doc, method=None):
    """Updates the linked Custody Issue's return status and posts the return into the stock ledger."""
    issue = frappe.get_doc("Custody Issue", doc.custody_issue)
    if issue.docstatus == 1:
        try:
            status = _issue_return_progress(issue)
        except Exception:
            frappe.log_error(
                title="Custody Return on_submit: return-progress computation failed",
                message=frappe.get_traceback(),
            )
            status = None
        if status and issue.status != status:
            issue.db_set("status", status)

    _post_return_stock(doc)


def _post_return_stock(doc):
    """Move stock from the holder's custody back into the building store on the
    Accommodation Stock Ledger. ``returned_by_employee`` is the older Employee-only
    field and still wins where set; otherwise the party pair names the holder, which
    is how a Temporary Worker returns what was issued to them."""
    from apex.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import (
        post_stock_entry, has_stock_entries,
    )
    if doc.get("returned_by_employee"):
        party_type, party = "Employee", doc.returned_by_employee
    else:
        party_type, party = doc.get("party_type"), doc.get("party")
    if not party or has_stock_entries("Custody Return", doc.name):
        return
    for row in doc.items:
        post_stock_entry(item_type="Custody Article", item=row.article, qty=-(row.qty or 0),
                         building=doc.building, party_type=party_type, party=party,
                         voucher_type="Custody Return",
                         voucher_no=doc.name, voucher_detail_no=row.name, posting_date=doc.return_date)
        post_stock_entry(item_type="Custody Article", item=row.article, qty=(row.qty or 0),
                         building=doc.building, voucher_type="Custody Return",
                         voucher_no=doc.name, voucher_detail_no=row.name, posting_date=doc.return_date)


def before_cancel(doc, method=None):
    """Every refusal a cancel can raise lives here, before db_update() stamps
    docstatus 2 — so a refused return is left submitted rather than reading as
    cancelled for the rest of the request. Read-only; writes nothing, which is why
    the issue-progress recompute stays in on_cancel below."""
    damage = frappe.get_all(
        "Custody Damage Assessment",
        filters={"custody_return": doc.name, "docstatus": 1},
        limit=1
    )
    if damage:
        frappe.throw(
            _("Cannot cancel Custody Return {0} because it is referenced by active Custody Damage Assessment {1}.").format(
                doc.name, damage[0].name
            )
        )
    from apex.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import (
        assert_reversal_allowed,
    )
    assert_reversal_allowed("Custody Return", doc.name)


def on_cancel(doc, method=None):
    """Recomputes the linked Custody Issue's return status and reverses its stock ledger entries."""
    issue = frappe.get_doc("Custody Issue", doc.custody_issue)
    try:
        status = _issue_return_progress(issue, exclude=doc.name)
        if issue.status != status:
            issue.db_set("status", status)
    except Exception:
        frappe.log_error(
            title="Custody Return on_cancel: return-progress recompute failed",
            message=frappe.get_traceback(),
        )
    from apex.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import (
        reverse_stock_entries,
    )
    reverse_stock_entries("Custody Return", doc.name)


_DAMAGED_CONDITIONS = ("Damaged", "Lost")


@frappe.whitelist()
def make_damage_assessment(source_name, target_doc=None):
    """Open a draft Custody Damage Assessment pre-filled from a submitted return:
    only the Damaged/Lost rows carry over, and the back-link + worker derive so the
    coordinator just fills the per-item damage description and replacement cost."""
    frappe.has_permission("Custody Return", "read", doc=source_name, throw=True)
    from frappe.model.mapper import get_mapped_doc
    from frappe.utils import nowdate

    def set_missing_values(source, target):
        """Stamps the new Custody Damage Assessment's source return link and today's assessment date."""
        target.custody_return = source.name
        target.assessment_date = nowdate()

    return get_mapped_doc(
        "Custody Return",
        source_name,
        {
            "Custody Return": {
                "doctype": "Custody Damage Assessment",
                "field_map": {
                    "party_type": "party_type",
                    "party": "party",
                    "building": "building",
                },
            },
            "Custody Return Item": {
                "doctype": "Custody Damage Item",
                "field_map": {
                    "article": "article",
                    "serial_no": "serial_no",
                    "damage_note": "damage_description",
                },
                "condition": lambda row: row.condition_on_return in _DAMAGED_CONDITIONS,
            },
        },
        target_doc,
        set_missing_values,
    )
