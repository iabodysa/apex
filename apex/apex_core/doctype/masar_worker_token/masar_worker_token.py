# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import hmac
import io
from base64 import b64encode

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils.password import decrypt, encrypt

from apex.apex_core.utils.portal_identity import (
    DRIVER,
    ISSUED,
    REISSUED,
    RESHARED,
    ROTATED,
    WORKER,
    authorize_issuance,
    authorize_revocation,
    hash_token,
    log_credential_event,
    revoke_subject_tokens,
    validate_subject_binding,
)
from apex.apex_core.utils.party_link import sync_party_employee
from apex.salis.api.web_push import disable_subject_subscriptions

TOKEN_BYTES = 24
SUBJECT_BINDING_FIELDS = (
    "holder_type",
    "party_type",
    "party",
    "employee",
    "driver",
)
_CREDENTIAL_REISSUE_GUARD = object()


TOKEN_TTL_DAYS = 180


def _new_token() -> str:
    for _attempt in range(8):
        candidate = frappe.generate_hash(length=TOKEN_BYTES * 2)
        if not frappe.db.exists("Masar Worker Token", {"token": hash_token(candidate)}):
            return candidate
    frappe.throw(_("Could not generate a unique worker token. Please try again."))


class MasarWorkerToken(Document):

    def _issuance_subject(self) -> tuple[str, str | None]:
        audience = DRIVER if self.holder_type == DRIVER else WORKER
        return audience, self.driver if audience == DRIVER else self.employee

    def _set_defaults(self):
        worker_binding = (
            self.get("party_type"),
            self.get("party"),
            self.get("employee"),
        )
        super()._set_defaults()
        if self.holder_type == DRIVER and not any(worker_binding):
            self.party_type, self.party, self.employee = worker_binding

    def _sync_autoname_field(self):
        if self.holder_type == DRIVER:
            return
        super()._sync_autoname_field()

    def _reject_temporary_worker(self) -> None:
        if self.party_type == "Temporary Worker":
            frappe.throw(
                _(
                    "A Masar worker link can only be issued to an Employee. "
                    "This worker is linked once their Iqama is issued and a permanent Employee record exists."
                )
            )

    def _validate_subject_binding_immutability(self) -> None:
        if self.is_new():
            return
        persisted = frappe.db.get_value(
            self.doctype,
            self.name,
            SUBJECT_BINDING_FIELDS,
            as_dict=True,
        )
        if not persisted:
            return
        if any(
            (persisted.get(fieldname) or None)
            != (self.get(fieldname) or None)
            for fieldname in SUBJECT_BINDING_FIELDS
        ):
            frappe.throw(
                _("Portal token subject binding cannot be changed after issuance."),
                frappe.ValidationError,
            )

    def _validate_disabled_credential_reactivation(self) -> None:
        reissue_guard = getattr(self, "_credential_reissue_guard", None)
        if hasattr(self, "_credential_reissue_guard"):
            del self._credential_reissue_guard
        if self.is_new() or not self.enabled:
            return

        persisted = frappe.db.get_value(
            self.doctype,
            self.name,
            ["enabled", "token", "token_enc"],
            as_dict=True,
            for_update=True,
        )
        if not persisted or persisted.enabled:
            return

        pending = getattr(self, "_pending_token_fields", None) or {}
        rotated = reissue_guard is _CREDENTIAL_REISSUE_GUARD and all(
            pending.get(fieldname)
            and not hmac.compare_digest(
                frappe.utils.cstr(pending.get(fieldname)),
                frappe.utils.cstr(persisted.get(fieldname)),
            )
            for fieldname in ("token", "token_enc")
        )
        if rotated:
            try:
                raw = decrypt(pending["token_enc"])
            except Exception:
                rotated = False
            else:
                rotated = hmac.compare_digest(
                    pending["token"], hash_token(raw)
                )
        if not rotated:
            frappe.throw(_("Not permitted"), frappe.PermissionError)

    def _mint(self) -> str:
        audience, subject = self._issuance_subject()
        authorize_issuance(audience, subject)
        if not self.is_new() and frappe.db.table_exists("Portal Push Subscription"):
            disable_subject_subscriptions(audience, subject)
        raw = _new_token()
        self.token = hash_token(raw)
        self.token_enc = encrypt(raw)
        self.consumed_on = None
        self._pending_token_fields = {
            "token": self.token,
            "token_enc": self.token_enc,
            "consumed_on": None,
        }
        self._credential_reissue_guard = _CREDENTIAL_REISSUE_GUARD
        self._plaintext_token = raw
        self.expires_on = frappe.utils.add_to_date(frappe.utils.now_datetime(), days=TOKEN_TTL_DAYS)
        self.last_generated_on = frappe.utils.now_datetime()
        self.last_generated_by = frappe.session.user
        return raw

    def _persist_pending_token_fields(self) -> None:
        pending = getattr(self, "_pending_token_fields", None)
        if not pending:
            return
        audience, subject = self._issuance_subject()
        authorize_issuance(audience, subject)
        frappe.db.set_value(
            self.doctype,
            self.name,
            pending,
            update_modified=False,
        )
        self.token = pending["token"]
        self.token_enc = pending["token_enc"]
        del self._pending_token_fields
        if hasattr(self, "_credential_reissue_guard"):
            del self._credential_reissue_guard

    def recover_token(self) -> str:
        audience, subject = self._issuance_subject()
        if authorize_issuance(audience, subject):
            return self.regenerate()
        if self.token_enc:
            try:
                return decrypt(self.token_enc)
            except Exception:
                pass
        return self.regenerate()

    def autoname(self):
        if self.holder_type == DRIVER:
            if not self.driver:
                frappe.throw(_("A Salis Driver is required for a driver access token."))
            self.name = self.driver
        else:
            self.name = self.party

    def before_validate(self):
        self._validate_subject_binding_immutability()
        if self.holder_type == DRIVER:
            if not self.driver:
                frappe.throw(_("A Salis Driver is required for a driver access token."))
            validate_subject_binding(self, DRIVER)
            authorize_issuance(DRIVER, self.driver)
            self._validate_disabled_credential_reactivation()
            return
        sync_party_employee(self, require_party=True)
        self._reject_temporary_worker()
        validate_subject_binding(self, WORKER)
        authorize_issuance(WORKER, self.employee)
        self._validate_disabled_credential_reactivation()

    def before_change(self):
        if self.is_new() or not self.enabled:
            return
        audience, subject = self._issuance_subject()
        authorize_issuance(audience, subject)
        self._validate_disabled_credential_reactivation()

    def _get_missing_mandatory_fields(self):
        missing = super()._get_missing_mandatory_fields()
        if self.holder_type == DRIVER:
            return [item for item in missing if item[0] != "party_type"]
        return missing

    def before_insert(self):
        if self.holder_type != DRIVER:
            sync_party_employee(self)
            self._reject_temporary_worker()
        self._mint()

    def after_insert(self):
        self._persist_pending_token_fields()

    def regenerate(self):
        audience, subject = self._issuance_subject()
        authorize_issuance(audience, subject)
        raw = self._mint()
        self.save()
        self._persist_pending_token_fields()
        return raw

    def extend_expiry(self):
        audience, subject = self._issuance_subject()
        authorize_issuance(audience, subject)
        self.expires_on = frappe.utils.add_to_date(frappe.utils.now_datetime(), days=TOKEN_TTL_DAYS)
        self.last_generated_on = frappe.utils.now_datetime()
        self.last_generated_by = frappe.session.user
        self.save()
        return self.expires_on


