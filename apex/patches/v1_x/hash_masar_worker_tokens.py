# Copyright (c) 2026, AFMCO and contributors
import frappe
from frappe.utils.password import encrypt


def _looks_hashed(token: str) -> bool:
    """True when ``token`` is already a 64-char SHA-256 hex digest (i.e. hardened)."""
    return len(token) == 64 and all(c in "0123456789abcdef" for c in token.lower())


def execute():
    """Hash existing plaintext Masar Worker Token rows at rest (P-104, ONE-TIME).

    Historically the ``token`` column held the RAW personal token in clear, so a
    direct row read handed out a working ``/masar`` link. The token now lives ONLY as
    a SHA-256 hash (matched by the resolver) plus a site-key-encrypted recoverable
    copy in ``token_enc`` (so the desk can still re-share the same link without
    rotating). Runs AFTER model sync so the ``token_enc`` field exists.

    For each row still carrying a plaintext token, replace the ``token`` column with
    its hash and stash the encrypted copy — the raw value never leaves this process
    and is never logged. Idempotent: a row whose ``token`` is already a 64-hex digest
    is left untouched (its raw is, correctly, unrecoverable), and re-running finds
    only hashed rows. No-op on fresh installs (no pre-existing rows). PRUNE once every
    deployed site has run it (tracked in tabPatch Log).
    """
    rows = frappe.get_all(
        "Masar Worker Token",
        filters={"token": ["is", "set"]},
        fields=["name", "token"],
    )
    for row in rows:
        token = (row.token or "").strip()
        # Already hardened (post-P-104 mint, or a prior run of this patch): skip so we
        # never double-hash. A hashed row's raw is not recoverable — nothing to do.
        if not token or _looks_hashed(token):
            continue
        # `token` is still the raw secret: keep an encrypted recoverable copy, then
        # replace the stored value with its hash. update_modified=False: an at-rest
        # migration must not disturb the audit timestamp.
        from apex.apex_core.doctype.masar_worker_token.masar_worker_token import (
            _hash_token,
        )

        frappe.db.set_value(
            "Masar Worker Token",
            row.name,
            {"token": _hash_token(token), "token_enc": encrypt(token)},
            update_modified=False,
        )
