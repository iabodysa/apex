# Copyright (c) 2026, afmcoltd
"""Whitelisted API for the OTP-confirmed Custody Handover.

Confirmation is fail-closed: lockout, then expiry, then the review-and-approve
gate, are all checked BEFORE the code is compared, and a mismatch reveals nothing
about which check failed. Separation of duties forbids the procurement supervisor
who shipped the goods from confirming their own receipt. The receive leg posts
into the destination store only on a verified code (or, when the OTP requirement
is switched off, on approval alone)."""

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
from apex.habitat.utils.otp_policy import (
    ELEVATED_ROLE,
    LOCKOUT_MINUTES,
    MAX_OTP_ATTEMPTS,
)


def _get_submitted(handover: str):
    """Loads the named custody handover and blocks the action unless it has been submitted."""
    doc = frappe.get_doc(VOUCHER_TYPE, handover)
    if doc.docstatus != 1:
        frappe.throw(_("Only a submitted handover can be actioned."))
    return doc


def _require_receiving_side(doc):
    """Write permission plus membership of the receiving side (the receiving
    supervisor or an Accommodation Manager)."""
    frappe.has_permission(VOUCHER_TYPE, "write", doc=doc, throw=True)
    user = frappe.session.user
    if user == doc.receiving_supervisor or ELEVATED_ROLE in frappe.get_roles(user):
        return
    frappe.throw(
        _("Only the receiving supervisor or an Accommodation Manager may action this handover."),
        frappe.PermissionError,
    )


def _otp_required() -> bool:
    """Returns whether Habitat Settings currently requires an OTP to confirm a handover."""
    return bool(frappe.db.get_single_value("Habitat Settings", "require_handover_otp"))


@frappe.whitelist(methods=["POST"])
def confirm_handover(handover: str, otp: str):
    """Confirm receipt and post the receive leg into the destination store.

    Fail-closed gate order: lockout -> expiry -> review/approve gate -> code match.
    Separation of duties: the procurement supervisor cannot confirm their own
    shipment. A wrong code increments the attempt counter and, on the third miss,
    locks the handover for a few minutes; the thrown error is deliberately generic."""
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
    otp_required = _otp_required()

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


def _receive_leg_posted(doc) -> bool:
    """True once this handover's receive leg exists: a live positive-qty ledger
    row landing in to_building under this voucher. Distinguishes the receive leg
    from the ship leg (negative, in from_building), which shares the voucher_no."""
    return bool(frappe.db.exists(
        "Accommodation Stock Ledger",
        {
            "voucher_type": VOUCHER_TYPE,
            "voucher_no": doc.name,
            "building": doc.to_building,
            "signed_qty": [">", 0],
            "is_cancelled": 0,
        },
    ))


def _post_receive_and_confirm(doc):
    """Post the receive leg into the destination store, mark the handover
    Confirmed, stamp the verification time, and clear the stored hash. Idempotent
    on the receive leg — re-entry posts nothing further (belt-and-braces with the
    FOR UPDATE lock + Confirmed-status short-circuit in confirm_handover)."""
    from apex.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import (
        post_stock_entry,
    )
    if _receive_leg_posted(doc):
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
    """Move a handover from Under Review to Approved. Every line must have been
    physically checked (all_items_verified) first.

    """
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
    """Reject a handover: reverse the ship leg and mark it Rejected.

    Not a cancel — docstatus stays 1 — so there is no before_cancel to move the
    positivity refusal into. It is already ordered correctly: reverse_stock_entries
    raises before the comment and the status write below, so a refused rejection
    leaves the handover exactly as it was.

    The status is re-read under a row lock, the way confirm_handover reads it: the
    reversal below takes no lock of its own (_live_rows is a plain read), so two
    rejections arriving together both found live rows and credited the source store
    twice for one shipment."""
    doc = _get_submitted(handover)
    _require_receiving_side(doc)
    if not (reason or "").strip():
        frappe.throw(_("A reason is required to reject a handover."))

    locked_status = frappe.db.get_value(VOUCHER_TYPE, doc.name, "status", for_update=True)
    if locked_status in ("Confirmed", "Rejected", "Cancelled"):
        frappe.throw(_("Handover {0} can no longer be rejected.").format(doc.name))
    from apex.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger import (
        reverse_stock_entries,
    )
    reverse_stock_entries(VOUCHER_TYPE, doc.name)
    doc.add_comment("Comment", _("Rejected: {0}").format(reason))
    doc.db_set("status", "Rejected")
    return doc.name


@frappe.whitelist(methods=["POST"])
def regenerate_handover_otp(handover: str):
    """Issue a fresh code and expiry window and clear any lockout. Restricted to
    the procurement supervisor side; returns the new plaintext ONCE."""
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
