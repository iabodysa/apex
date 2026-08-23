# Copyright (c) 2026, afmcoltd
"""Rental Accrual Ledger controller.

Read-only, machine-written daily rental memo. No DocPerm grants create/write/
delete to any human role; rows are inserted only by the rental accrual engine
(``rental_engine.daily_rental_accrual``) using ignore_permissions. This DocType
posts NO General Ledger / accounting entry — each row is an operational memo.
"""

from __future__ import annotations

import frappe
from frappe.model.document import Document

UNIQUE_KEY = ["vehicle", "accrual_date", "reversal_of"]
UNIQUE_KEY_NAME = "unique_ral_vehicle_date"


class RentalAccrualLedger(Document):
    pass


def _drop_stale_unique_key():
    """Drop ``unique_ral_vehicle_date`` when its live columns are not ``UNIQUE_KEY``.

    The index predates ``reversal_of``: it shipped as (vehicle, accrual_date)
    only, which rejects a same-day reversal outright (``rental_engine.
    reverse_rental_accrual`` posts one dated to the SAME day it negates).
    ``add_unique_guarded`` below only checks the constraint NAME, so a narrower
    index of that name would otherwise survive every migrate and keep blocking
    the exact insert the reversal makes. Best-effort and idempotent: once the
    live columns already match, this is a no-op; a fresh install has no index
    yet, so the SELECT returns no rows and nothing is dropped.

    ``information_schema.STATISTICS`` is read directly because the one thing
    ``frappe.db.has_index`` (frappe/database/mariadb/database.py:375) cannot do is
    report an index's COLUMNS — it matches ``Key_name`` alone, which is exactly the
    name this index keeps while its columns are wrong. Both parameters are bound.
    A probe failure is logged through ``frappe.get_traceback`` and nothing is
    dropped: refusing to guess is safer than dropping a constraint on a guess.
    """
    try:
        rows = frappe.db.sql(
            """
            SELECT COLUMN_NAME
            FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = %s
              AND INDEX_NAME = %s
            ORDER BY SEQ_IN_INDEX
            """,
            ("tabRental Accrual Ledger", UNIQUE_KEY_NAME),
            as_dict=True,
        )
    except Exception:
        return
    live_columns = [r["COLUMN_NAME"] for r in rows]
    if not live_columns or live_columns == UNIQUE_KEY:
        return
    try:
        frappe.db.sql(
            "ALTER TABLE `tabRental Accrual Ledger` DROP INDEX `{0}`".format(UNIQUE_KEY_NAME)
        )
    except Exception:
        frappe.log_error(
            message=frappe.get_traceback(),
            title=f"Could not drop stale {UNIQUE_KEY_NAME}"[:140],
        )


def on_doctype_update():
    """Hard idempotency backstop: a composite UNIQUE index on (vehicle,
    accrual_date, reversal_of) so the daily one-row-per-vehicle-per-day accrual
    cannot be double-posted at the DB level even if the engine's check-then-insert
    is bypassed by a race. ``reversal_of`` is part of the key, not a separate
    constraint, for the same reason Trip Boarding Ledger's key carries it: an
    original row's ``reversal_of`` is unset (a Link column is NOT NULL DEFAULT
    ''), so two originals for one vehicle+day collide — which is what the daily
    accrual job's own check is for — while a reversal's ``reversal_of`` names its
    original, dated to the SAME day it negates (``rental_engine.
    reverse_rental_accrual``), so it cannot collide with that original and only a
    second reversal of the same original would. Created/kept in sync on migrate
    via Frappe's on_doctype_update hook. Guarded so pre-existing duplicate data
    logs rather than aborting migrate."""
    from apex.apex_core.utils.ledger_index import add_unique_guarded

    _drop_stale_unique_key()
    add_unique_guarded(
        "Rental Accrual Ledger",
        UNIQUE_KEY,
        constraint_name=UNIQUE_KEY_NAME,
    )
