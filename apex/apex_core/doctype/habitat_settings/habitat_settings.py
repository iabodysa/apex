# Copyright (c) 2026, afmcoltd
"""Habitat Settings controller.

Single DocType holding global integration toggles. All defaults are
conservative: no financial posting unless explicitly enabled.

Three concerns share this record because the framework's shape is one Settings
Single per module: the custody/notification toggles, the ``enable_gl_posting``
finance gate with the data-retention windows that govern how long machine-written
time-series records are kept, and the Payment Router configuration
(``target_payment_doctype``, ``auto_submit_target``, ``field_map``) that decides
which payment DocType the Pay action builds.
"""

from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe.utils import cint

from apex.apex_core.payment_router import (
    get_target_doctype,
    validate_field_map,
    validate_target_doctype,
)

RETENTION_DEFAULTS = {
    "snapshot_retention_days": 365,
    "depreciation_snapshot_retention_days": 730,
}

SETTINGS_DOCTYPE = "Habitat Settings"


class HabitatSettings(Document):
    def validate(self):
        """Refuse an unroutable payment configuration at config time, fail-closed.

        Both guards live in ``apex.apex_core.payment_router`` and are re-run there
        immediately before the insert, because this ``validate`` is skipped by
        ``db_set``, raw SQL and patches. Config-integrity only - nothing is posted
        or created here.
        """
        target = get_target_doctype(self)
        validate_target_doctype(target)
        validate_field_map(target, self.field_map or [])


def before_save(doc, method=None):
    """Stamp the editor's top role on the document.

    Who may write is the DocPerm's answer — System Manager alone holds write here — and
    repeating it in Python refuses the installer too, because the setup wizard writes
    these settings through ``ignore_permissions`` and a hand-written role check does not
    honour that flag.
    """
    roles = frappe.get_roles(frappe.session.user)
    doc.last_modified_by_role = roles[0] if roles else ""


def retention_days(key: str) -> int:
    """Return a retention window (days) for one of the retention fields, falling
    back to its built-in default when the stored value is blank or zero.
    Behaviour-neutral: each default equals the literal the call site used before
    this setting existed.

    Blank and zero are the same stored value here and both mean "unset": an Int
    field the operator never filled is written as ``0`` on the next save of this
    Single, and ``frappe.db.get_single_value`` casts a missing row to ``0`` too
    (``frappe/database/database.py:854``), so neither can be told from a typed
    zero. The field's own description states that contract; a zero window would
    otherwise purge every snapshot on the next daily cleanup."""
    if key not in RETENTION_DEFAULTS:
        raise KeyError(key)
    value = frappe.db.get_single_value(SETTINGS_DOCTYPE, key)
    return cint(value) if value else RETENTION_DEFAULTS[key]


def effective_retention_days(key: str, days: int | None = None) -> int:
    """Resolve the retention window a ``clear_old_logs`` cleanup should actually use.

    Frappe's ``Log Settings.clear_logs`` always invokes ``clear_old_logs(days=...)``
    with the Log Settings row value, which is seeded from the
    ``default_log_clearing_doctypes`` hook (the same literal as ``RETENTION_DEFAULTS``)
    the first time the DocType is registered. So the passed ``days`` is, in the
    untouched case, exactly the hook default; an operator who edits the Log Settings
    row passes a different value.

    Resolution, so the Habitat Settings field is the single source while a real Log
    Settings override still wins:

    * ``days is None`` (a direct or test call): use the Habitat Settings value.
    * ``days`` equals the built-in default (the untouched hook seed): use the Habitat
      Settings value, so changing the setting changes the cleanup window.
    * ``days`` differs from the built-in default (an explicit Log Settings edit):
      honour that operator override verbatim.
    """
    if key not in RETENTION_DEFAULTS:
        raise KeyError(key)
    if days is None or cint(days) == RETENTION_DEFAULTS[key]:
        return retention_days(key)
    return cint(days)
