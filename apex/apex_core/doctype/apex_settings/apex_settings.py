# Copyright (c) 2026, AFMCO and contributors
"""Apex Settings controller.

App-wide configuration shared by every Apex module (Habitat and Salis). Holds
settings that are not scoped to a single domain: the ``enable_gl_posting`` finance
gate and the data-retention windows (``snapshot_retention_days``,
``depreciation_snapshot_retention_days``) that govern how long machine-written
time-series records are kept before the daily log cleanup purges old rows.
"""

from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe.utils import cint

RETENTION_DEFAULTS = {
    "snapshot_retention_days": 365,
    "depreciation_snapshot_retention_days": 730,
}


class ApexSettings(Document):
    pass


def retention_days(key: str) -> int:
    """Return a retention window (days) for one of the Apex Settings retention
    fields, falling back to its built-in default when the stored value is blank or
    zero. Behaviour-neutral: each default equals the literal the call site used
    before this setting existed."""
    if key not in RETENTION_DEFAULTS:
        raise KeyError(key)
    value = frappe.db.get_single_value("Apex Settings", key)
    return cint(value) if value else RETENTION_DEFAULTS[key]


def effective_retention_days(key: str, days: int | None = None) -> int:
    """Resolve the retention window a ``clear_old_logs`` cleanup should actually use.

    Frappe's ``Log Settings.clear_logs`` always invokes ``clear_old_logs(days=...)``
    with the Log Settings row value, which is seeded from the
    ``default_log_clearing_doctypes`` hook (the same literal as ``RETENTION_DEFAULTS``)
    the first time the DocType is registered. So the passed ``days`` is, in the
    untouched case, exactly the hook default; an operator who edits the Log Settings
    row passes a different value.

    Resolution, so the Apex Settings field is the single source while a real Log
    Settings override still wins:

    * ``days is None`` (a direct or test call): use the Apex Settings value.
    * ``days`` equals the built-in default (the untouched hook seed): use the Apex
      Settings value, so changing the setting changes the cleanup window.
    * ``days`` differs from the built-in default (an explicit Log Settings edit):
      honour that operator override verbatim.
    """
    if key not in RETENTION_DEFAULTS:
        raise KeyError(key)
    if days is None or cint(days) == RETENTION_DEFAULTS[key]:
        return retention_days(key)
    return cint(days)


def gl_posting_enabled() -> bool:
    """Single source of truth for the ``enable_gl_posting`` finance gate.

    Read via ``frappe.db.get_single_value`` (no full-doc load) so every caller -
    the Payment Router, the housing ledger, a report - reads the flag the same
    way. When this is falsy (the factory default), financial side effects stay
    OFF: the housing ledger keeps writing operational memos and the Payment
    Router routes the payment record without driving a GL-posting submit.
    """
    return bool(cint(frappe.db.get_single_value("Apex Settings", "enable_gl_posting")))
