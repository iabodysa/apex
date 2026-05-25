"""Custody Kiosk — POS-style custody-issue API (v0.9.0).

A thin presentation + orchestration layer over the existing Custody Issue
controller. This module adds NO posting, locking, or ledger logic of its own:

- ``get_kiosk_catalog`` is read-only and built from a BOUNDED set of bulk
  queries (no N+1) — one query over Custody Article and, when a building is
  given, ONE grouped pass over the Accommodation Stock Ledger for store
  balances (never one ``get_store_balance`` per article).
- ``issue_cart`` constructs a Custody Issue and submits it so the existing
  controller runs natively (``validate`` qty gate, ``on_submit`` status flip,
  and ``_post_custody_stock`` which posts to the Accommodation Stock Ledger).
  The kiosk never touches the ledger directly — the no-GL Operational Memo
  boundary is preserved (the ledger is system-written; rows post only through
  the Custody Issue controller).

The ``image`` field on Custody Article is a confirmed v0.9.0 schema add (an
Attach Image). The catalog always selects it and returns it as-is (may be
``None`` → the client renders initials/placeholder).
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt, today


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

    # Optional store balances — ONE grouped pass over the ledger (no N+1).
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
def issue_cart(employee: str, building: str, items_json: str) -> dict:
    """Build and submit ONE Custody Issue from a kiosk cart.

    Builds a full Custody Issue (``issued_to_employee``, ``building``, and one
    Custody Issue Item row per cart line) and ``insert().submit()`` so ALL native
    controller behavior runs: ``validate`` (at least one item, each qty > 0) and
    ``on_submit`` (status -> Issued, then ``_post_custody_stock`` which posts to
    the Accommodation Stock Ledger — building store -1, employee custody +1 per
    line).

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
    doc.insert(ignore_permissions=False)
    doc.submit()
    return {"custody_issue": doc.name}
