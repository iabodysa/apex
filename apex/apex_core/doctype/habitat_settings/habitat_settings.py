# Copyright (c) 2026, afmcoltd
"""Habitat Settings controller.

Single DocType holding global integration toggles. All defaults are
conservative: no financial posting unless explicitly enabled.

Four concerns share this record because the framework's shape is one Settings
Single per module: the custody/notification toggles, the ``enable_gl_posting``
finance gate with the data-retention windows that govern how long machine-written
time-series records are kept, the Payment Router configuration
(``target_payment_doctype``, ``auto_submit_target``, ``field_map``) that decides
which payment DocType the Pay action builds, and the building-store engine's
policy — the negative-stock, period-freeze and backdating-window controls the
Accommodation Stock Ledger's write path enforces before any row lands.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, getdate, today

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

        Both payment-routing guards live in ``apex.apex_core.payment_router`` and are
        re-run there immediately before the insert, because this ``validate`` is
        skipped by ``db_set``, raw SQL and patches. Config-integrity only - nothing is
        posted or created here.
        """
        target = get_target_doctype(self)
        validate_target_doctype(target)
        validate_field_map(target, self.field_map or [])
        if self.backdating_role and not cint(self.backdating_days):
            frappe.msgprint(
                _("A backdating role has no effect while the window is zero days."),
                indicator="orange",
            )


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


def policy() -> dict:
    """The stock engine's settings as plain values, cached for the request.

    ``frappe.get_cached_doc`` (frappe/__init__.py:1183) is read rather than
    ``get_single_value`` per field, so a posting loop does not fetch the Single once
    per row. The values are returned as a plain dict because the one thing a cached
    Document cannot do is stay unchanged: a caller holding the document could write to
    it and mutate every other holder's copy in the same request.
    """
    doc = frappe.get_cached_doc(SETTINGS_DOCTYPE)
    return {
        "enabled": bool(cint(doc.enable_stock_engine)),
        "allow_negative": bool(cint(doc.allow_negative_stock)),
        "backdating_days": cint(doc.backdating_days),
        "backdating_role": doc.backdating_role,
        "frozen_upto": doc.stock_frozen_upto,
        "require_active_store": bool(cint(doc.require_active_store)),
    }


def validate_posting_allowed(building: str, posting_date=None) -> None:
    """Refuse a posting the policy does not allow, before any row is written.

    ``frappe.utils.add_days`` (frappe/utils/data.py:270) computes the backdating
    boundary; the one thing it cannot do is decide the window, which is a policy field
    the operator sets.

    Three refusals, in the order that tells the operator the most: the engine is off, the
    period is frozen, the date is further back than the window allows. The store check is
    last because it is the one a supervisor can fix themselves.
    """
    p = policy()
    if not p["enabled"]:
        frappe.throw(_("The stock engine is switched off in Habitat Settings."))

    date = getdate(posting_date or today())
    if date > getdate(today()):
        frappe.throw(_("A posting cannot be dated in the future."))

    if p["frozen_upto"] and date <= getdate(p["frozen_upto"]):
        frappe.throw(
            _("Stock is frozen up to {0}. Nothing can be posted on or before that date.").format(
                frappe.format(p["frozen_upto"], {"fieldtype": "Date"})
            )
        )

    earliest = frappe.utils.add_days(getdate(today()), -p["backdating_days"])
    if date < earliest and not _holds_role(p["backdating_role"]):
        frappe.throw(
            _("A posting cannot be dated before {0}. Ask a {1} to post it.").format(
                frappe.format(earliest, {"fieldtype": "Date"}),
                _(p["backdating_role"]) if p["backdating_role"] else _("System Manager"),
            )
        )
    if p["require_active_store"] and building and not store_is_open(building):
        frappe.throw(
            _("The store at {0} is closed, so nothing can be posted to it.").format(building)
        )


def _holds_role(role) -> bool:
    """True when the session holds ``role``, or System Manager, which outranks every gate.

    ``frappe.get_roles`` (frappe/permissions.py:497) returns every Role for
    Administrator, so the administrator passes without a special case. The one thing
    it cannot do is rank them: "System Manager outranks this gate" is a policy this
    app states, not something the framework's role list implies.
    """
    roles = frappe.get_roles(frappe.session.user)
    return "System Manager" in roles or (bool(role) and role in roles)


def store_is_open(building: str) -> bool:
    """True when this building's store accepts a posting.

    The store IS the Building. A separate store record was built and then refused: the
    building already carries ``is_procurement_store``, the ledger already denormalises
    company and cost centre from it, and one active store per building would have made a
    second entity 1:1 with the first — a table of attributes wearing an entity's name.
    """
    if not building:
        return False
    row = frappe.get_cached_value(
        "Building", building, ["is_procurement_store", "store_is_active"], as_dict=True
    )
    return bool(row and cint(row.is_procurement_store) and cint(row.store_is_active))
