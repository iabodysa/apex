# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import base64
import datetime
import io
import re

import frappe
from frappe import _

from apex.apex_core.doctype.masar_worker_token.masar_worker_token import (
    masar_qr_data_uri,
    reshare_worker_link,
)
from apex.apex_core.utils.addresses import get_address_text
from apex.apex_core.utils.party_link import PARTY_EMPLOYEE, PARTY_TEMPORARY_WORKER
from apex.apex_core.utils.portal_identity import (
    WORKER,
    credential_delivery_destination,
)
from apex.habitat import permissions
from apex.habitat.api.front_desk import quick_check_in
from apex.habitat.utils import arrival_slips, occupancy
from apex.habitat.utils.arrival_slips import (
    ARRIVAL_SLIP_TEMPLATE,
    CHECKIN_SLIP_TEMPLATE,
    CUSTODY_HANDOVER_SLIP_TEMPLATE,
)
from apex.habitat.utils.housing_scope import active_building_scope, assert_party_in_scope
from apex.salis.api import messaging_gateway

__all__ = [
    "ARRIVAL_SLIP_TEMPLATE",
    "CHECKIN_SLIP_TEMPLATE",
    "CUSTODY_HANDOVER_SLIP_TEMPLATE",
]

def _expiry_days(expiry_date) -> int | None:
    if not expiry_date:
        return None
    return frappe.utils.date_diff(expiry_date, frappe.utils.today())

@frappe.whitelist()
def get_intake_settings() -> dict:
    if not frappe.has_permission(PARTY_TEMPORARY_WORKER, "create"):
        return {"enable_passport_mrz_ocr": False}
    return {
        "enable_passport_mrz_ocr": bool(
            frappe.db.get_single_value("Habitat Settings", "enable_passport_mrz_ocr")
        )
    }

@frappe.whitelist(methods=["POST"])
def send_masar_link_message(employee, phone=None) -> dict:
    frappe.has_permission("Masar Worker Token", "read", throw=True)
    assert_party_in_scope(PARTY_EMPLOYEE, employee)
    destination = credential_delivery_destination(
        WORKER, employee, requested=phone
    )
    gateway_configured = messaging_gateway.is_configured()
    if not destination:
        return {
            "gateway_configured": gateway_configured,
            "queued": False,
            "reason": "no_phone",
        }
    if not gateway_configured:
        return {
            "gateway_configured": False,
            "queued": False,
            "reason": "not_configured",
        }

    savepoint = "masar_link_delivery"
    frappe.db.savepoint(savepoint)
    try:
        link = reshare_worker_link(employee)
        if not link:
            frappe.throw(
                _("This worker has no active Masar link yet. Create the QR first.")
            )

        result = messaging_gateway.send_masar_link(
            employee, link, phone=destination
        )
        if not result.get("queued"):
            frappe.db.rollback(save_point=savepoint)
            return {"gateway_configured": True, **result}
        frappe.db.release_savepoint(savepoint)
        return {"gateway_configured": True, **result}
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise

def _arrival_identity(party_type, party):
    if party_type == PARTY_EMPLOYEE:
        frappe.has_permission("Employee", "read", throw=True)
        assert_party_in_scope(party_type, party)
        info = frappe.db.get_value("Employee", party, ["employee_name", "image"], as_dict=True) or {}
        if not info:
            frappe.throw(_("Employee {0} does not exist.").format(party))
        return info.get("employee_name"), info.get("image"), None

    if party_type == PARTY_TEMPORARY_WORKER:
        frappe.has_permission("Temporary Worker", "read", throw=True)
        assert_party_in_scope(party_type, party)
        info = frappe.db.get_value(
            "Temporary Worker", party, ["worker_name", "expiry_date"], as_dict=True
        ) or {}
        if not info:
            frappe.throw(_("Temporary Worker {0} does not exist.").format(party))
        return info.get("worker_name"), None, info.get("expiry_date")

    frappe.throw(_("Unknown party type: {0}").format(party_type))

