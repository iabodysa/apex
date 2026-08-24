# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt, now_datetime, today

from apex.apex_core.utils.party_link import (
    PARTY_EMPLOYEE,
    PARTY_TEMPORARY_WORKER,
)
from apex.habitat import permissions
from apex.salis.api.driver_portal.images import verified_image_type

@frappe.whitelist()
def get_kiosk_catalog(building: str | None = None) -> dict:
    frappe.has_permission("Custody Article", "read", throw=True)
    articles = frappe.get_list(
        "Custody Article",
        fields=[
            "name as article",
            "article_name",
            "unit_of_measure as uom",
            "image",
            "standard_unit_cost",
        ],
        order_by="article_name asc",
        limit_page_length=0,
    )

    balances: dict[str, float] = {}
    if building:
        frappe.has_permission("Building", "read", doc=building, throw=True)
        Ledger = frappe.qb.DocType("Accommodation Stock Ledger")
        rows = (
            frappe.qb.from_(Ledger)
            .select(Ledger.item, Ledger.signed_qty)
            .where(Ledger.item_type == "Custody Article")
            .where(Ledger.building == building)
            .where(Ledger.is_cancelled == 0)
            .where(Ledger.party.isnull())
            .run(as_dict=True)
        )
        for row in rows:
            balances[row.item] = balances.get(row.item, 0.0) + flt(row.signed_qty)

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

@frappe.whitelist()
def resolve_scan(code: str, party_type: str | None = None, building: str | None = None) -> dict:
    code = (code or "").strip()
    if not code:
        return {"kind": "none"}

    worker = _resolve_worker_scan(code, party_type)
    if worker:
        return worker

    article = _resolve_article_scan(code, building)
    if article:
        return article

    return {"kind": "none"}

def _resolve_worker_scan(code: str, party_type: str | None) -> dict | None:
    party_type = (party_type or "").strip()
    order = [party_type] if party_type in (PARTY_EMPLOYEE, PARTY_TEMPORARY_WORKER) else []
    for pt in (PARTY_EMPLOYEE, PARTY_TEMPORARY_WORKER):
        if pt not in order:
            order.append(pt)

    for pt in order:
        if not frappe.has_permission(pt, "read"):
            continue
        if frappe.db.exists(pt, code):
            title_field = frappe.get_meta(pt).get_title_field()
            party_name = frappe.db.get_value(pt, code, title_field)
            return {
                "kind": "worker",
                "party_type": pt,
                "party": code,
                "party_name": party_name or code,
            }
    return None

def _resolve_article_scan(code: str, building: str | None) -> dict | None:
    if not frappe.has_permission("Custody Article", "read"):
        return None

    fields = [
        "name as article",
        "article_name",
        "unit_of_measure as uom",
        "image",
        "standard_unit_cost",
    ]
    match = None
    if frappe.db.exists("Custody Article", code):
        match = frappe.db.get_value("Custody Article", code, fields, as_dict=True)
    else:
        by_name = frappe.get_all(
            "Custody Article", filters={"article_name": code}, fields=fields, limit=2
        )
        if len(by_name) == 1:
            match = by_name[0]
    if not match:
        return None

    match["store_balance"] = _article_store_balance(match["article"], building)
    return {"kind": "article", "article": match}

def _article_store_balance(article: str, building: str | None) -> float | None:
    if not building:
        return None
    if not frappe.has_permission("Building", "read", doc=building):
        return None
    Ledger = frappe.qb.DocType("Accommodation Stock Ledger")
    rows = (
        frappe.qb.from_(Ledger)
        .select(Ledger.signed_qty)
        .where(Ledger.item_type == "Custody Article")
        .where(Ledger.item == article)
        .where(Ledger.building == building)
        .where(Ledger.is_cancelled == 0)
        .where(Ledger.party.isnull())
        .run(as_dict=True)
    )
    return flt(sum(flt(r.signed_qty) for r in rows))

