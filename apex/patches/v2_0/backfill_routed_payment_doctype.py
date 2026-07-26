# Copyright (c) 2026, AFMCO and contributors
"""Stamp ``Salis Payment Request.linked_payment_doctype`` on rows written before it
existed (A-278).

``linked_payment_entry`` used to be ``Link -> Payment Entry`` while the Payment Router
built whatever ``Payment Routing Settings.target_payment_doctype`` named — its own
default being the native ``Payment Request``, never a Payment Entry. The router stamps
that field with ``db_set``, which skips ``validate`` entirely
(frappe/model/document.py:1235-1239), so the link check never fired and every routed
request on an existing site carries a name that its declared type cannot resolve.

The field is now a ``Dynamic Link`` over the new ``linked_payment_doctype`` companion.
This patch fills that companion for the historical rows, by asking which table actually
holds a document of that name.

Fail-closed on ambiguity: a name matching zero or several candidate DocTypes is LEFT
BLANK and reported, never guessed. A guessed type is exactly the "plausible-looking but
wrong" record this work exists to prevent, and a blank companion is visibly incomplete
where a wrong one is not. Nothing is deleted or overwritten.

post_model_sync: it WRITES ``linked_payment_doctype``, a column that only exists once
model sync has re-imported the DocType. Idempotent — it only ever considers rows whose
companion is still empty.
"""

from __future__ import annotations

import frappe

from apex.apex_core.payment_router import (
    DEFAULT_TARGET_DOCTYPE,
    LINK_DOCTYPE_FIELD,
    LINK_NAME_FIELD,
    SOURCE_DOCTYPE,
)

# The field's historical declared type. Kept explicitly: on a site that really did set
# the reference by hand, "Payment Entry" is the correct answer and nothing else knows it.
LEGACY_TARGET_DOCTYPE = "Payment Entry"


def _candidate_doctypes() -> list[str]:
    """Every DocType a stored payment reference could plausibly belong to.

    The router's currently-configured target first, then its built-in default, then the
    field's historical declared type. Only DocTypes that exist AND have a table are
    kept, so an uninstalled optional app cannot raise mid-migrate.
    """
    configured = frappe.db.get_single_value("Payment Routing Settings", "target_payment_doctype")
    ordered = [configured, DEFAULT_TARGET_DOCTYPE, LEGACY_TARGET_DOCTYPE]
    out = []
    for doctype in ordered:
        if not doctype or doctype in out:
            continue
        if frappe.db.exists("DocType", doctype) and frappe.db.table_exists(doctype):
            out.append(doctype)
    return out


def execute() -> None:
    # Only the untyped side is filtered in SQL (["in", [None, ""]] is the ORM form that
    # matches NULL); the "has a payment name" half is applied in Python, because a
    # negated NULL filter is the one the ORM does not reliably express.
    rows = frappe.get_all(
        SOURCE_DOCTYPE,
        filters={LINK_DOCTYPE_FIELD: ["in", [None, ""]]},
        fields=["name", LINK_NAME_FIELD],
    )
    if not rows:
        return

    candidates = _candidate_doctypes()
    unresolved = []
    for row in rows:
        payment = (row[LINK_NAME_FIELD] or "").strip()
        if not payment:
            continue
        matches = [dt for dt in candidates if frappe.db.exists(dt, payment)]
        if len(matches) != 1:
            unresolved.append(f"{row['name']} -> {payment} ({len(matches)} matches)")
            continue
        frappe.db.set_value(
            SOURCE_DOCTYPE, row["name"], LINK_DOCTYPE_FIELD, matches[0], update_modified=False
        )

    if unresolved:
        # Surfaced, not guessed: an operator has to say which document these name.
        frappe.log_error(
            title="Apex: unresolved routed payment links",
            message=(
                "Salis Payment Request rows whose linked payment could not be typed "
                f"against {candidates}; linked_payment_doctype left blank:\n"
                + "\n".join(unresolved)
            ),
        )
    frappe.db.commit()
