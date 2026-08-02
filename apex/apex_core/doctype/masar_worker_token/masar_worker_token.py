"""Masar Worker Token — personal access link for the worker self-service app.

Each row binds ONE Employee to an unguessable random ``token``. The worker opens
their personal URL ``/masar?w=<token>`` (or scans the matching QR); the Masar
worker endpoints resolve that token server-side back to this single Employee and
scope every query to them. The client never supplies an Employee id, so one
token can only ever surface its own worker's data.

Why a dedicated link DocType (not Custom Fields on Employee): adding fields to
the standard HRMS Employee needs a Custom Field fixture + hooks wiring and
clutters the HR form. A small purpose-built record is auto-discovered by Frappe,
owns its own desk action (generate / regenerate + QR), keeps the access token
off the Employee master, and makes token-scoping a single indexed lookup.

No financial impact: this is identity/issuance metadata only.
"""

from __future__ import annotations

import hmac

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils.password import decrypt, encrypt

from apex.apex_core.utils.portal_token_security import (
    DRIVER,
    ISSUED,
    REISSUED,
    RESHARED,
    ROTATED,
    WORKER,
    TOKEN_COOKIES,
    authorize_issuance,
    authorize_revocation,
    hash_token,
    log_credential_event,
    revoke_subject_tokens,
    resolve_portal_subject,
    validate_subject_binding,
)
from apex.apex_core.utils.party_link import sync_party_employee

TOKEN_BYTES = 24  # [#9dvf8n]
SUBJECT_BINDING_FIELDS = (
    "holder_type",
    "party_type",
    "party",
    "employee",
    "driver",
)
_CREDENTIAL_REISSUE_GUARD = object()

# Driver access-token cookie (barcode entry at /driver?d=<raw>). Distinct from the
# worker cookie (masar_wt) so the two portals' credentials never cross-read; the
# holder_type filter in the resolver is the second, authoritative guard.
DRIVER_TOKEN_COOKIE = TOKEN_COOKIES[DRIVER]

# [#9haukd]


def _hash_token(raw: str) -> str:
    """The at-rest form of a raw token: its SHA-256 hex digest (what ``token`` stores
    and what every resolver filters by)."""
    return hash_token(raw)


def _decrypt_token(token_enc: str) -> str:
    """Recover the raw token from its stored Fernet ciphertext (site-key protected)."""
    return decrypt(token_enc)

# [#7khxj6]
TOKEN_TTL_DAYS = 180


def _token_expiry():
    """The expiry stamp for a freshly issued/extended link: now + the TTL window."""
    return frappe.utils.add_to_date(frappe.utils.now_datetime(), days=TOKEN_TTL_DAYS)


def _new_token() -> str:
    """A fresh url-safe random raw token, whose HASH is unique across the doctype."""
    for _attempt in range(8):
        candidate = frappe.generate_hash(length=TOKEN_BYTES * 2)
        # [#9at93o]
        if not frappe.db.exists("Masar Worker Token", {"token": _hash_token(candidate)}):
            return candidate
    # [#s3grro]
    frappe.throw(_("Could not generate a unique worker token. Please try again."))


