"""Accommodation Ledger controller.

Hidden, machine-written cost allocation ledger. No DocPerm grants write/create
to any human role; rows are inserted by scheduled jobs and hooks using
ignore_permissions. When GL posting is disabled in Habitat Settings, rows are
operational memos and no GL Entry is posted.
"""

from __future__ import annotations

from frappe.model.document import Document


class AccommodationLedger(Document):
    pass


def before_save(doc, method=None):
    # Validate document properties
    if not doc.doctype:
        return


def on_doctype_update():
    """Hard idempotency backstop: a composite UNIQUE index matching the daily
    cost-allocation guard ``(employee, posting_date, assignment, building,
    ledger_type)`` so the racy daily job cannot double-post the same employee's
    per-type daily share even if its check-then-insert is bypassed.

    Column choice: the daily allocation in ``habitat.tasks
    .daily_accommodation_cost_allocation`` is the high-frequency, race-prone
    writer and these five columns are exactly its existing ``frappe.db.exists``
    key. The other writers (Utility Bill Entry, Maintenance Work Order) post rows
    with ``employee``/``assignment`` NULL — and MariaDB treats NULLs as distinct
    in a UNIQUE index — so this constraint does not falsely collide their rows
    (including a utility original + its reversal); those paths keep their own
    ``source_doctype``/``source_name`` app-level guards and run on user submit,
    not on a daily loop. Guarded so pre-existing duplicate data logs rather than
    aborting migrate."""
    from apex_habitat.habitat.utils.ledger_index import add_unique_guarded

    add_unique_guarded(
        "Accommodation Ledger",
        ["employee", "posting_date", "assignment", "building", "ledger_type"],
        constraint_name="unique_accl_daily_share",
    )