def _custody_balance(party) -> int:
    rows = frappe.get_list(
        "Accommodation Stock Ledger",
        filters={"item_type": "Custody Article", "employee": party, "is_cancelled": 0},
        fields=["signed_qty"],
    )
    return int(sum(int(r.signed_qty or 0) for r in rows))

def _masar_is_enabled(party_type, party) -> bool:
    token = (
        frappe.db.get_value(
            "Masar Worker Token", {"party_type": party_type, "party": party},
            ["token", "enabled"], as_dict=True
        )
        or {}
    )
    return bool(token.get("token")) and bool(token.get("enabled"))

@frappe.whitelist()
def get_arrival_card(party_type=None, party=None, employee=None) -> dict:
    if not party and employee:
        party_type, party = PARTY_EMPLOYEE, employee
    if not (party_type and party):
        frappe.throw(_("party_type and party are required."))

    worker_name, image, tw_expiry = _arrival_identity(party_type, party)

    assignment = (
        frappe.db.get_value(
            "Housing Assignment",
            occupancy.active_assignment_filters(party_type=party_type, party=party),
            ["name", "project", "building", "bed", "check_in_date"],
            as_dict=True,
        )
        or {}
    )
    current_bed = assignment.get("bed")
    current_bed_code = (
        frappe.db.get_value("Bed", current_bed, "bed_code") if current_bed else None
    )

    custody_count = _custody_balance(party) if party_type == PARTY_EMPLOYEE else 0
    masar_enabled = _masar_is_enabled(party_type, party)

    return {
        "party_type": party_type,
        "party": party,
        "employee": party if party_type == PARTY_EMPLOYEE else None,
        "employee_name": worker_name,
        "worker_name": worker_name,
        "image": image,
        "project": assignment.get("project"),
        "current_building": assignment.get("building"),
        "current_bed": current_bed,
        "current_bed_code": current_bed_code,
        "check_in_date": (
            frappe.utils.formatdate(assignment.get("check_in_date")) if assignment.get("check_in_date") else None
        ),
        "has_housing": bool(current_bed),
        "custody_count": custody_count,
        "has_custody": bool(custody_count),
        "masar_enabled": masar_enabled,
        "masar_status": "issued" if masar_enabled else "pending",
        "expiry_date": frappe.utils.formatdate(tw_expiry) if tw_expiry else None,
        "expiry_days": _expiry_days(tw_expiry),
    }

def _housed_employees() -> set:
    housed = frappe.get_all(
        "Housing Assignment",
        filters=occupancy.active_assignment_filters(),
        fields=["employee"],
    )
    return {h.employee for h in housed if h.employee}

def _housed_temporary_workers(restrict, allowed) -> set:
    filters = occupancy.active_assignment_filters(party_type="Temporary Worker")
    if restrict:
        filters["building"] = ["in", allowed]
    housed = frappe.get_all("Housing Assignment", filters=filters, fields=["party"])
    return {h.party for h in housed if h.party}

def _employee_matches(txt, excluded) -> list:
    filters = {"status": "Active"}
    if excluded:
        filters["name"] = ["not in", sorted(excluded)]
    emps = frappe.get_all(
        "Employee",
        filters=filters,
        or_filters=(
            [["employee_name", "like", f"%{txt}%"], ["name", "like", f"%{txt}%"]] if txt else None
        ),
        fields=["name", "employee_name", "designation"],
        order_by="employee_name asc",
        limit_page_length=15,
    )
    return [
        {
            "party_type": PARTY_EMPLOYEE,
            "party": e.name,
            "label": e.employee_name or e.name,
            "sub": e.designation or e.name,
        }
        for e in emps
    ]