class MasarWorkerToken(Document):
    def _issuance_subject(self) -> tuple[str, str | None]:
        audience = DRIVER if self.holder_type == DRIVER else WORKER
        return audience, self.driver if audience == DRIVER else self.employee

    def _set_defaults(self):
        """Discard legacy Worker defaults only from exact new Driver rows."""
        worker_binding = (
            self.get("party_type"),
            self.get("party"),
            self.get("employee"),
        )
        super()._set_defaults()
        if self.holder_type == DRIVER and not any(worker_binding):
            self.party_type, self.party, self.employee = worker_binding

    def _sync_autoname_field(self):
        """Keep legacy field-based naming from populating Driver.party."""
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
        """Prevent an issued credential from being reassigned to another subject."""
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
        """Allow disabled-to-enabled only after server-side credential rotation."""
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
                raw = _decrypt_token(pending["token_enc"])
            except Exception:
                rotated = False
            else:
                rotated = hmac.compare_digest(
                    pending["token"], _hash_token(raw)
                )
        if not rotated:
            frappe.throw(_("Not permitted"), frappe.PermissionError)

    # [#ojkvw4]
    def _mint(self) -> str:
        audience, subject = self._issuance_subject()
        authorize_issuance(audience, subject)
        raw = _new_token()
        self.token = _hash_token(raw)
        self.token_enc = encrypt(raw)
        self._pending_token_fields = {
            "token": self.token,
            "token_enc": self.token_enc,
        }
        self._credential_reissue_guard = _CREDENTIAL_REISSUE_GUARD
        self._plaintext_token = raw
        # [#ag7geg]
        self.expires_on = _token_expiry()
        self.last_generated_on = frappe.utils.now_datetime()
        self.last_generated_by = frappe.session.user
        return raw

    def _persist_pending_token_fields(self) -> None:
        """Persist only the generated permlevel-1 fields after issuer policy."""
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
        """Recover the raw token from its encrypted copy (to re-share the SAME link).
        Falls back to a rotation only when no usable ciphertext exists (a legacy row
        the hashing migration has not reached, or a key mismatch)."""
        audience, subject = self._issuance_subject()
        if authorize_issuance(audience, subject):
            return self.regenerate()
        if self.token_enc:
            try:
                return _decrypt_token(self.token_enc)
            except Exception:
                pass
        return self.regenerate()

    def autoname(self):
        # Controller autoname overrides the meta field:party rule (which cannot name a
        # driver row — a driver has no party). Name a Driver token by its Salis Driver,
        # a Worker token by its party (Employee), exactly as before for workers.
        if self.holder_type == DRIVER:
            if not self.driver:
                frappe.throw(_("A Salis Driver is required for a driver access token."))
            self.name = self.driver
        else:
            self.name = self.party

    # [#pewmoc]
    def before_validate(self):
        self._validate_subject_binding_immutability()
        # A Driver token binds a Salis Driver, not a worker party — skip the whole
        # Employee/party sync + Temporary-Worker guard (those apply to workers only).
        if self.holder_type == DRIVER:
            if not self.driver:
                frappe.throw(_("A Salis Driver is required for a driver access token."))
            validate_subject_binding(self, DRIVER)
            authorize_issuance(DRIVER, self.driver)
            self._validate_disabled_credential_reactivation()
            return
        sync_party_employee(self, require_party=True)
        # [#c8p9h6]
        self._reject_temporary_worker()
        validate_subject_binding(self, WORKER)
        authorize_issuance(WORKER, self.employee)
        self._validate_disabled_credential_reactivation()

    def before_change(self):
        """Recheck locked database state before Document.db_set updates."""
        if self.is_new() or not self.enabled:
            return
        audience, subject = self._issuance_subject()
        authorize_issuance(audience, subject)
        self._validate_disabled_credential_reactivation()

    def _get_missing_mandatory_fields(self):
        """Exclude only the Worker-specific party type from Driver validation."""
        missing = super()._get_missing_mandatory_fields()
        if self.holder_type == DRIVER:
            return [item for item in missing if item[0] != "party_type"]
        return missing

    def before_insert(self):
        # [#6ldmk7]
        if self.holder_type != DRIVER:
            sync_party_employee(self)
            self._reject_temporary_worker()
        # [#n4hnje]
        self._mint()

    def after_insert(self):
        self._persist_pending_token_fields()

    def regenerate(self):
        """Rotate the token (invalidates any previously shared link/QR). Returns the
        fresh RAW token — the only moment it is available in clear."""
        audience, subject = self._issuance_subject()
        authorize_issuance(audience, subject)
        raw = self._mint()
        self.save()
        self._persist_pending_token_fields()
        return raw

    def extend_expiry(self):
        """Push the expiry out by a fresh TTL window WITHOUT rotating the token.

        Show Link re-shares the SAME distributed link, so it must keep that link
        alive (a worker who is still active should never lose their link just because
        the window lapsed). Token + QR are unchanged; only ``expires_on`` advances."""
        audience, subject = self._issuance_subject()
        authorize_issuance(audience, subject)
        self.expires_on = _token_expiry()
        self.last_generated_on = frappe.utils.now_datetime()
        self.last_generated_by = frappe.session.user
        self.save()
        return self.expires_on


def get_or_create_for_employee(employee: str) -> "MasarWorkerToken":
    """Return the worker's token row, creating one on first use."""
    authorize_issuance(WORKER, employee)
    if not frappe.db.exists("Employee", employee):
        frappe.throw(_("Employee {0} does not exist.").format(employee))
    name = frappe.db.get_value("Masar Worker Token", {"employee": employee}, "name")
    if name:
        return frappe.get_doc("Masar Worker Token", name)
    doc = frappe.get_doc({"doctype": "Masar Worker Token", "employee": employee})
    doc.insert()
    return doc


def _worker_link(token: str) -> str:
    """The shareable personal Masar URL for a RAW token."""
    return f"{frappe.utils.get_url()}/masar?w={token}"