def get_or_create_for_employee(employee: str) -> "MasarWorkerToken":
    authorize_issuance(WORKER, employee)
    if not frappe.db.exists("Employee", employee):
        frappe.throw(_("Employee {0} does not exist.").format(employee))
    name = frappe.db.get_value("Masar Worker Token", {"employee": employee}, "name")
    if name:
        return frappe.get_doc("Masar Worker Token", name)
    doc = frappe.get_doc({"doctype": "Masar Worker Token", "employee": employee})
    doc.insert()
    return doc


def reshare_worker_link(employee: str) -> str | None:
    scoped_issuer = authorize_issuance(WORKER, employee)
    name = frappe.db.get_value(
        "Masar Worker Token",
        {
            "holder_type": WORKER,
            "employee": employee,
            "enabled": 1,
        },
        "name",
    )
    if not name:
        return None

    doc = frappe.get_doc("Masar Worker Token", name)
    validate_subject_binding(
        doc, WORKER, exception=frappe.PermissionError
    )
    raw = doc.recover_token()
    if not scoped_issuer:
        doc.extend_expiry()
    return f"{frappe.utils.get_url()}/masar?w={raw}"


@frappe.whitelist(methods=["POST"])
def issue_worker_link(employee: str, regenerate: int = 0) -> dict:
    frappe.has_permission("Masar Worker Token", "write", throw=True)
    scoped_issuer = authorize_issuance(WORKER, employee)
    doc = get_or_create_for_employee(employee)
    raw = _issue_token(doc, regenerate, scoped_issuer)

    link = f"{frappe.utils.get_url()}/masar?w={raw}"
    return {
        "employee": doc.employee,
        "employee_name": doc.employee_name,
        "enabled": bool(doc.enabled),
        "token": raw,
        "link": link,
        "qr": masar_qr_data_uri(link),
        "expires_on": frappe.utils.cstr(doc.expires_on) if doc.expires_on else None,
        "phone": frappe.db.get_value("Employee", doc.employee, "cell_number"),
    }


