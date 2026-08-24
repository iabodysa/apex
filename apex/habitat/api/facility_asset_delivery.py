# Copyright (c) 2026, afmcoltd

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

from apex.apex_core.utils.otp_lockout import charge_wrong_code, is_locked_out
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
    doc = frappe.get_doc(DELIVERY_DOCTYPE, delivery)
    if doc.docstatus != 1:
        frappe.throw(_("Only a submitted delivery can be actioned."))
    return doc


def _pass_exit(delivery: str, n: int):
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

    frappe.only_for([EXIT_ROLES[n], "System Manager"], message=True)

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
    return {1: "security", 2: "logistics", 3: "receiving"}[n]


@frappe.whitelist(methods=["POST"])
def pass_exit_1(delivery: str):
    return _pass_exit(delivery, 1)


@frappe.whitelist(methods=["POST"])
def pass_exit_3(delivery: str):
    return _pass_exit(delivery, 3)


@frappe.whitelist(methods=["POST"])
def confirm_receipt(delivery: str, code: str):
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
        ["status", "otp_expires_at", "otp_hash"],
        as_dict=True,
        for_update=True,
    )

    if locked.status == "Delivered":
        return doc.name

    now = now_datetime()
    if is_locked_out(DELIVERY_DOCTYPE, doc.name, attempts=MAX_OTP_ATTEMPTS):
        frappe.throw(
            _("Too many incorrect codes for this delivery. Wait a few minutes and try again."),
            frappe.RateLimitExceededError,
        )

    if locked.status != "Released":
        frappe.throw(_("Both exit checkpoints must be cleared before confirming receipt."))

    if locked.otp_expires_at and now > locked.otp_expires_at:
        frappe.throw(_("The on-site code has expired. Ask the initiator to regenerate it."))

    if locked.otp_hash and hmac.compare_digest(hash_otp(code or "", doc.name), locked.otp_hash):
        return _move_and_deliver(doc)

    charge_wrong_code(
        DELIVERY_DOCTYPE, doc.name,
        attempts=MAX_OTP_ATTEMPTS, lockout_minutes=LOCKOUT_MINUTES,
    )
    frappe.throw(_("Invalid code."))


def _move_and_deliver(doc):
    move_asset_on_delivery(doc)
    doc.db_set(
        {
            "otp_verified_on": now_datetime(),
            "otp_hash": None,
            "status": "Delivered",
        }
    )
    return doc.name


@frappe.whitelist(methods=["POST"])
def regenerate_code(delivery: str):
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