def _temporary_worker_matches(txt, restrict, allowed, housed_tw) -> list:
    tw_filters = {"status": "Active"}
    if restrict:
        tw_filters["building"] = ["in", allowed]
    if housed_tw:
        tw_filters["name"] = ["not in", sorted(housed_tw)]
    tws = frappe.get_all(
        "Temporary Worker",
        filters=tw_filters,
        or_filters=(
            [
                ["worker_name", "like", f"%{txt}%"],
                ["passport_number", "like", f"%{txt}%"],
                ["name", "like", f"%{txt}%"],
            ]
            if txt
            else None
        ),
        fields=["name", "worker_name", "passport_number", "expiry_date"],
        order_by="modified desc",
        limit_page_length=15,
    )
    return [
        {
            "party_type": PARTY_TEMPORARY_WORKER,
            "party": t.name,
            "label": t.worker_name or t.name,
            "sub": _("Passport {0}").format(t.passport_number or "—"),
            "expiry_date": frappe.utils.formatdate(t.expiry_date) if t.expiry_date else None,
            "expiry_days": _expiry_days(t.expiry_date),
        }
        for t in tws
    ]

@frappe.whitelist()
def search_arrivals_workers(building=None, txt=None) -> list:
    txt = (txt or "").strip()
    results = []

    restrict, allowed = permissions.report_building_scope(frappe.session.user)
    if restrict and not allowed:
        return []

    if frappe.has_permission("Employee", "read"):
        results += _employee_matches(txt, _housed_employees())

    if frappe.has_permission("Temporary Worker", "read"):
        results += _temporary_worker_matches(
            txt, restrict, allowed, _housed_temporary_workers(restrict, allowed)
        )

    return results

@frappe.whitelist(methods=["POST"])
def register_temporary_worker(
    worker_name,
    passport_number,
    nationality=None,
    labour_supplier=None,
    building=None,
    project=None,
    cell_number=None,
    iqama_number=None,
    batch_row=None,
) -> dict:
    frappe.has_permission("Temporary Worker", "create", throw=True)
    doc = frappe.get_doc(
        {
            "doctype": "Temporary Worker",
            "worker_name": worker_name,
            "passport_number": passport_number,
            "nationality": nationality,
            "labour_supplier": labour_supplier,
            "building": building,
            "project": project,
            "cell_number": cell_number,
            "iqama_number": iqama_number,
        }
    )
    doc.insert()
    _link_manifest_row(batch_row, doc.name)
    return {
        "party_type": PARTY_TEMPORARY_WORKER,
        "party": doc.name,
        "label": doc.worker_name,
        "expiry_date": frappe.utils.formatdate(doc.expiry_date) if doc.expiry_date else None,
    }

def _link_manifest_row(batch_row, temporary_worker) -> None:
    if not (batch_row and temporary_worker):
        return
    parent = frappe.db.get_value("Arrival Batch Worker", batch_row, "parent")
    if not parent:
        return
    if not frappe.has_permission("Arrival Batch", "write", doc=parent):
        return
    frappe.db.set_value("Arrival Batch Worker", batch_row, "temporary_worker", temporary_worker)

_MRZ_NATIONALITY = {
    "IND": "Indian",
    "PAK": "Pakistani",
    "BGD": "Bangladeshi",
    "NPL": "Nepali",
    "LKA": "Sri Lankan",
    "PHL": "Filipino",
    "EGY": "Egyptian",
    "SDN": "Sudanese",
    "YEM": "Yemeni",
    "IDN": "Indonesian",
    "ETH": "Ethiopian",
    "KEN": "Kenyan",
    "UGA": "Ugandan",
    "SAU": "Saudi",
}

def _mrz_yymmdd_to_date(value: str, is_expiry: bool) -> str | None:
    value = (value or "").strip()
    if len(value) != 6 or not value.isdigit():
        return None
    yy, mm, dd = int(value[:2]), int(value[2:4]), int(value[4:6])
    if not (1 <= mm <= 12 and 1 <= dd <= 31):
        return None
    current_yy = frappe.utils.now_datetime().year % 100
    if is_expiry:
        century = 2000
    else:
        century = 2000 if yy <= current_yy else 1900
    try:
        return datetime.date(century + yy, mm, dd).isoformat()
    except ValueError:
        return None