@frappe.whitelist(methods=["POST"])
def batch_issue_worker_links(employees_json) -> list:
    frappe.has_permission("Masar Worker Token", "write", throw=True)
    employees = frappe.parse_json(employees_json) or []
    scoped_issuers = {
        emp: authorize_issuance(WORKER, emp) for emp in employees
    }
    out = []
    for emp in employees:
        doc = get_or_create_for_employee(emp)
        raw = _issue_token(doc, scoped_issuer=scoped_issuers[emp])
        link = f"{frappe.utils.get_url()}/masar?w={raw}"
        out.append(
            {
                "employee": doc.employee,
                "employee_name": doc.employee_name,
                "link": link,
                "qr": masar_qr_data_uri(link),
            }
        )
    emp_ids = [r["employee"] for r in out if r.get("employee")]
    phones = dict(
        frappe.get_all(
            "Employee",
            filters={"name": ["in", emp_ids]},
            fields=["name", "cell_number"],
            as_list=True,
        )
    ) if emp_ids else {}
    for r in out:
        r["phone"] = phones.get(r["employee"])
    return out


_ELEVATED_DRIVER_USER_ROLES = {
    "System Manager",
    "Fleet Manager",
    "Fleet Project Manager",
    "Fleet Supervisor",
    "Finance Manager",
    "HR User",
    "HR Manager",
    "Accommodation Manager",
}


def _issue_token(
    doc: "MasarWorkerToken", regenerate: int = 0, scoped_issuer: bool = False
) -> str:
    audience, subject = doc._issuance_subject()
    raw = getattr(doc, "_plaintext_token", None)
    if not doc.enabled:
        doc.enabled = 1
        action, raw = REISSUED, doc.regenerate()
    elif raw is not None:
        action = ISSUED
    elif scoped_issuer or frappe.utils.cint(regenerate) or not doc.token:
        action, raw = ROTATED, doc.regenerate()
    else:
        previous = doc.token
        raw = doc.recover_token()
        doc.extend_expiry()
        action = RESHARED if doc.token == previous else ROTATED
    log_credential_event(audience, subject, action, doc.name)
    return raw


def get_or_create_for_driver(driver: str) -> "MasarWorkerToken":
    authorize_issuance(DRIVER, driver)
    if not frappe.db.exists("Salis Driver", driver):
        frappe.throw(_("Salis Driver {0} does not exist.").format(driver))
    name = frappe.db.get_value(
        "Masar Worker Token", {"driver": driver, "holder_type": "Driver"}, "name"
    )
    if name:
        return frappe.get_doc("Masar Worker Token", name)
    doc = frappe.get_doc(
        {"doctype": "Masar Worker Token", "holder_type": "Driver", "driver": driver}
    )
    doc.insert()
    return doc