@frappe.whitelist(methods=["POST"])
def issue_cart(
    building: str,
    items_json: str,
    party_type: str | None = None,
    party: str | None = None,
    employee: str | None = None,
    signature: str | None = None,
    request_token: str | None = None,
) -> dict:
    frappe.has_permission("Custody Issue", "create", throw=True)
    frappe.has_permission("Custody Issue", "submit", throw=True)

    request_token = (request_token or "").strip() or None
    if request_token:
        already = frappe.db.get_value(
            "Custody Issue", {"request_token": request_token}, "name"
        )
        if already:
            return {"custody_issue": already}

    if not party and employee:
        party_type, party = PARTY_EMPLOYEE, employee
    party_type, party = _normalize_party(party_type, party)

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
            "party_type": party_type,
            "party": party,
            "items": rows,
            "request_token": request_token,
        }
    )
    signature = (signature or "").strip()
    if signature:
        verified_image_type(signature)
        doc.signature = signature
        doc.acknowledged_on = now_datetime()
    doc.insert(ignore_permissions=False)
    doc.submit()
    return {"custody_issue": doc.name}

_OPEN_ISSUE_STATUSES = ("Issued", "Partially Returned")

def _return_condition_options() -> list[str]:
    options = frappe.get_meta("Custody Return Item").get_field("condition_on_return").options or ""
    return [o for o in (opt.strip() for opt in options.split("\n")) if o]

def _normalize_party(party_type: str | None, party: str | None) -> tuple[str, str]:
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
    issue_filters = {
        "party_type": party_type,
        "party": party,
        "docstatus": 1,
        "status": ["in", _OPEN_ISSUE_STATUSES],
    }

    restrict, allowed = permissions.report_building_scope(frappe.session.user, doctype="Custody Issue")
    if restrict:
        if not allowed:
            return []
        issue_filters["building"] = ["in", allowed]

    issues = frappe.get_all(
        "Custody Issue",
        filters=issue_filters,
        fields=["name", "building", "issue_date"],
        order_by="issue_date asc, name asc",
    )
    if not issues:
        return []

    issue_names = [i.name for i in issues]
    issue_meta = {i.name: i for i in issues}

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
    frappe.has_permission("Custody Issue", "read", throw=True)
    party_type, party = _normalize_party(party_type, party)
    return {
        "party_type": party_type,
        "party": party,
        "lines": _open_party_custody(party_type, party),
    }

@frappe.whitelist(methods=["POST"])
def return_cart(party_type: str, party: str, items_json: str) -> dict:
    frappe.has_permission("Custody Return", "create", throw=True)
    frappe.has_permission("Custody Return", "submit", throw=True)

    party_type, party = _normalize_party(party_type, party)

    items = frappe.parse_json(items_json) or []
    if not isinstance(items, list) or not items:
        frappe.throw(_("Add at least one item to the cart before returning."))

    conditions = _return_condition_options()
    grouped: dict[str, list[dict]] = {}
    for line in items:
        line = line or {}
        custody_issue = line.get("custody_issue")
        article = line.get("article")
        qty = line.get("qty")
        condition = (line.get("condition_on_return") or "").strip()
        if not custody_issue:
            frappe.throw(_("Each return line must reference a Custody Issue."))
        if not article:
            frappe.throw(_("Each return line must reference an article."))
        if not qty or int(qty) <= 0:
            frappe.throw(_("Each return line must have a quantity greater than zero."))
        if condition and condition not in conditions:
            frappe.throw(_("{0} is not a valid return condition.").format(condition))
        row = {"article": article, "qty": int(qty)}
        if condition:
            row["condition_on_return"] = condition
        grouped.setdefault(custody_issue, []).append(row)

    issue_party = frappe.get_list(
        "Custody Issue",
        filters={"name": ["in", list(grouped.keys())]},
        fields=["name", "party_type", "party", "building", "docstatus"],
        limit_page_length=0,
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