def parse_mrz_text(text: str) -> dict:
    lines = [
        re.sub(r"[^A-Z0-9<]", "", ln.strip().upper())
        for ln in (text or "").splitlines()
        if ln.strip()
    ]
    mrz_lines = [ln for ln in lines if len(ln) >= 30 and "<" in ln]
    out: dict = {"raw_lines": mrz_lines}
    if len(mrz_lines) < 2:
        return out

    line1, line2 = mrz_lines[0], mrz_lines[1]

    name_part = line1
    m = re.match(r"^P[A-Z<]([A-Z]{3})(.*)$", line1)
    if m:
        out["nationality"] = _MRZ_NATIONALITY.get(m.group(1), m.group(1))
        name_part = m.group(2)
    if "<<" in name_part:
        surname, _, given = name_part.partition("<<")
        surname = surname.replace("<", " ").strip()
        given = given.replace("<", " ").strip()
        full = " ".join(p for p in (given, surname) if p)
        if full:
            out["worker_name"] = full

    passport_no = line2[:9].replace("<", "").strip()
    if passport_no:
        out["passport_number"] = passport_no
    if len(line2) >= 13 and "nationality" not in out:
        nat = line2[10:13].replace("<", "").strip()
        if nat:
            out["nationality"] = _MRZ_NATIONALITY.get(nat, nat)
    if len(line2) >= 27:
        expiry = _mrz_yymmdd_to_date(line2[21:27], is_expiry=True)
        if expiry:
            out["expiry_date"] = expiry
    return out

def _ocr_image_to_text(image: str) -> str | None:
    payload = image.split(",", 1)[1] if image.startswith("data:") and "," in image else image
    try:
        raw = base64.b64decode(payload)
    except Exception:
        return None

    try:
        import pytesseract
        from PIL import Image

        img = Image.open(io.BytesIO(raw))
        return pytesseract.image_to_string(img)
    except Exception:
        return None

@frappe.whitelist(methods=["POST"])
def parse_passport(image) -> dict:
    frappe.has_permission("Temporary Worker", "create", throw=True)
    if not frappe.db.get_single_value("Habitat Settings", "enable_passport_mrz_ocr"):
        return {"ok": False, "reason": "disabled"}

    image = (image or "").strip()
    if not image:
        frappe.throw(_("No image was captured."))

    text = _ocr_image_to_text(image)
    if text is None:
        return {"ok": False, "reason": "ocr_unavailable"}

    fields = parse_mrz_text(text)
    parsed = {
        k: fields.get(k)
        for k in ("worker_name", "passport_number", "nationality", "expiry_date")
        if fields.get(k)
    }
    return {"ok": bool(parsed), "fields": parsed}

@frappe.whitelist(methods=["POST"])
def house_over_capacity(room, party_type, party, project, check_in_date=None) -> dict:

    frappe.has_permission("Bed", "create", throw=True)
    if not frappe.db.exists("Room", room):
        frappe.throw(_("Room {0} does not exist.").format(room))

    n = frappe.db.count("Bed", {"room": room, "is_temporary": 1}) + 1
    bed = frappe.get_doc(
        {
            "doctype": "Bed",
            "room": room,
            "bed_code": f"{room}-OC{n}",
            "status": "Available",
            "is_temporary": 1,
        }
    )
    bed.insert()

    result = quick_check_in(
        bed=bed.name,
        party_type=party_type,
        party=party,
        project=project,
        check_in_date=check_in_date,
    )
    return {**result, "is_temporary": True, "bed_code": bed.bed_code}