def _disable_legacy_driver_user(driver: str) -> bool:
    if not driver:
        return False
    token = frappe.db.get_value(
        "Masar Worker Token",
        {"driver": driver, "holder_type": "Driver", "enabled": 1},
        ["token", "expires_on"],
        as_dict=True,
    )
    if not token or not token.token:
        return False
    if token.expires_on and frappe.utils.now_datetime() > frappe.utils.get_datetime(
        token.expires_on
    ):
        return False

    user = frappe.db.get_value("Salis Driver", driver, "driver_user")
    if not user or user in ("Administrator", "Guest"):
        return False
    info = frappe.db.get_value("User", user, ["enabled", "user_type"], as_dict=True)
    if not info or not info.enabled or info.user_type != "Website User":
        return False
    if set(frappe.get_roles(user)) & _ELEVATED_DRIVER_USER_ROLES:
        return False

    user_doc = frappe.get_doc("User", user)
    user_doc.enabled = 0
    user_doc.save(ignore_permissions=True)
    return True


@frappe.whitelist(methods=["POST"])
def issue_driver_link(driver: str, regenerate: int = 0) -> dict:
    frappe.has_permission("Masar Worker Token", "write", throw=True)
    scoped_issuer = authorize_issuance(DRIVER, driver)
    doc = get_or_create_for_driver(driver)
    raw = _issue_token(doc, regenerate, scoped_issuer)
    _disable_legacy_driver_user(driver)

    link = f"{frappe.utils.get_url()}/driver?d={raw}"
    return {
        "driver": doc.driver,
        "driver_name": frappe.db.get_value("Salis Driver", doc.driver, "full_name"),
        "enabled": bool(doc.enabled),
        "token": raw,
        "link": link,
        "qr": masar_qr_data_uri(link),
        "expires_on": frappe.utils.cstr(doc.expires_on) if doc.expires_on else None,
        "phone": frappe.db.get_value("Salis Driver", doc.driver, "phone"),
    }


@frappe.whitelist(methods=["POST"])
def batch_issue_driver_links(drivers_json) -> list:
    frappe.has_permission("Masar Worker Token", "write", throw=True)
    drivers = frappe.parse_json(drivers_json) or []
    scoped_issuers = {
        drv: authorize_issuance(DRIVER, drv) for drv in drivers
    }
    out = []
    for drv in drivers:
        doc = get_or_create_for_driver(drv)
        raw = _issue_token(doc, scoped_issuer=scoped_issuers[drv])
        _disable_legacy_driver_user(drv)
        link = f"{frappe.utils.get_url()}/driver?d={raw}"
        out.append(
            {
                "driver": doc.driver,
                "driver_name": frappe.db.get_value("Salis Driver", doc.driver, "full_name"),
                "link": link,
                "qr": masar_qr_data_uri(link),
            }
        )
    driver_ids = [r["driver"] for r in out if r.get("driver")]
    phones = dict(
        frappe.get_list(
            "Salis Driver",
            filters={"name": ["in", driver_ids]},
            fields=["name", "phone"],
            as_list=True,
            limit_page_length=0,
        )
    ) if driver_ids else {}
    for r in out:
        r["phone"] = phones.get(r["driver"])
    return out


@frappe.whitelist(methods=["POST"])
def revoke_driver_link(driver: str) -> dict:
    frappe.has_permission("Masar Worker Token", "write", throw=True)
    authorize_revocation(DRIVER, driver)
    revoked = revoke_subject_tokens(DRIVER, driver)
    return {
        "driver": driver,
        "driver_name": frappe.db.get_value("Salis Driver", driver, "full_name"),
        "revoked": revoked,
        "enabled": False,
    }


def on_driver_clearance_submit(doc, method=None):
    revoke_subject_tokens(DRIVER, getattr(doc, "driver", None))


def masar_qr_data_uri(text: str):
    try:
        import pyqrcode

        q = pyqrcode.create(text)
        buf = io.BytesIO()
        q.svg(buf, scale=4)
        return "data:image/svg+xml;base64," + b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        return None


def doc_verify_qr(doctype: str, name: str):
    if not (doctype and name):
        return None
    return masar_qr_data_uri(
        frappe.utils.get_url(f"/app/{frappe.scrub(doctype).replace('_', '-')}/{name}")
    )
