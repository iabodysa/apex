# Copyright (c) 2026, AFMCO and contributors
import frappe


def execute():
    """Stamp a generous expiry on existing Masar Worker Token rows (T-629, ONE-TIME).

    The token now carries a TTL (``expires_on``); a leaked /masar link is no longer
    valid forever. Rows minted before the field existed have a NULL ``expires_on``,
    which the resolver treats as never-expiring (the deliberate backward-compat seam).
    To CLOSE that NULL window without instantly invalidating any currently distributed
    worker link, give every existing row a generous future expiry — the same window a
    freshly minted link gets (TOKEN_TTL_DAYS), measured from today. A worker re-opening
    their link, or a supervisor re-sharing it (Show Link extends the expiry), keeps it
    alive well beyond this; only a genuinely abandoned/leaked link eventually lapses.

    Never clobbers a row that already carries an expiry (idempotent, re-run safe).
    No-op on fresh installs (no pre-existing rows). PRUNE once every deployed site has
    run it (tracked in tabPatch Log).
    """
    from apex.apex_core.doctype.masar_worker_token.masar_worker_token import (
        _token_expiry,
    )

    names = frappe.get_all(
        "Masar Worker Token",
        filters={"expires_on": ["is", "not set"], "token": ["is", "set"]},
        pluck="name",
    )
    if not names:
        return

    expiry = _token_expiry()
    for name in names:
        # update_modified=False: a backfill must not touch the audit timestamp, and
        # the token field is unchanged (only the new expiry is stamped).
        frappe.db.set_value(
            "Masar Worker Token", name, "expires_on", expiry, update_modified=False
        )