def _arrival_supplier(arrival, tw_supplier):
    if arrival.party_type == PARTY_TEMPORARY_WORKER:
        return tw_supplier.get(arrival.party)
    if arrival.is_external_supplier:
        return arrival.billed_to_supplier
    return None

def _supplier_breakdown(arrivals) -> list:
    tw_parties = [a.party for a in arrivals if a.party_type == PARTY_TEMPORARY_WORKER and a.party]
    tw_supplier = {}
    if tw_parties:
        for row in frappe.get_list(
            "Temporary Worker",
            filters={"name": ["in", list(set(tw_parties))]},
            fields=["name", "labour_supplier"],
        ):
            tw_supplier[row.name] = row.labour_supplier

    counts: dict[str | None, int] = {}
    for a in arrivals:
        sup = _arrival_supplier(a, tw_supplier)
        counts[sup] = counts.get(sup, 0) + 1

    sup_ids = [s for s in counts if s]
    sup_names = {}
    if sup_ids:
        for row in frappe.get_all(
            "Supplier", filters={"name": ["in", sup_ids]}, fields=["name", "supplier_name"]
        ):
            sup_names[row.name] = row.supplier_name

    return sorted(
        (
            {
                "supplier": s,
                "supplier_name": sup_names.get(s) if s else _("Direct / Company"),
                "count": c,
            }
            for s, c in counts.items()
        ),
        key=lambda r: r["count"],
        reverse=True,
    )

def _over_capacity_count(bed_ids) -> int:
    if not bed_ids:
        return 0
    return frappe.db.count("Bed", {"name": ["in", list(set(bed_ids))], "is_temporary": 1})

def _empty_arrival_summary(date, building):
    return {
        "date": date,
        "building": building,
        "housed_count": 0,
        "by_supplier": [],
        "over_capacity_count": 0,
        "manifest_expected": None,
        "manifest_completion_pct": None,
    }

def _manifest_progress(date, building_filter, housed_count):
    if not frappe.db.exists("DocType", "Arrival Batch"):
        return None, None
    batch_filters = {"expected_date": date}
    if building_filter:
        batch_filters["building"] = building_filter
    expected = 0
    for b in frappe.get_all("Arrival Batch", filters=batch_filters, fields=["expected_count"]):
        expected += int(b.get("expected_count") or 0)
    if not expected:
        return expected, None
    return expected, round(min(housed_count, expected) / expected * 100, 1)

@frappe.whitelist()
def get_arrival_summary(date=None, building=None) -> dict:
    frappe.has_permission("Housing Assignment", "read", throw=True)
    if building:
        frappe.has_permission("Building", "read", doc=building, throw=True)
    date = date or frappe.utils.today()

    restrict, allowed = permissions.report_building_scope(
        frappe.session.user, doctype="Housing Assignment"
    )
    if building:
        building_filter = building
    elif restrict:
        if not allowed:
            return _empty_arrival_summary(date, building)
        building_filter = ["in", allowed]
    else:
        building_filter = None

    filters = {"check_in_date": date, "docstatus": 1}
    if building_filter:
        filters["building"] = building_filter
    arrivals = frappe.get_all(
        "Housing Assignment",
        filters=filters,
        fields=["name", "bed", "party_type", "party", "is_external_supplier", "billed_to_supplier"],
    )
    housed_count = len(arrivals)

    by_supplier = _supplier_breakdown(arrivals)
    over_capacity_count = _over_capacity_count([a.bed for a in arrivals if a.bed])
    manifest_expected, manifest_completion_pct = _manifest_progress(
        date, building_filter, housed_count
    )

    return {
        "date": date,
        "building": building,
        "housed_count": housed_count,
        "by_supplier": by_supplier,
        "over_capacity_count": over_capacity_count,
        "manifest_expected": manifest_expected,
        "manifest_completion_pct": manifest_completion_pct,
    }

def _empty_manifest(date, building=None):
    return {
        "date": date,
        "building": building,
        "workers": [],
        "total": 0,
        "arrived": 0,
        "housed": 0,
        "pending": 0,
    }

