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

import hashlib

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils.password import decrypt, encrypt

from apex.apex_core.utils.party_link import sync_party_employee

TOKEN_BYTES = 24  # [#9dvf8n]

# Driver access-token cookie (barcode entry at /driver?d=<raw>). Distinct from the
# worker cookie (masar_wt) so the two portals' credentials never cross-read; the
# holder_type filter in the resolver is the second, authoritative guard.
DRIVER_TOKEN_COOKIE = "masar_dt"

# [#9haukd]


def _hash_token(raw: str) -> str:
    """The at-rest form of a raw token: its SHA-256 hex digest (what ``token`` stores
    and what every resolver filters by)."""
    return hashlib.sha256((raw or "").encode("utf-8")).hexdigest()


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
    # [#ojkvw4]
    def _mint(self) -> str:
        raw = _new_token()
        self.token = _hash_token(raw)
        self.token_enc = encrypt(raw)
        self._plaintext_token = raw
        # [#ag7geg]
        self.expires_on = _token_expiry()
        self.last_generated_on = frappe.utils.now_datetime()
        self.last_generated_by = frappe.session.user
        return raw

    def recover_token(self) -> str:
        """Recover the raw token from its encrypted copy (to re-share the SAME link).
        Falls back to a rotation only when no usable ciphertext exists (a legacy row
        the P-104 migration has not reached, or a key mismatch)."""
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
        if self.holder_type == "Driver":
            if not self.driver:
                frappe.throw(_("A Salis Driver is required for a driver access token."))
            self.name = self.driver
        else:
            self.name = self.party

    # [#pewmoc]
    def before_validate(self):
        # A Driver token binds a Salis Driver, not a worker party — skip the whole
        # Employee/party sync + Temporary-Worker guard (those apply to workers only).
        if self.holder_type == "Driver":
            if not self.driver:
                frappe.throw(_("A Salis Driver is required for a driver access token."))
            return
        sync_party_employee(self, require_party=True)
        # [#c8p9h6]
        if self.party_type == "Temporary Worker":
            frappe.throw(
                _(
                    "A Masar worker link can only be issued to an Employee. "
                    "This worker is linked once their Iqama is issued and a permanent Employee record exists."
                )
            )

    def before_insert(self):
        # [#6ldmk7]
        if self.holder_type != "Driver":
            sync_party_employee(self)
        # [#n4hnje]
        self._mint()

    def regenerate(self):
        """Rotate the token (invalidates any previously shared link/QR). Returns the
        fresh RAW token — the only moment it is available in clear."""
        raw = self._mint()
        self.save()
        return raw

    def extend_expiry(self):
        """Push the expiry out by a fresh TTL window WITHOUT rotating the token.

        Show Link re-shares the SAME distributed link, so it must keep that link
        alive (a worker who is still active should never lose their link just because
        the window lapsed). Token + QR are unchanged; only ``expires_on`` advances."""
        self.expires_on = _token_expiry()
        self.last_generated_on = frappe.utils.now_datetime()
        self.last_generated_by = frappe.session.user
        self.save()
        return self.expires_on


def get_or_create_for_employee(employee: str) -> "MasarWorkerToken":
    """Return the worker's token row, creating one on first use."""
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


def worker_link_for_row(row) -> str | None:
    """Rebuild the shareable /masar link for a token row from its ENCRYPTED copy.

    The raw token is no longer stored in clear, so link re-display recovers it from
    ``token_enc`` (site-key protected). Returns None when the row has no usable
    ciphertext (disabled/legacy row) so a caller degrades gracefully rather than
    emitting a dead ``/masar?w=<hash>`` link. Read-only: never rotates."""
    enc = row.get("token_enc") if isinstance(row, dict) else getattr(row, "token_enc", None)
    if not enc:
        return None
    try:
        return _worker_link(_decrypt_token(enc))
    except Exception:
        return None


@frappe.whitelist(methods=["POST"])
def issue_worker_link(employee: str, regenerate: int = 0) -> dict:
    """Desk action: issue (or rotate) a worker's personal Masar link + QR.

    Permission-gated on write access to Masar Worker Token. Returns the link, the
    token, an SVG data-URI QR image (or None if QR rendering is unavailable), and
    the worker's phone (Employee.cell_number) so the caller can offer a WhatsApp
    share. No financial impact."""
    frappe.has_permission("Masar Worker Token", "write", throw=True)
    doc = get_or_create_for_employee(employee)
    # [#bqs6iz]
    raw = getattr(doc, "_plaintext_token", None)
    if raw is None:
        if frappe.utils.cint(regenerate) or not doc.token:
            # [#gl1eyq]
            raw = doc.regenerate()
        else:
            raw = doc.recover_token()
            # [#7k3u5f]
            doc.extend_expiry()

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
    out = []
    for emp in employees:
        doc = get_or_create_for_employee(emp)
        # [#t5zj54]
        raw = getattr(doc, "_plaintext_token", None)
        if raw is None:
            if not doc.token:
                raw = doc.regenerate()
            else:
                raw = doc.recover_token()
                # [#8kwg9b]
                doc.extend_expiry()
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


