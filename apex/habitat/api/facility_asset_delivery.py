# Copyright (c) 2026, afmcoltd
"""Whitelisted API for the Facility Asset Delivery 3-exit transfer lock and the
on-site code receipt.

THE 2-EXIT TRANSFER LOCK, the core of this module: a submitted delivery sits in
``Pending Exits`` until BOTH exit checkpoints pass IN ORDER, one on each side of
the hand-over. Only clearing the last exit opens the lock — status flips to
``Released`` and the on-site code is issued. Until then the asset has NOT moved.

  exit 1  Gate / hand-over      Procurement Supervisor    pass_exit_1
  exit 3  Receiving Acceptance  receiving supervisor      pass_exit_3
                                OR Resident Supervisor

Each ``pass_exit_N`` is fail-closed: it requires the delivery to be submitted and
in ``Pending Exits``, requires the PRIOR exit to already be cleared, and requires
the caller to hold the exit's role (or be System Manager). An exit cannot be
cleared twice and cannot be skipped.

THE ON-SITE CODE RECEIPT: once Released, the receiving side confirms an on-site
6-digit code (the SAME mechanism as Custody Handover, reused via ``hash_otp`` /
``generate_otp``) to flip the delivery to ``Delivered`` and ACTUALLY move the
tracked asset into the destination. Separation of duties: the initiator who
shipped the asset cannot confirm its own receipt. The confirm is fail-closed:
lockout -> expiry -> released-state gate -> code match, and a mismatch reveals
nothing about which check failed."""

from __future__ import annotations

import hmac

import frappe
from frappe import _
from frappe.utils import now_datetime

from apex.habitat.doctype.custody_handover.custody_handover import (
    generate_otp,
    hash_otp,
)
from apex.habitat.doctype.facility_asset_delivery.facility_asset_delivery import (
    DELIVERY_DOCTYPE,
    move_asset_on_delivery,
)

from apex.apex_core.utils.otp_lockout import charge_wrong_code
from apex.habitat.utils.otp_policy import (
    ELEVATED_ROLE,
    LOCKOUT_MINUTES,
    MAX_OTP_ATTEMPTS,
)

EXIT_ROLES = {
    1: "Procurement Supervisor",
    3: "Resident Supervisor",
}

EXIT_ORDER = sorted(EXIT_ROLES)
LAST_EXIT = EXIT_ORDER[-1]


def _get_submitted(delivery: str):
    """Returns the submitted Facility Asset Delivery, or blocks the action if it is not submitted."""
    doc = frappe.get_doc(DELIVERY_DOCTYPE, delivery)
    if doc.docstatus != 1:
        frappe.throw(_("Only a submitted delivery can be actioned."))
    return doc


def _require_role(role: str):
    """Caller must hold the exit's role (or be System Manager). Write permission on
    the delivery is also required (defense in depth on top of the role grant)."""
    roles = frappe.get_roles(frappe.session.user)
    if "System Manager" in roles or role in roles:
        return
    frappe.throw(
        _("Only a {0} may clear this exit.").format(_(role)),
        frappe.PermissionError,
    )


def _pass_exit(delivery: str, n: int):
    """Clear exit ``n`` of the 3-exit lock. Fail-closed: submitted + Pending Exits,
    the prior exit already cleared, the caller holds exit ``n``'s role, and the
    exit is not already cleared. Clearing exit 3 opens the lock (Released) and
    issues the on-site code."""
    doc = _get_submitted(delivery)
    frappe.has_permission(DELIVERY_DOCTYPE, "write", doc=doc, throw=True)

    if doc.status != "Pending Exits":
        frappe.throw(
            _("Exit checkpoints can only be cleared while the delivery is Pending Exits.")
        )

    flag = f"exit{n}_{_exit_slug(n)}_cleared"
    if doc.get(flag):
        frappe.throw(_("Exit {0} has already been cleared.").format(n))

    for prior in EXIT_ORDER:
        if prior >= n:
            break
        if not doc.get(f"exit{prior}_{_exit_slug(prior)}_cleared"):
            frappe.throw(
                _("Exit {0} must be cleared before exit {1}.").format(prior, n)
            )

    _require_role(EXIT_ROLES[n])

    now = now_datetime()
    doc.db_set(
        {
            flag: 1,
            f"exit{n}_cleared_by": frappe.session.user,
            f"exit{n}_cleared_on": now,
        }
    )

    code = None
    if n == LAST_EXIT:
        doc.db_set("status", "Released")
        code = generate_otp(doc)
    return {"delivery": doc.name, "code": code}