@frappe.whitelist()
def get_expected_arrivals(date=None, building=None) -> dict:
    date = date or frappe.utils.today()
    if not frappe.db.exists("DocType", "Arrival Batch"):
        return _empty_manifest(date, building)
    frappe.has_permission("Arrival Batch", "read", throw=True)
    if building:
        frappe.has_permission("Building", "read", doc=building, throw=True)

    restrict, allowed = permissions.report_building_scope(
        frappe.session.user, doctype="Arrival Batch"
    )
    filters = {"expected_date": date}
    if building:
        filters["building"] = building
    elif restrict:
        if not allowed:
            return _empty_manifest(date, building)
        filters["building"] = ["in", allowed]
    batches = frappe.get_all(
        "Arrival Batch", filters=filters, fields=["name", "building", "labour_supplier", "project"]
    )
    workers: list[dict] = []
    if batches:
        batch_meta = {b.name: b for b in batches}
        rows = frappe.get_all(
            "Arrival Batch Worker",
            filters={"parent": ["in", [b.name for b in batches]], "parenttype": "Arrival Batch"},
            fields=["name", "parent", "worker_name", "passport_number", "nationality", "temporary_worker"],
            order_by="idx asc",
        )
        registered_parties = [r.temporary_worker for r in rows if r.temporary_worker]
        housed_parties = set()
        if registered_parties:
            housed_parties = set(
                frappe.get_list(
                    "Housing Assignment",
                    filters=occupancy.active_assignment_filters(
                        party_type=PARTY_TEMPORARY_WORKER,
                        party=["in", registered_parties],
                    ),
                    pluck="party",
                    limit_page_length=0,
                )
            )
        for r in rows:
            b = batch_meta.get(r.parent)
            workers.append(
                {
                    "batch": r.parent,
                    "row": r.name,
                    "worker_name": r.worker_name,
                    "passport_number": r.passport_number,
                    "nationality": r.nationality,
                    "building": b.building if b else None,
                    "labour_supplier": b.labour_supplier if b else None,
                    "project": b.project if b else None,
                    "arrived": bool(r.temporary_worker),
                    "housed": r.temporary_worker in housed_parties,
                    "temporary_worker": r.temporary_worker,
                }
            )
    arrived = sum(1 for w in workers if w["arrived"])
    housed = sum(1 for w in workers if w.get("housed"))
    total = len(workers)
    return {
        "date": date,
        "building": building,
        "workers": workers,
        "total": total,
        "arrived": arrived,
        "housed": housed,
        "pending": total - arrived,
    }

@frappe.whitelist(methods=["POST"])
def get_arrival_slip(party_type, party) -> dict:
    card = get_arrival_card(party_type=party_type, party=party)
    ctx = arrival_slips.slip_context(
        card.get("worker_name") or card.get("party"), party_type
    )
    ctx.update({
        "building": card.get("current_building") or "",
        "bed": card.get("current_bed_code") or card.get("current_bed") or "",
        "project": card.get("project") or "",
        "check_in_date": card.get("check_in_date") or "",
        "designation": None,
        "passport_number": None,
        "iqama_number": None,
        "nationality": None,
        "qr": None,
    })

    if party_type == PARTY_EMPLOYEE:
        ctx["designation"] = frappe.db.get_value("Employee", party, "designation")
        frappe.has_permission("Masar Worker Token", "read", throw=True)
        link = reshare_worker_link(party)
        if link:
            ctx["qr"] = masar_qr_data_uri(link)
    elif party_type == PARTY_TEMPORARY_WORKER:
        frappe.has_permission("Temporary Worker", "read", throw=True)
        assert_party_in_scope(party_type, party)
        tw = (
            frappe.db.get_value(
                "Temporary Worker", party, ["passport_number", "iqama_number", "nationality"], as_dict=True
            )
            or {}
        )
        ctx["passport_number"] = tw.get("passport_number")
        ctx["iqama_number"] = tw.get("iqama_number")
        ctx["nationality"] = tw.get("nationality")

    return {
        "html": frappe.render_template(arrival_slips.ARRIVAL_SLIP_TEMPLATE, ctx),
        "title": ctx["worker_name"],
        "card": ctx,
    }

