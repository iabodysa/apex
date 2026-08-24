# Copyright (c) 2026, afmcoltd
"""Portal Device — one row per device a worker or driver has enrolled through a
one-time Masar Worker Token key.

The QR a supervisor issues (``masar_worker_token.issue_worker_link`` /
``issue_driver_link``) is unchanged; what changes is what scanning it MEANS.
:func:`consume_enrolment_key` treats the presented Masar Worker Token as a
single-use enrolment key rather than a standing bearer: it mints a fresh,
device-only secret, stores that secret's hash here, and marks the token row
``consumed_on`` so a second scan of the same key is refused. The minted secret is
what ``apex/www/masar.py``/``apex/www/driver.py`` would cookie going forward —
``portal_identity.resolve_portal_subject`` already accepts it via
``_resolve_portal_device`` — so every existing portal endpoint recognises a
device-enrolled holder with no change of its own.

Why a separate DocType and not more fields on Masar Worker Token: that row's
``autoname`` sets ``name`` to the driver or employee itself, which is a one-row-
per-subject constraint at the PRIMARY KEY, not only the ``unique`` flags on
``employee``/``driver`` — dropping those flags alone would still collide on
``name`` for a second device. Several out-of-scope callers
(``apex/habitat/api/front_desk.py``, ``apex/habitat/api/arrivals_desk.py``) also
read that single row with ``frappe.db.get_value(..., {"party_type":...,"party":...})``,
which is only correct while at most one row exists per subject. Adding a device
DIMENSION next to the subject's single standing key — rather than multiplying that
key — leaves every one of those reads correct unchanged.

``track_changes`` stays 0 for the same reason it stays 0 on Masar Worker Token
(see that DocType's own controller docstring): ``device_hash`` is a Data field, and
``Version.get_diff`` would otherwise copy a device's hash history into a Version
row a System Manager can read.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from apex.apex_core.utils.portal_identity import (
    DEVICE_EVICTED,
    DEVICE_REVOKED,
    DRIVER,
    ENROLLED,
    ENROLMENT_REFUSED,
    MAX_DEVICES_PER_SUBJECT,
    WORKER,
    as_capacity,
    hash_token,
    log_portal_device_event,
    throttle_bad_token_attempt,
    validate_subject_binding,
)

_SUBJECT_DOCTYPE = {WORKER: "Employee", DRIVER: "Salis Driver"}

_IMMUTABLE_FIELDS = (
    "holder_type",
    "employee",
    "driver",
    "device_hash",
    "enrolled_on",
    "enrolled_by",
    "enrolment_source",
)


class PortalDevice(Document):
    """Controller for one enrolled worker or driver device."""

    def validate(self):
        if self.holder_type == WORKER:
            if not self.employee or self.driver:
                frappe.throw(_("A worker device requires exactly one employee."))
        elif self.holder_type == DRIVER:
            if not self.driver or self.employee:
                frappe.throw(_("A driver device requires exactly one driver."))
        else:
            frappe.throw(_("Portal device holder type must be Worker or Driver."))
        self._validate_immutable_fields()
        self._apply_revocation_rules()

    def on_update(self):
        """Fires the audit log staged by :func:`_apply_revocation_rules`, after
        ``Document.save`` has already committed the row -- the desk supervisor's
        revoke-by-save is the only revoking writer that reaches this controller at
        all (the other three go through ``frappe.db.set_value`` and log
        themselves), so this is also the only place that needs to.
        """
        if not getattr(self, "_pending_revocation_log", False):
            return
        self._pending_revocation_log = False
        subject = self.employee if self.holder_type == WORKER else self.driver
        log_portal_device_event(
            self.holder_type,
            subject,
            DEVICE_REVOKED,
            "Linked",
            device_name=self.name,
            ignore_permissions=False,
        )

    def _validate_immutable_fields(self) -> None:
        """Blocks any change to the fields only :func:`consume_enrolment_key` may set."""
        if self.is_new():
            return
        persisted = frappe.db.get_value(self.doctype, self.name, _IMMUTABLE_FIELDS, as_dict=True)
        if not persisted:
            return
        if any(
            (persisted.get(fieldname) or None) != (self.get(fieldname) or None)
            for fieldname in _IMMUTABLE_FIELDS
        ):
            frappe.throw(
                _("A Portal Device's identity cannot be changed after enrolment."),
                frappe.ValidationError,
            )

    def _apply_revocation_rules(self) -> None:
        """React to a ``revoked`` transition on a desk SAVE -- the only writer that
        reaches this controller at all (the other three revoking writers go
        through ``frappe.db.set_value`` and already stamp and log themselves: see
        :func:`apex.apex_core.utils.portal_identity.revoke_subject_devices`,
        :func:`revoke_own_device` below and ``_evict_oldest_if_over_cap`` below).

        1 -> 0 is blocked outright: the field's own description is the contract
        ("Never cleared -- a returning device enrols afresh with a new key"). 0 ->
        1 stamps ``revoked_on`` when the caller left it blank and queues the audit
        log for :meth:`on_update` -- by the time ``validate`` runs, ``Document.save``
        has already confined this SAVE to the acting supervisor's own project or
        building (``portal_device_has_permission``'s ``write`` gate).
        """
        self._pending_revocation_log = False
        if self.is_new():
            return
        persisted = frappe.db.get_value(self.doctype, self.name, "revoked")
        if persisted and not self.revoked:
            frappe.throw(
                _("A revoked Portal Device cannot be un-revoked."),
                frappe.ValidationError,
            )
        if self.revoked and not persisted:
            if not self.revoked_on:
                self.revoked_on = frappe.utils.now_datetime()
            self._pending_revocation_log = True


def _default_label() -> str:
    """A short, non-identifying default device label from the request's user agent."""
    request = getattr(frappe.local, "request", None)
    agent = (request.headers.get("User-Agent") if request else "") or ""
    return agent[:140] or _("Device")


def _refuse_enrolment(audience: str, subject: str | None) -> None:
    """Throttles, logs the refusal with status Failed, and raises -- as loud as a success."""
    throttle_bad_token_attempt()
    log_portal_device_event(audience, subject, ENROLMENT_REFUSED, "Failed")
    frappe.throw(
        _("This enrolment key is invalid or has already been used."),
        frappe.PermissionError,
    )


def consume_enrolment_key(audience: str, raw_key: str, device_label: str | None = None) -> str | None:
    """One-time enrolment: resolve an unconsumed Masar Worker Token key, mint a
    fresh device bearer secret, insert the Portal Device row, and mark the key
    consumed — all in ONE transaction, the token row locked before the verdict so
    two concurrent scans of the SAME key cannot both succeed.

    Returns the RAW device secret on success (the only moment it exists in
    clear — the caller cookies it exactly as ``portal_identity.set_token_cookie``
    already does for a Masar Worker Token). A refusal never returns; it throws
    through :func:`_refuse_enrolment`, which never receives the raw key either.
    """
    raw_key = (raw_key or "").strip()
    if not raw_key:
        _refuse_enrolment(audience, None)

    key_hash = hash_token(raw_key)
    row = frappe.db.get_value(
        "Masar Worker Token",
        {"token": key_hash, "holder_type": audience},
        [
            "name",
            "holder_type",
            "enabled",
            "consumed_on",
            "expires_on",
            "employee",
            "driver",
            "party_type",
            "party",
            "last_generated_by",
        ],
        as_dict=True,
        for_update=True,
    )
    if not row or not row.enabled or row.consumed_on:
        known_subject = row.get("driver" if audience == DRIVER else "employee") if row else None
        _refuse_enrolment(audience, known_subject)

    try:
        expires_on = frappe.utils.get_datetime(row.get("expires_on"))
    except Exception:
        expires_on = None
    if not expires_on or expires_on <= frappe.utils.now_datetime():
        _refuse_enrolment(audience, None)

    subject = validate_subject_binding(row, audience, exception=frappe.PermissionError)
    if frappe.db.get_value(_SUBJECT_DOCTYPE[audience], subject, "status") != "Active":
        _refuse_enrolment(audience, subject)

    frappe.db.set_value(
        "Masar Worker Token", row.name, "consumed_on", frappe.utils.now_datetime(), update_modified=False
    )

    raw_device = frappe.generate_hash(length=48)
    device = frappe.get_doc(
        {
            "doctype": "Portal Device",
            "holder_type": audience,
            "employee": subject if audience == WORKER else None,
            "driver": subject if audience == DRIVER else None,
            "device_label": (device_label or _default_label())[:140],
            "enrolled_on": frappe.utils.now_datetime(),
            "enrolled_by": row.get("last_generated_by"),
            "enrolment_source": row.name,
            "last_seen_on": frappe.utils.now_datetime(),
        }
    )
    with as_capacity(audience, subject=subject):
        device.insert()

    frappe.db.set_value(
        "Portal Device", device.name, "device_hash", hash_token(raw_device), update_modified=False
    )

    log_portal_device_event(audience, subject, ENROLLED, "Linked", device_name=device.name)
    _evict_oldest_if_over_cap(audience, subject, keep_name=device.name)
    return raw_device


def _evict_oldest_if_over_cap(audience: str, subject: str, keep_name: str) -> str | None:
    """Evict the oldest un-revoked device once a subject holds more than
    ``portal_identity.MAX_DEVICES_PER_SUBJECT`` — see that constant's own
    docstring for why it stands in for ``User.simultaneous_sessions``. The evicted
    row is REVOKED, not deleted, so it stays in the holder's device list beside the
    surviving one.
    """
    field = "employee" if audience == WORKER else "driver"
    cap = MAX_DEVICES_PER_SUBJECT[audience]
    Device = frappe.qb.DocType("Portal Device")
    rows = (
        frappe.qb.from_(Device)
        .select(Device.name)
        .where(
            (Device.holder_type == audience)
            & (getattr(Device, field) == subject)
            & (Device.revoked == 0)
        )
        .orderby(Device.enrolled_on)
        .for_update()
        .run(as_dict=True)
    )
    if len(rows) <= cap:
        return None
    candidates = [row.name for row in rows if row.name != keep_name]
    if not candidates:
        return None
    oldest = candidates[0]
    frappe.db.set_value(
        "Portal Device", oldest, {"revoked": 1, "revoked_on": frappe.utils.now_datetime()}, update_modified=False
    )
    log_portal_device_event(audience, subject, DEVICE_EVICTED, "Linked", device_name=oldest)
    return oldest


def list_devices_for(audience: str, subject: str) -> list:
    """Every device row belonging to one already-authenticated subject, revoked or
    not — the holder must see an evicted or self-revoked row too, not only the
    survivors.

    Reads via ``frappe.get_list`` — genuinely permission-checked, unlike
    ``frappe.get_all``, which sets ``ignore_permissions=True`` unconditionally
    (frappe/__init__.py:2050) — run as the audience's capacity user so the read
    carries real DocPerm (``read: 1`` on ``Portal Worker Capacity`` /
    ``Portal Driver Capacity``) rather than none at all. Scoping to exactly this
    ``subject`` — never another holder's rows — comes from
    ``portal_device_scope_query``'s own capacity branch
    (``permission_query_conditions``, registered in ``hooks.py``), which reads
    back the SAME ``subject`` :func:`apex.apex_core.utils.portal_identity.
    as_capacity` bound for this call; ``filters`` here is redundant with it by
    design, not a second, competing scope.
    """
    field = "employee" if audience == WORKER else "driver"
    with as_capacity(audience, subject=subject):
        return frappe.get_list(
            "Portal Device",
            filters={"holder_type": audience, field: subject},
            fields=["name", "device_label", "enrolled_on", "last_seen_on", "revoked", "revoked_on"],
            order_by="enrolled_on desc",
            limit_page_length=0,
        )


def revoke_own_device(audience: str, subject: str, device_name: str) -> bool:
    """Revoke exactly one of the CALLING holder's own devices. ``subject`` is the
    caller's own token-resolved identity; the row's ``employee``/``driver`` must
    match it or the call is refused as not-found — one holder can never revoke
    another's device even by guessing a name.
    """
    field = "employee" if audience == WORKER else "driver"
    row = frappe.db.get_value(
        "Portal Device",
        device_name,
        ["name", "holder_type", field, "revoked"],
        as_dict=True,
        for_update=True,
    )
    if not row or row.holder_type != audience or row.get(field) != subject:
        frappe.throw(_("Portal device not found."), frappe.DoesNotExistError)
    if row.revoked:
        return False
    frappe.db.set_value(
        "Portal Device", device_name, {"revoked": 1, "revoked_on": frappe.utils.now_datetime()}, update_modified=False
    )
    log_portal_device_event(audience, subject, DEVICE_REVOKED, "Linked", device_name=device_name)
    return True