def reshare_worker_link(employee: str) -> str | None:
    """Return a policy-authorized Worker link, rotating scoped re-shares.

    PERMLEVEL IS NEVER CONSULTED ON THIS PATH, so it protects the stored record and
    not the credential: every issuer role -- Accommodation Manager, HR User, Resident
    Supervisor -- still obtains the RAW token here, because ``recover_token`` decrypts
    ``token_enc`` (or mints a fresh one) and it is returned inside the link. The only
    gate is ``authorize_issuance``, which checks role and project/building scope alone.
    That is deliberate: re-sharing a link means handing over the credential. Withdrawing
    a role's permlevel-1 row stops it reading the hash and ciphertext OFF THE RECORD and
    nothing more -- see ``test_masar_worker_token_credential_permlevel``.
    """
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
    return _worker_link(raw)


@frappe.whitelist(methods=["POST"])
def issue_worker_link(employee: str, regenerate: int = 0) -> dict:
    """Desk action: issue (or rotate) a worker's personal Masar link + QR.

    Permission-gated on write access to Masar Worker Token. Returns the link, the
    token, an SVG data-URI QR image (or None if QR rendering is unavailable), and
    the worker's phone (Employee.cell_number) so the caller can offer a WhatsApp
    share. No financial impact."""
    frappe.has_permission("Masar Worker Token", "write", throw=True)
    scoped_issuer = authorize_issuance(WORKER, employee)
    doc = get_or_create_for_employee(employee)
    # [#bqs6iz]
    raw = _issue_token(doc, regenerate, scoped_issuer)

    link = _worker_link(raw)
    return {
        "employee": doc.employee,
        "employee_name": doc.employee_name,
        "enabled": bool(doc.enabled),
        # [#cqj0cx]
        "token": raw,
        "link": link,
        "qr": masar_qr_data_uri(link),
        "expires_on": frappe.utils.cstr(doc.expires_on) if doc.expires_on else None,
        # [#p7spkl]
        "phone": frappe.db.get_value("Employee", doc.employee, "cell_number"),
    }


@frappe.whitelist(methods=["POST"])
def batch_issue_worker_links(employees_json) -> list:
    """Issue (or fetch) the Masar link + QR for several Employees in ONE call — the
    Arrivals Desk group-QR action. Same per-worker behaviour as issue_worker_link
    (mints a token when missing), permission-checked once. Returns one row per
    Employee: ``{employee, employee_name, link, qr, phone}``."""
    frappe.has_permission("Masar Worker Token", "write", throw=True)
    employees = frappe.parse_json(employees_json) or []
    scoped_issuers = {
        emp: authorize_issuance(WORKER, emp) for emp in employees
    }
    out = []
    for emp in employees:
        doc = get_or_create_for_employee(emp)
        raw = _issue_token(doc, scoped_issuer=scoped_issuers[emp])
        link = _worker_link(raw)
        out.append(
            {
                "employee": doc.employee,
                "employee_name": doc.employee_name,
                "link": link,
                "qr": masar_qr_data_uri(link),
            }
        )
    # [#n3vua5]
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


def _driver_link(token: str) -> str:
    """The shareable personal driver-portal URL for a RAW token."""
    return f"{frappe.utils.get_url()}/driver?d={token}"


def _issue_token(
    doc: "MasarWorkerToken", regenerate: int = 0, scoped_issuer: bool = False
) -> str:
    """Issue or rotate a token for any holder (worker or driver): the logic is
    holder-agnostic, keyed only off the MasarWorkerToken doc.

    [#a267ai] Every worker and driver desk issuance funnels through here, so the one
    audit write lives here too — naming the branch actually taken, because "re-shared
    the same link" and "rotated, invalidating the old QR" are different events for
    anyone later reconstructing who held a live credential when."""
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
        # recover_token falls back to a rotation for a legacy row with no usable
        # ciphertext, so the hash decides the label rather than the intent.
        previous = doc.token
        raw = doc.recover_token()
        doc.extend_expiry()
        action = RESHARED if doc.token == previous else ROTATED
    log_credential_event(audience, subject, action, doc.name)
    return raw


def get_or_create_for_driver(driver: str) -> "MasarWorkerToken":
    """Return the driver's token row (holder_type=Driver), creating one on first use."""
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
    """Disable a legacy Website User only after the driver's barcode is live.

    System users and Website Users with elevated operational roles stay enabled.
    The operation is reversible and idempotent; it never deletes an account.
    """
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

    frappe.db.set_value("User", user, "enabled", 0, update_modified=False)
    return True


