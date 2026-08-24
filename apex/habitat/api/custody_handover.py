# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import hmac

import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime

from apex.habitat.doctype.custody_handover.custody_handover import (
    VOUCHER_TYPE,
    generate_otp,
    hash_otp,
)

from apex.apex_core.utils.otp_lockout import charge_wrong_code, is_locked_out
from apex.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import (
    post_stock_entry,
    reverse_stock_entries,
)
from apex.habitat.utils.otp_policy import (
    ELEVATED_ROLE,
    LOCKOUT_MINUTES,
    MAX_OTP_ATTEMPTS,
)


def _get_submitted(handover: str):
    doc = frappe.get_doc(VOUCHER_TYPE, handover)
    if doc.docstatus != 1:
        frappe.throw(_("Only a submitted handover can be actioned."))
    return doc


def _require_receiving_side(doc):
    frappe.has_permission(VOUCHER_TYPE, "write", doc=doc, throw=True)
    user = frappe.session.user
    if user == doc.receiving_supervisor or ELEVATED_ROLE in frappe.get_roles(user):
        return
    frappe.throw(
        _("Only the receiving supervisor or an Accommodation Manager may action this handover."),
        frappe.PermissionError,
    )


@frappe.whitelist(methods=["POST"])
def confirm_handover(handover: str, otp: str):
    doc = _get_submitted(handover)
    _require_receiving_side(doc)

    if frappe.session.user == doc.procurement_supervisor:
        frappe.throw(
            _("The procurement supervisor who shipped the goods cannot confirm their own receipt."),
            frappe.PermissionError,
        )

    locked = frappe.db.get_value(
        VOUCHER_TYPE, doc.name,
        ["status", "otp_expires_at", "otp_hash"],
        as_dict=True, for_update=True,
    )

    if locked.status == "Confirmed":
        return doc.name

    now = now_datetime()
    otp_required = bool(frappe.db.get_single_value("Habitat Settings", "require_handover_otp"))

    if otp_required and is_locked_out(doc.doctype, doc.name, attempts=MAX_OTP_ATTEMPTS):
        frappe.throw(
            _("Too many incorrect codes for this handover. Wait a few minutes and try again."),
            frappe.RateLimitExceededError,
        )

    if otp_required and locked.otp_expires_at and now > locked.otp_expires_at:
        frappe.throw(_("The one-time password has expired. Ask the procurement supervisor to regenerate it."))

    if otp_required and locked.status != "Approved":
        frappe.throw(_("Review and approve the handover before confirming receipt."))

    if not otp_required:
        if locked.status != "Approved":
            frappe.throw(_("Review and approve the handover before confirming receipt."))
        return _post_receive_and_confirm(doc)

    if locked.otp_hash and hmac.compare_digest(hash_otp(otp or "", doc.name), locked.otp_hash):
        return _post_receive_and_confirm(doc)

    charge_wrong_code(
        doc.doctype, doc.name,
        attempts=MAX_OTP_ATTEMPTS, lockout_minutes=LOCKOUT_MINUTES,
    )
    frappe.throw(_("Invalid code."))


def _post_receive_and_confirm(doc):
    if frappe.db.exists(
        "Accommodation Stock Ledger",
        {
            "voucher_type": VOUCHER_TYPE,
            "voucher_no": doc.name,
            "building": doc.to_building,
            "signed_qty": [">", 0],
            "is_cancelled": 0,
        },
    ):
        return doc.name
    now = now_datetime()
    for row in doc.items:
        post_stock_entry(
            item_type=row.item_type, item=row.item, qty=flt(row.qty),
            building=doc.to_building, employee=None,
            from_building=doc.from_building, to_building=doc.to_building,
            voucher_type=VOUCHER_TYPE, voucher_no=doc.name, voucher_detail_no=row.name,
            posting_date=doc.handover_date,
        )
    doc.db_set({
        "otp_verified_on": now,
        "otp_hash": None,
        "status": "Confirmed",
    })
    return doc.name


@frappe.whitelist(methods=["POST"])
def approve_handover(handover: str, all_items_verified=None):
    doc = _get_submitted(handover)
    _require_receiving_side(doc)
    if doc.status == "Approved":
        return doc.name
    if doc.status != "Under Review":
        frappe.throw(_("Only a handover Under Review can be approved."))
    if all_items_verified is not None and cint(all_items_verified) and not doc.all_items_verified:
        doc.db_set("all_items_verified", 1)
    if not doc.all_items_verified:
        frappe.throw(_("Confirm that all items have been verified before approving."))
    doc.db_set("status", "Approved")
    return doc.name


@frappe.whitelist(methods=["POST"])
def reject_handover(handover: str, reason: str):
    doc = _get_submitted(handover)
    _require_receiving_side(doc)
    if not (reason or "").strip():
        frappe.throw(_("A reason is required to reject a handover."))

    locked_status = frappe.db.get_value(VOUCHER_TYPE, doc.name, "status", for_update=True)
    if locked_status in ("Confirmed", "Rejected", "Cancelled"):
        frappe.throw(_("Handover {0} can no longer be rejected.").format(doc.name))
    reverse_stock_entries(VOUCHER_TYPE, doc.name)
    doc.add_comment("Comment", _("Rejected: {0}").format(reason))
    doc.db_set("status", "Rejected")
    return doc.name


@frappe.whitelist(methods=["POST"])
def regenerate_handover_otp(handover: str):
    doc = _get_submitted(handover)
    frappe.has_permission(VOUCHER_TYPE, "write", doc=doc, throw=True)
    user = frappe.session.user
    if user != doc.procurement_supervisor and ELEVATED_ROLE not in frappe.get_roles(user):
        frappe.throw(
            _("Only the procurement supervisor or an Accommodation Manager may regenerate the code."),
            frappe.PermissionError,
        )
    if doc.status in ("Confirmed", "Rejected", "Cancelled"):
        frappe.throw(_("Handover {0} is closed; a new code cannot be issued.").format(doc.name))
    return generate_otp(doc)
