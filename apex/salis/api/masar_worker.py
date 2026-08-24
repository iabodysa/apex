# Copyright (c) 2026, afmcoltd

import os

import frappe
from frappe import _
from frappe.utils import flt
from frappe.utils.file_manager import save_file

from apex.apex_core.utils.portal_identity import (
    WORKER,
    TOKEN_COOKIES,
    presented_token,
    resolve_portal_subject,
)
from apex.salis.api.masar_routes import _worker_today_dispatch_trip
from apex.salis.utils import days_until as _days_until

MASAR_TOKEN_COOKIE = TOKEN_COOKIES[WORKER]

WORKER_PHOTO_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
WORKER_PHOTO_MAX_BYTES = 8 * 1024 * 1024

_RESIDENT_REQUEST_SETTLED_STATES = ("Resolved", "Rejected", "Closed")


def _token_from_request(token=None):
    return presented_token(WORKER, token)[0]


def _resolve_worker(token):
    return resolve_portal_subject(WORKER, token, required=True)


def _fmt_date(value):
    return frappe.utils.cstr(value) if value else None


def _iqama_of(emp):
    return (
        emp.get("iqama") or emp.get("iqama_no"),
        emp.get("iqama_expiry") or emp.get("valid_upto"),
    )


def _worker_documents(emp):
    documents = []
    iqama_no, iqama_expiry = _iqama_of(emp)
    if iqama_no or iqama_expiry:
        documents.append(
            {
                "type": "iqama",
                "number": iqama_no,
                "expiry": _fmt_date(iqama_expiry),
                "days_left": _days_until(iqama_expiry),
            }
        )
    passport_no = emp.get("passport_number")
    passport_expiry = emp.get("passport_expiry")
    if passport_no:
        documents.append(
            {
                "type": "passport",
                "number": passport_no,
                "expiry": _fmt_date(passport_expiry),
                "days_left": _days_until(passport_expiry),
            }
        )
    return documents


def _active_assignment(employee):
    rows = frappe.get_all(
        "Housing Assignment",
        filters={
            "employee": employee,
            "docstatus": 1,
            "check_out_date": ["is", "not set"],
        },
        fields=[
            "name",
            "building",
            "room",
            "bed",
            "project",
            "check_in_date",
            "stay_type",
            "expected_checkout_date",
            "notes",
        ],
        order_by="check_in_date desc",
        limit=1,
    )
    return rows[0] if rows else None


def _request_status_timeline(req):
    timeline = [
        {
            "key": "created",
            "status": "New",
            "timestamp": frappe.utils.cstr(req.get("creation")) if req.get("creation") else None,
        }
    ]
    status = req.get("status")
    if status in _RESIDENT_REQUEST_SETTLED_STATES:
        timeline.append(
            {
                "key": "closed",
                "status": status,
                "timestamp": frappe.utils.cstr(req.get("closed_on") or req.get("modified"))
                if (req.get("closed_on") or req.get("modified"))
                else None,
            }
        )
    else:
        if status and status != "New":
            timeline.append(
                {
                    "key": "current",
                    "status": status,
                    "timestamp": frappe.utils.cstr(req.get("modified"))
                    if req.get("modified")
                    else None,
                }
            )
    return timeline


def _net_custody_items(rows):
    agg = {}
    for r in rows:
        key = (r.building, r.item)
        bucket = agg.setdefault(
            key,
            {
                "item": r.item,
                "item_name": r.item_name,
                "building": r.building,
                "uom": r.uom,
                "qty": 0.0,
                "received_date": None,
                "_issue_voucher": None,
            },
        )
        bucket["qty"] += flt(r.signed_qty)
        if flt(r.signed_qty) > 0:
            bucket["received_date"] = _fmt_date(r.posting_date)
            if r.voucher_type == "Custody Issue" and r.voucher_no:
                bucket["_issue_voucher"] = r.voucher_no
    return [bucket for bucket in agg.values() if bucket["qty"] >= 1e-9]


def _custody_issued_by(custody_issue, building):
    owner = None
    if custody_issue:
        owner = frappe.db.get_value("Custody Issue", custody_issue, "owner")
    if owner:
        return frappe.utils.get_fullname(owner) or owner
    if building:
        sup = frappe.db.get_value(
            "Building", building, "responsible_supervisor"
        )
        if sup:
            return frappe.utils.get_fullname(sup) or sup
    return None


def _attach_worker_photo(doc, photo, photo_filename):
    from apex.salis.api.driver_portal.images import verified_image_type

    photo = (photo or "").strip()
    if not photo:
        return

    content_type = verified_image_type(photo, max_bytes=WORKER_PHOTO_MAX_BYTES)

    stem = (photo_filename or "request-photo").strip() or "request-photo"
    stem = stem.replace("\\", "/").split("/")[-1]
    stem = os.path.splitext(stem)[0] or "request-photo"
    fname = f"{stem}{WORKER_PHOTO_EXTENSIONS[content_type]}"

    saved = save_file(
        fname,
        photo,
        doc.doctype,
        doc.name,
        decode=True,
        is_private=1,
        df="attachment",
    )
    doc.db_set("attachment", saved.file_url)


def _clean_adhoc_passengers(passengers):
    passengers = frappe.parse_json(passengers or "[]")
    rows = []
    for p in passengers or []:
        full_name = (p.get("full_name") or "").strip()
        id_number = (p.get("id_number") or "").strip()
        if not full_name or not id_number:
            frappe.throw(_("Each additional passenger needs a name and an ID number."))
        expiry = (p.get("id_expiry") or "").strip() or None
        if expiry:
            try:
                expiry = frappe.utils.getdate(expiry).isoformat()
            except Exception:
                frappe.throw(_("An additional passenger's ID expiry is not a valid date."))
        rows.append(
            {
                "full_name": full_name[:140],
                "id_number": id_number[:64],
                "id_expiry": expiry,
                "nationality": (p.get("nationality") or "").strip()[:64] or None,
                "phone": (p.get("phone") or "").strip()[:32] or None,
            }
        )
    return rows


def _building_in_charge(employee):
    assignment = _active_assignment(employee)
    user = assignment and frappe.db.get_value(
        "Building", assignment.get("building"), "responsible_supervisor"
    )
    if not user:
        return None
    return {
        "name": frappe.utils.get_fullname(user) or user,
        "phone": frappe.db.get_value("User", user, "mobile_no"),
    }


def _today_driver(employee):
    resolved = _worker_today_dispatch_trip(employee)
    if not resolved:
        return None
    driver = frappe.db.get_value("Dispatch Trip", resolved[0], "driver")
    if not driver:
        return None
    d = frappe.db.get_value("Salis Driver", driver, ["full_name", "phone"], as_dict=True)
    return d or None
