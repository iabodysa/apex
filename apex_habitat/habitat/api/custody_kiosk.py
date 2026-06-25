"""Custody Kiosk — POS-style custody issue + return API (v0.9.0).

A thin presentation + orchestration layer over the existing Custody Issue and
Custody Return controllers. This module adds NO posting, locking, or ledger
logic of its own:

- ``get_kiosk_catalog`` is read-only and built from a BOUNDED set of bulk
  queries (no N+1) — one query over Custody Article and, when a building is
  given, ONE grouped pass over the Accommodation Stock Ledger for store
  balances (never one ``get_store_balance`` per article).
- ``issue_cart`` constructs a Custody Issue and submits it so the existing
  controller runs natively (``validate`` qty gate, ``on_submit`` status flip,
  and ``_post_custody_stock`` which posts to the Accommodation Stock Ledger).
- ``get_party_custody`` is read-only: for one party it reports what is still
  held, per source Custody Issue, as issued-minus-already-returned per article
  (the same per-article model the Custody Return over-return guard enforces).
- ``return_cart`` groups the returned lines by their source Custody Issue and
  constructs + submits ONE Custody Return per issue, so the existing controller
  runs natively (``validate`` over-return guard, ``on_submit`` status roll-up,
  and ``_post_return_stock`` which reverses the Accommodation Stock Ledger).

The kiosk never touches the ledger directly — the no-GL Operational Memo
boundary is preserved (the ledger is system-written; rows post only through the
Custody Issue / Custody Return controllers).

The ``image`` field on Custody Article is a confirmed v0.9.0 schema add (an
Attach Image). The catalog always selects it and returns it as-is (may be
``None`` → the client renders initials/placeholder).
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt, now_datetime, today

from apex_habitat.apex_core.utils.party_link import (
    PARTY_EMPLOYEE,
    PARTY_TEMPORARY_WORKER,
)


@frappe.whitelist()
def get_kiosk_catalog(building: str | None = None) -> dict:
    """Return the Custody Article catalog for the kiosk tile grid.

    Reads only. Built from a BOUNDED set of bulk queries (no per-article round
    trips). One bulk query over Custody Article; if ``building`` is given, ONE
    grouped pass over the Accommodation Stock Ledger attaches the live store
    balance per article (employee unset) — never ``get_store_balance`` per tile.

    Args:
        building: optional Accommodation Building docname. When set, each
            article carries the live store balance for that building.

    Returns:
        dict shaped as ``{has_images, building, articles}`` where each article is
        ``{article, article_name, uom, image, store_balance}``. ``image`` may be
        ``None`` (the client falls back to initials/placeholder).
    """
    frappe.has_permission("Custody Article", "read", throw=True)
    articles = frappe.get_all(
        "Custody Article",
        fields=[
            "name as article",
            "article_name",
            "unit_of_measure as uom",
            "image",
        ],
        order_by="article_name asc",
    )

    # [#q1odkg]
    balances: dict[str, float] = {}
    if building:
        frappe.has_permission("Accommodation Building", "read", doc=building, throw=True)
        Ledger = frappe.qb.DocType("Accommodation Stock Ledger")
        rows = (
            frappe.qb.from_(Ledger)
            .select(Ledger.item, Ledger.qty)
            .where(Ledger.item_type == "Custody Article")
            .where(Ledger.building == building)
            .where(Ledger.is_cancelled == 0)
            .where(Ledger.employee.isnull())
            .run(as_dict=True)
        )
        for row in rows:
            balances[row.item] = balances.get(row.item, 0.0) + flt(row.qty)

    has_images = False
    for art in articles:
        if art.get("image"):
            has_images = True
        art["store_balance"] = flt(balances.get(art["article"])) if building else None

    return {
        "has_images": has_images,
        "building": building,
        "articles": articles,
    }


@frappe.whitelist(methods=["POST"])
def issue_cart(
    employee: str, building: str, items_json: str, signature: str | None = None
) -> dict:
    """Build and submit ONE Custody Issue from a kiosk cart.

    Builds a full Custody Issue (``issued_to_employee``, ``building``, and one
    Custody Issue Item row per cart line) and ``insert().submit()`` so ALL native
    controller behavior runs: ``validate`` (at least one item, each qty > 0) and
    ``on_submit`` (status -> Issued, then ``_post_custody_stock`` which posts to
    the Accommodation Stock Ledger — building store -1, employee custody +1 per
    line).

    When the kiosk captures the recipient's signature at handover, the data-URL is
    stored on the issue and ``acknowledged_on`` is stamped — in-person proof of
    handover at issue time (distinct from the later Custody Acknowledgment record
    the holder can file from the Web Form).

    This method adds NO posting, locking, or ledger logic of its own. It never
    writes a Stock Ledger row directly; the read-only ledger engine is reached
    only through the Custody Issue controller (no-GL Operational Memo boundary
    preserved).

    Permission: caller must have ``create`` AND ``submit`` on Custody Issue
    (checked explicitly below; defense in depth on top of the role grant).

    Args:
        employee: Employee docname (the responsible party).
        building: Accommodation Building docname (the source store).
        items_json: JSON string of ``[{"article": <name>, "qty": <int>}]``.
        signature: optional signature data-URL captured at the kiosk.

    Returns:
        dict: ``{"custody_issue": <docname>}``.
    """
    frappe.has_permission("Custody Issue", "create", throw=True)
    frappe.has_permission("Custody Issue", "submit", throw=True)

    items = frappe.parse_json(items_json) or []
    if not isinstance(items, list) or not items:
        frappe.throw(_("Add at least one item to the cart before issuing."))

    rows = []
    for line in items:
        article = (line or {}).get("article")
        qty = (line or {}).get("qty")
        if not article:
            frappe.throw(_("Each cart line must reference an article."))
        if not qty or int(qty) <= 0:
            frappe.throw(_("Each cart line must have a quantity greater than zero."))
        rows.append({"article": article, "qty": int(qty)})

    doc = frappe.get_doc(
        {
            "doctype": "Custody Issue",
            "issue_date": today(),
            "building": building,
            "issued_to_employee": employee,
            "items": rows,
        }
    )
    signature = (signature or "").strip()
    if signature:
        doc.signature = signature
        doc.acknowledged_on = now_datetime()
    doc.insert(ignore_permissions=False)
    doc.submit()
    return {"custody_issue": doc.name}


# [#rtcz4r]
_OPEN_ISSUE_STATUSES = ("Issued", "Partially Returned")


def _normalize_party(party_type: str | None, party: str | None) -> tuple[str, str]:
    """Validate the (party_type, party) pair and return it normalized.

    ``party_type`` must be one of the native options (Employee | Temporary
    Worker); ``party`` must be a non-empty docname. Read-only — does not touch
    the ledger.
    """
    party_type = (party_type or "").strip()
    party = (party or "").strip()
    if party_type not in (PARTY_EMPLOYEE, PARTY_TEMPORARY_WORKER):
        frappe.throw(_("Select a valid worker type (Employee or Temporary Worker)."))
    if not party:
        frappe.throw(_("Select a worker before continuing."))
    if not frappe.db.exists(party_type, party):
        frappe.throw(_("{0} {1} does not exist.").format(_(party_type), party))
    return party_type, party


def _open_party_custody(party_type: str, party: str) -> list[dict]:
    """Compute what one party still holds, per source Custody Issue.

    For every SUBMITTED Custody Issue of this party that is not fully returned,
    the remaining held quantity of each article is ``issued − already returned``
    (summed over that issue's SUBMITTED Custody Returns). This mirrors the exact
    per-article model the Custody Return controller's over-return guard enforces,
    so every line returned here is genuinely returnable — and each line carries
    the ``custody_issue`` + ``building`` the return must be booked against.

    Bounded query plan (no N+1): one pass over open Custody Issues for the party,
    one bulk pass over their issue items, one bulk pass over their submitted
    returns, one bulk pass over those returns' items. Returns a flat list of
    ``{custody_issue, building, issue_date, article, article_name, uom, qty}``
    with ``qty`` (remaining) > 0 only.
    """
    issues = frappe.get_all(
        "Custody Issue",
        filters={
            "party_type": party_type,
            "party": party,
            "docstatus": 1,
            "status": ["in", _OPEN_ISSUE_STATUSES],
        },
        fields=["name", "building", "issue_date"],
        order_by="issue_date asc, name asc",
    )
    if not issues:
        return []

    issue_names = [i.name for i in issues]
    issue_meta = {i.name: i for i in issues}

    # [#5aq8wd]
    issued: dict[str, dict[str, float]] = {}
    issue_item_rows = frappe.get_all(
        "Custody Issue Item",
        filters={"parent": ["in", issue_names]},
        fields=["parent", "article", "qty"],
    )
    for row in issue_item_rows:
        issued.setdefault(row.parent, {})
        issued[row.parent][row.article] = (
            issued[row.parent].get(row.article, 0.0) + flt(row.qty)
        )

    # [#qb3m1n]
    returned: dict[str, dict[str, float]] = {}
    submitted_returns = frappe.get_all(
        "Custody Return",
        filters={"custody_issue": ["in", issue_names], "docstatus": 1},
        fields=["name", "custody_issue"],
    )
    if submitted_returns:
        return_to_issue = {r.name: r.custody_issue for r in submitted_returns}
        return_item_rows = frappe.get_all(
            "Custody Return Item",
            filters={"parent": ["in", list(return_to_issue.keys())]},
            fields=["parent", "article", "qty"],
        )
        for row in return_item_rows:
            issue_name = return_to_issue[row.parent]
            returned.setdefault(issue_name, {})
            returned[issue_name][row.article] = (
                returned[issue_name].get(row.article, 0.0) + flt(row.qty)
            )

    # [#7uv0lc]
    article_names = {a for per in issued.values() for a in per}
    name_map: dict[str, dict] = {}
    if article_names:
        for art in frappe.get_all(
            "Custody Article",
            filters={"name": ["in", list(article_names)]},
            fields=["name", "article_name", "unit_of_measure as uom"],
        ):
            name_map[art.name] = art

    lines: list[dict] = []
    for issue_name in issue_names:
        per_issued = issued.get(issue_name, {})
        per_returned = returned.get(issue_name, {})
        meta = issue_meta[issue_name]
        for article, qty in per_issued.items():
            remaining = flt(qty) - flt(per_returned.get(article, 0.0))
            if remaining <= 0:
                continue
            art_meta = name_map.get(article, {})
            lines.append(
                {
                    "custody_issue": issue_name,
                    "building": meta.building,
                    "issue_date": meta.issue_date,
                    "article": article,
                    "article_name": art_meta.get("article_name") or article,
                    "uom": art_meta.get("uom"),
                    "qty": remaining,
                }
            )
    return lines


@frappe.whitelist()
def get_party_custody(party_type: str, party: str) -> dict:
    """Return the articles a party currently holds, as returnable kiosk lines.

    Read-only. For the given (``party_type``, ``party``) pair, lists each still
    held article line — ``issued − already returned`` per article, per source
    Custody Issue — so Return mode can show exactly what is returnable and how
    much. Each line names the ``custody_issue`` and ``building`` the return is
    booked against (``return_cart`` groups by ``custody_issue``).

    Permission: caller must have ``read`` on Custody Issue.

    Args:
        party_type: ``Employee`` or ``Temporary Worker``.
        party: the party docname (an Employee or Temporary Worker name).

    Returns:
        dict shaped as ``{party_type, party, lines}`` where each line is
        ``{custody_issue, building, issue_date, article, article_name, uom,
        qty}`` with ``qty`` (remaining held) > 0.
    """
    frappe.has_permission("Custody Issue", "read", throw=True)
    party_type, party = _normalize_party(party_type, party)
    return {
        "party_type": party_type,
        "party": party,
        "lines": _open_party_custody(party_type, party),
    }


@frappe.whitelist(methods=["POST"])
def return_cart(party_type: str, party: str, items_json: str) -> dict:
    """Build and submit Custody Returns from a kiosk return cart.

    Each requested line names the source ``custody_issue`` it is being returned
    against (as surfaced by :func:`get_party_custody`). Lines are grouped by
    ``custody_issue`` and ONE Custody Return is constructed + submitted per issue,
    so ALL native controller behaviour runs per return: ``validate`` (the
    per-article over-return guard) and ``on_submit`` (rolls the linked Custody
    Issue status to Partially Returned / Returned, then ``_post_return_stock``
    which reverses the Accommodation Stock Ledger — employee custody −qty,
    building store +qty per line).

    This method adds NO posting, locking, or ledger logic of its own. It never
    writes a Stock Ledger row directly; the read-only ledger engine is reached
    only through the Custody Return controller (no-GL Operational Memo boundary
    preserved). If any Custody Return fails to validate/submit (e.g. over-return),
    the whole call rolls back — no partial returns are left submitted.

    Permission: caller must have ``create`` AND ``submit`` on Custody Return
    (checked explicitly below; defense in depth on top of the role grant).

    Args:
        party_type: ``Employee`` or ``Temporary Worker`` (the returning party).
        party: the party docname.
        items_json: JSON string of
            ``[{"custody_issue": <name>, "article": <name>, "qty": <int>}]``.

    Returns:
        dict: ``{"custody_returns": [<docname>, ...]}`` — one per source issue.
    """
    frappe.has_permission("Custody Return", "create", throw=True)
    frappe.has_permission("Custody Return", "submit", throw=True)

    party_type, party = _normalize_party(party_type, party)

    items = frappe.parse_json(items_json) or []
    if not isinstance(items, list) or not items:
        frappe.throw(_("Add at least one item to the cart before returning."))

    # [#m9c2pk]
    grouped: dict[str, list[dict]] = {}
    for line in items:
        line = line or {}
        custody_issue = line.get("custody_issue")
        article = line.get("article")
        qty = line.get("qty")
        if not custody_issue:
            frappe.throw(_("Each return line must reference a Custody Issue."))
        if not article:
            frappe.throw(_("Each return line must reference an article."))
        if not qty or int(qty) <= 0:
            frappe.throw(_("Each return line must have a quantity greater than zero."))
        grouped.setdefault(custody_issue, []).append(
            {"article": article, "qty": int(qty)}
        )

    # [#k4r0tn]
    issue_party = frappe.get_all(
        "Custody Issue",
        filters={"name": ["in", list(grouped.keys())]},
        fields=["name", "party_type", "party", "building", "docstatus"],
    )
    issue_map = {i.name: i for i in issue_party}
    for custody_issue in grouped:
        info = issue_map.get(custody_issue)
        if not info or info.docstatus != 1:
            frappe.throw(
                _("Custody Issue {0} was not found or is not submitted.").format(custody_issue)
            )
        if info.party_type != party_type or info.party != party:
            frappe.throw(
                _("Custody Issue {0} is not held by the selected worker.").format(custody_issue)
            )

    created: list[str] = []
    for custody_issue, rows in grouped.items():
        info = issue_map[custody_issue]
        doc = frappe.get_doc(
            {
                "doctype": "Custody Return",
                "return_date": today(),
                "custody_issue": custody_issue,
                "building": info.building,
                "party_type": party_type,
                "party": party,
                "items": rows,
            }
        )
        doc.insert(ignore_permissions=False)
        doc.submit()
        created.append(doc.name)

    return {"custody_returns": created}