@frappe.whitelist()
def get_checkin_slip(party_type, party) -> dict:
    card = get_arrival_card(party_type=party_type, party=party)
    building = card.get("current_building")
    if building:
        frappe.has_permission("Building", "read", doc=building, throw=True)
    bldg = (
        frappe.db.get_value("Building", building, ["city"], as_dict=True)
        if building
        else None
    ) or {}
    address = get_address_text("Building", building)

    ctx = arrival_slips.slip_context(
        card.get("worker_name") or card.get("party"), party_type
    )
    ctx.update({
        "building": building or "",
        "address": address,
        "city": bldg.get("city") or "",
        "bed": card.get("current_bed_code") or card.get("current_bed") or "",
        "project": card.get("project") or "",
        "check_in_date": card.get("check_in_date") or "",
        "terms": arrival_slips.HOUSING_TERMS,
    })
    return {
        "html": frappe.render_template(arrival_slips.CHECKIN_SLIP_TEMPLATE, ctx),
        "title": ctx["worker_name"],
    }

def _custody_slip_items(doc):
    article_ids = list({row.article for row in doc.items if row.article})
    masters = {}
    if article_ids:
        for a in frappe.get_all(
            "Custody Article",
            filters={"name": ["in", article_ids]},
            fields=["name", "article_name", "unit_of_measure"],
        ):
            masters[a.name] = a

    items = []
    for row in doc.items:
        m = masters.get(row.article, {})
        items.append(
            {
                "article_name": row.article_name or m.get("article_name") or row.article,
                "qty": row.qty,
                "uom": m.get("unit_of_measure") or "",
            }
        )
    return items, any(it["uom"] for it in items)

@frappe.whitelist()
def get_custody_handover_slip(custody_issue) -> dict:
    frappe.has_permission("Custody Issue", "read", doc=custody_issue, throw=True)
    doc = frappe.get_doc("Custody Issue", custody_issue)
    if not doc.issued_to_employee:
        frappe.throw(_("This Custody Issue has no issued-to Employee; nothing to hand over."))

    worker_name = (
        frappe.db.get_value("Employee", doc.issued_to_employee, "employee_name")
        or doc.issued_to_name
        or doc.issued_to_employee
    )

    items, show_uom = _custody_slip_items(doc)

    ctx = arrival_slips.slip_context(worker_name)
    ctx.update({
        "custody_issue": doc.name,
        "building": doc.building or "",
        "issue_date": frappe.utils.formatdate(doc.issue_date) if doc.issue_date else "",
        "items": items,
        "show_uom": show_uom,
    })
    return {
        "html": frappe.render_template(arrival_slips.CUSTODY_HANDOVER_SLIP_TEMPLATE, ctx),
        "title": worker_name,
    }

@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def buildings_with_capacity(doctype, txt, searchfield, start, page_len, filters):
    scope = active_building_scope(frappe.session.user)
    if scope.filters is None:
        return []

    f = dict(scope.filters)
    if txt:
        f["building_name"] = ["like", f"%{txt}%"]

    buildings = frappe.get_list(
        "Building", filters=f, fields=["name", "building_name"], limit_page_length=0
    )
    if not buildings:
        return []
    building_names = [b.name for b in buildings]

    mix = occupancy.bed_mix(occupancy.bed_mix_rows(building_names), building_names)

    rows = [
        (b.name, b.building_name or b.name)
        for b in buildings
        if mix[b.name]["available"] > 0
    ]
    rows.sort(key=lambda r: str(r[1]))
    return rows[start : start + page_len] if page_len else rows