def _exit_slug(n: int) -> str:
    """Returns the slug name (security, logistics or receiving) for a given exit checkpoint number."""
    return {1: "security", 2: "logistics", 3: "receiving"}[n]


@frappe.whitelist(methods=["POST"])
def pass_exit_1(delivery: str):
    """Exit 1 of 2 — Gate clearance at the source (Procurement Supervisor)."""
    return _pass_exit(delivery, 1)


@frappe.whitelist(methods=["POST"])
def pass_exit_3(delivery: str):
    """Exit 2 of 2 — Receiving acceptance (Resident Supervisor). Opens the lock
    (status -> Released) and issues the on-site code."""
    return _pass_exit(delivery, 3)


@frappe.whitelist(methods=["POST"])
def confirm_receipt(delivery: str, code: str):
    """Confirm the on-site code receipt and actually move the asset.

    Only valid once the 3-exit lock is open (status Released). Fail-closed gate
    order: lockout -> expiry -> released-state gate -> code match. Separation of
    duties: the initiator who shipped the asset cannot confirm its own receipt. A
    wrong code increments the attempt counter and, on the third miss, locks the
    delivery for a few minutes; the thrown error is deliberately generic."""
    doc = _get_submitted(delivery)
    frappe.has_permission(DELIVERY_DOCTYPE, "write", doc=doc, throw=True)

    if frappe.session.user == doc.initiated_by:
        frappe.throw(
            _("The initiator who shipped the asset cannot confirm its own receipt."),
            frappe.PermissionError,
        )

    user = frappe.session.user
    if user != doc.receiving_supervisor and ELEVATED_ROLE not in frappe.get_roles(user):
        frappe.throw(
            _("Only the receiving supervisor or an Accommodation Manager may confirm receipt."),
            frappe.PermissionError,
        )

    locked = frappe.db.get_value(
        DELIVERY_DOCTYPE,
        doc.name,
        ["status", "otp_attempts", "otp_locked_until", "otp_expires_at", "otp_hash"],
        as_dict=True,
        for_update=True,
    )

    if locked.status == "Delivered":
        return doc.name

    now = now_datetime()
    if locked.otp_locked_until and now < locked.otp_locked_until:
        frappe.throw(_("Too many incorrect attempts. This delivery is temporarily locked."))

    if locked.status != "Released":
        frappe.throw(_("Both exit checkpoints must be cleared before confirming receipt."))

    if locked.otp_expires_at and now > locked.otp_expires_at:
        frappe.throw(_("The on-site code has expired. Ask the initiator to regenerate it."))

    if locked.otp_hash and hmac.compare_digest(hash_otp(code or "", doc.name), locked.otp_hash):
        return _move_and_deliver(doc)

    attempts = (locked.otp_attempts or 0) + 1
    charge_wrong_code(
        DELIVERY_DOCTYPE, doc.name,
        attempts=MAX_OTP_ATTEMPTS, lockout_minutes=LOCKOUT_MINUTES,
    )
    doc.db_set("otp_attempts", attempts)
    frappe.throw(_("Invalid code."))


def _move_and_deliver(doc):
    """Move the asset into the destination, mark the delivery Delivered, stamp the
    verification time, and clear the stored hash. Idempotent on the move (the
    movement-ledger engine skips a source already ledgered)."""
    move_asset_on_delivery(doc)
    doc.db_set(
        {
            "otp_verified_on": now_datetime(),
            "otp_hash": None,
            "otp_locked_until": None,
            "otp_attempts": 0,
            "status": "Delivered",
        }
    )
    return doc.name


@frappe.whitelist(methods=["POST"])
def regenerate_code(delivery: str):
    """Issue a fresh on-site code + expiry window and clear any lockout. Restricted
    to the initiator side; only valid once Released; returns the new plaintext ONCE."""
    doc = _get_submitted(delivery)
    frappe.has_permission(DELIVERY_DOCTYPE, "write", doc=doc, throw=True)
    user = frappe.session.user
    if user != doc.initiated_by and ELEVATED_ROLE not in frappe.get_roles(user):
        frappe.throw(
            _("Only the initiator or an Accommodation Manager may regenerate the code."),
            frappe.PermissionError,
        )
    if doc.status != "Released":
        frappe.throw(_("A code can only be regenerated once the delivery is Released."))
    return generate_otp(doc)