# ---------------------------------------------------------------------------
# Driver access tokens — passwordless barcode entry for a Salis Driver.
# Mirrors the worker issuance/resolution above; storage is identical (SHA-256
# hash + Fernet ciphertext only, never a raw token at rest). Drivers have NO
# Frappe User (full cutover): the token IS the identity, resolved server-side.
# ---------------------------------------------------------------------------


def _driver_link(token: str) -> str:
    """The shareable personal driver-portal URL for a RAW token."""
    return f"{frappe.utils.get_url()}/driver?d={token}"


def get_or_create_for_driver(driver: str) -> "MasarWorkerToken":
    """Return the driver's token row (holder_type=Driver), creating one on first use."""
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


@frappe.whitelist(methods=["POST"])
def issue_driver_link(driver: str, regenerate: int = 0) -> dict:
    """Desk action: issue (or rotate) a driver's personal barcode link + QR.

    Permission-gated on write access to Masar Worker Token (same gate as the worker
    action). Returns the link, the RAW token (shown ONCE), an SVG data-URI QR, the
    expiry, and the driver's phone for a WhatsApp share. The raw token is never
    stored or logged — only its hash + Fernet ciphertext persist. No financial impact."""
    frappe.has_permission("Masar Worker Token", "write", throw=True)
    doc = get_or_create_for_driver(driver)
    # [#bqs6iz] mirror worker: reuse the just-minted plaintext, else rotate/recover.
    raw = getattr(doc, "_plaintext_token", None)
    if raw is None:
        if frappe.utils.cint(regenerate) or not doc.token:
            raw = doc.regenerate()
        else:
            raw = doc.recover_token()
            doc.extend_expiry()

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
    out = []
    for drv in drivers:
        doc = get_or_create_for_driver(drv)
        raw = getattr(doc, "_plaintext_token", None)
        if raw is None:
            if not doc.token:
                raw = doc.regenerate()
            else:
                raw = doc.recover_token()
                doc.extend_expiry()
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


def _driver_token_from_request(token=None) -> str:
    """The driver token for this call: the explicit arg if given, else the httpOnly
    ``masar_dt`` cookie. Returns '' when neither is present (resolver fails closed)."""
    token = (token or "").strip()
    if token:
        return token
    request = getattr(frappe.local, "request", None)
    if request is not None:
        try:
            return (request.cookies.get(DRIVER_TOKEN_COOKIE) or "").strip()
        except Exception:
            return ""
    return ""


def resolve_driver_token(token=None):
    """Resolve a driver access token (cookie or explicit arg) to its Salis Driver, or None.

    The driver equivalent of ``masar._resolve_worker``: hashes the presented token and
    matches it against an ENABLED, non-expired Driver-holder row. The ``holder_type ==
    Driver`` filter means a worker token can never resolve a driver (cross-type
    isolation). Soft (returns None, no throw) so the shared ``get_driver_for_user``
    stays soft; the hard 403 is applied by ``_resolve_driver`` when this returns None."""
    token = _driver_token_from_request(token)
    if not token:
        return None
    row = frappe.db.get_value(
        "Masar Worker Token",
        {"token": _hash_token(token), "enabled": 1, "holder_type": "Driver"},
        ["driver", "expires_on"],
        as_dict=True,
    )
    if not row or not row.get("driver"):
        return None
    # Expired barcode refuses (mirrors the worker expiry gate).
    if row.get("expires_on") and frappe.utils.now_datetime() > frappe.utils.get_datetime(
        row["expires_on"]
    ):
        return None
    return row["driver"]


def revoke_driver_tokens(driver: str) -> int:
    """Disable every enabled Driver-holder token for ``driver`` (auto-revoke on
    clearance/off-boarding). Reversible (enabled flag only, hash+ciphertext kept) and
    idempotent — a re-run finds nothing enabled and is a no-op. Returns how many were
    disabled."""
    if not driver:
        return 0
    names = frappe.get_all(
        "Masar Worker Token",
        filters={"driver": driver, "holder_type": "Driver", "enabled": 1},
        pluck="name",
    )
    for name in names:
        frappe.db.set_value("Masar Worker Token", name, "enabled", 0)
    return len(names)


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
