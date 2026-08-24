# Copyright (c) 2026, afmcoltd

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
    request = getattr(frappe.local, "request", None)
    agent = (request.headers.get("User-Agent") if request else "") or ""
    return agent[:140] or _("Device")


def _refuse_enrolment(audience: str, subject: str | None) -> None:
    throttle_bad_token_attempt()
    log_portal_device_event(audience, subject, ENROLMENT_REFUSED, "Failed")
    frappe.throw(
        _("This enrolment key is invalid or has already been used."),
        frappe.PermissionError,
    )


def consume_enrolment_key(audience: str, raw_key: str, device_label: str | None = None) -> str | None:
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


def _live_device_name(audience: str, raw_token: str) -> str | None:
    if not raw_token or not frappe.db.table_exists("Portal Device"):
        return None
    return frappe.db.get_value(
        "Portal Device",
        {"device_hash": hash_token(raw_token), "holder_type": audience, "revoked": 0},
        "name",
    )


def onboarding_complete(audience: str, raw_token: str) -> bool:
    device = _live_device_name(audience, raw_token)
    if not device:
        return True
    return bool(frappe.db.get_value("Portal Device", device, "onboarded_on"))


def device_language(audience: str, raw_token: str) -> str | None:
    device = _live_device_name(audience, raw_token)
    return frappe.db.get_value("Portal Device", device, "language") if device else None


def set_device_language(audience: str, raw_token: str, language: str) -> bool:
    device = _live_device_name(audience, raw_token)
    if not device or not frappe.db.exists("Language", language):
        return False
    frappe.db.set_value("Portal Device", device, "language", language, update_modified=False)
    return True


def mark_onboarded(audience: str, raw_token: str) -> bool:
    device = _live_device_name(audience, raw_token)
    if not device or frappe.db.get_value("Portal Device", device, "onboarded_on"):
        return False
    frappe.db.set_value(
        "Portal Device", device, "onboarded_on", frappe.utils.now_datetime(), update_modified=False
    )
    return True