@frappe.whitelist(methods=["POST"])
def issue_driver_link(driver: str, regenerate: int = 0) -> dict:
    """Desk action: issue (or rotate) a driver's personal barcode link + QR.

    Permission-gated on write access to Masar Worker Token (same gate as the worker
    action). Returns the link, the RAW token (shown ONCE), an SVG data-URI QR, the
    expiry, and the driver's phone for a WhatsApp share. The raw token is never
    stored or logged — only its hash + Fernet ciphertext persist. No financial impact."""
    frappe.has_permission("Masar Worker Token", "write", throw=True)
    scoped_issuer = authorize_issuance(DRIVER, driver)
    doc = get_or_create_for_driver(driver)
    raw = _issue_token(doc, regenerate, scoped_issuer)
    _disable_legacy_driver_user(driver)

    link = _driver_link(raw)
    return {
        "driver": doc.driver,
        "driver_name": frappe.db.get_value("Salis Driver", doc.driver, "full_name"),
        "enabled": bool(doc.enabled),
        # [#cqj0cx] the ONE moment the raw token is returned; never persisted/logged.
        "token": raw,
        "link": link,
        "qr": masar_qr_data_uri(link),
        "expires_on": frappe.utils.cstr(doc.expires_on) if doc.expires_on else None,
        "phone": frappe.db.get_value("Salis Driver", doc.driver, "phone"),
    }


@frappe.whitelist(methods=["POST"])
def batch_issue_driver_links(drivers_json) -> list:
    """Issue (or fetch) the barcode link + QR for several Salis Drivers in ONE call.

    Same per-driver behaviour as issue_driver_link (mints a token when missing),
    permission-checked once. Returns one row per driver: ``{driver, driver_name,
    link, qr, phone}``. Raw tokens appear only in the returned payload, never logged."""
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
        link = _driver_link(raw)
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
        frappe.get_all(
            "Salis Driver",
            filters={"name": ["in", driver_ids]},
            fields=["name", "phone"],
            as_list=True,
        )
    ) if driver_ids else {}
    for r in out:
        r["phone"] = phones.get(r["driver"])
    return out


@frappe.whitelist(methods=["POST"])
def revoke_driver_link(driver: str) -> dict:
    """Desk action: kill a driver's barcode link now, without waiting for clearance.

    The automatic revocations (clearance submit, suspension, a non-Active status) each
    need an event to happen first. A lost phone, a shared QR or a driver who walked off
    site is not one of those events, so without this the only way to withdraw a live
    passwordless credential from the desk was to ROTATE it — which mints a NEW working
    link rather than leaving none. Rotation is the wrong tool for withdrawal.

    Authorized by ``authorize_revocation``: the same fleet roles and the same project
    scope as issuance, minus the still-Active requirement (see that function). Returns
    how many enabled rows were disabled — 0 is the honest answer for a driver who had
    no live link, not a failure. The revocation itself is audit-logged inside
    ``revoke_subject_tokens``, so every path lands one row. No financial impact."""
    frappe.has_permission("Masar Worker Token", "write", throw=True)
    authorize_revocation(DRIVER, driver)
    revoked = revoke_driver_tokens(driver)
    return {
        "driver": driver,
        "driver_name": frappe.db.get_value("Salis Driver", driver, "full_name"),
        "revoked": revoked,
        "enabled": False,
    }


def resolve_driver_token(token=None):
    """Resolve an optional Driver credential to its exact active Salis Driver.

    A missing credential returns None so desk preview may fall back to its session.
    Any presented invalid credential raises PermissionError and blocks fallback.
    """
    return resolve_portal_subject(DRIVER, token)


def revoke_driver_tokens(driver: str) -> int:
    """Disable every enabled Driver-holder token for ``driver`` (auto-revoke on
    clearance/off-boarding). Idempotent — a re-run finds nothing enabled and is a
    no-op. Explicit reissue rotates the retained row before enabling it. Returns how
    many were disabled."""
    return revoke_subject_tokens(DRIVER, driver)


def on_driver_clearance_submit(doc, method=None):
    """doc_events hook (Driver Clearance on_submit): auto-revoke the driver's barcode on
    exit clearance. A submitted clearance is the exit event, so the passwordless bearer
    credential is disabled the moment the driver is cleared out. Fail-safe: revoking is
    the safe direction; re-issue a fresh QR from the desk if a clearance is cancelled."""
    revoke_driver_tokens(getattr(doc, "driver", None))


def masar_qr_data_uri(text: str):
    """Render ``text`` as a base64 SVG data-URI QR, or None if unavailable.

    Uses ``pyqrcode`` (bundled with Frappe — ``frappe.twofactor`` relies on it;
    the ``qrcode`` package is NOT installed on the bench). pyqrcode emits a crisp,
    tiny vector SVG that scales cleanly on screen and in print. Kept defensive so a
    missing optional dependency degrades to a plain link rather than erroring the
    desk action."""
    try:
        import io
        from base64 import b64encode

        import pyqrcode  # [#9xz9bo]

        q = pyqrcode.create(text)
        buf = io.BytesIO()
        q.svg(buf, scale=4)
        return "data:image/svg+xml;base64," + b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        return None
