"""Shared authorization boundary for worker and driver portal bearer tokens."""

from __future__ import annotations

import hashlib

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

WORKER = "Worker"
DRIVER = "Driver"
TOKEN_COOKIES = {WORKER: "masar_wt", DRIVER: "masar_dt"}

ISSUER_ROLES = {
    WORKER: {
        "System Manager",
        "Accommodation Manager",
        "HR User",
        "Resident Supervisor",
    },
    DRIVER: {
        "System Manager",
        "Fleet Manager",
        "Fleet Project Manager",
        "Fleet Supervisor",
    },
}

_UNSCOPED_ISSUER_ROLES = {
    WORKER: {"System Manager", "Accommodation Manager", "HR User"},
    DRIVER: {"System Manager", "Fleet Manager"},
}

_SUBJECT_DOCTYPES = {
    WORKER: "Employee",
    DRIVER: "Salis Driver",
}

_TOKEN_SUBJECT_FIELDS = {
    WORKER: "employee",
    DRIVER: "driver",
}

# Defense-in-depth: cap blind portal-token guessing at 10 failed attempts / 60s per
# IP. Only failed resolutions are charged (see _reject_invalid_token), so a valid
# link never counts and a legitimate holder is never blocked. 10/60s mirrors the
# app's tight tier (driver-portal writes) yet allows the odd revoked-link retry.
BAD_TOKEN_ATTEMPTS_PER_MINUTE = 10


@rate_limit(limit=BAD_TOKEN_ATTEMPTS_PER_MINUTE, seconds=60)
def _throttle_bad_token_attempt() -> None:
    """Charge one failed portal-token attempt against the per-IP window; the (N+1)th
    raises RateLimitExceededError (HTTP 429). No-op without a request (rate_limiter.py
    :134), so console/test callers are never throttled."""


def _require_audience(audience: str) -> None:
    if audience not in TOKEN_COOKIES:
        frappe.throw(
            _("Portal token audience must be Worker or Driver."),
            frappe.ValidationError,
        )


def hash_token(raw: str) -> str:
    """Return the SHA-256 digest persisted for a raw bearer token."""
    return hashlib.sha256((raw or "").encode("utf-8")).hexdigest()


def presented_token(audience: str, explicit=None) -> tuple[str, bool]:
    """Return the audience credential and whether the request presented one."""
    _require_audience(audience)
    explicit = (explicit or "").strip()
    if explicit:
        return explicit, True

    request = getattr(frappe.local, "request", None)
    if request is None:
        return "", False
    cookies = request.cookies
    cookie_name = TOKEN_COOKIES[audience]
    if cookie_name in cookies:
        return (cookies.get(cookie_name) or "").strip(), True
    return "", False


def validate_subject_binding(
    row,
    audience: str,
    *,
    exception=frappe.ValidationError,
) -> str:
    """Require one exact audience and one exclusive portal subject binding."""
    _require_audience(audience)
    if audience == WORKER:
        employee = row.get("employee")
        valid = (
            row.get("holder_type") == WORKER
            and row.get("party_type") == "Employee"
            and employee
            and row.get("party") == employee
            and not row.get("driver")
        )
        subject = employee
    else:
        driver = row.get("driver")
        valid = (
            row.get("holder_type") == DRIVER
            and driver
            and not row.get("employee")
            and not row.get("party")
            and not row.get("party_type")
        )
        subject = driver

    if not valid:
        frappe.throw(_("Portal token subject binding is invalid."), exception)
    return subject


def _reject_invalid_token() -> None:
    # Charge the per-IP throttle before failing closed, so a flood of guesses from
    # one IP is cut off (429) while a single bad link still returns the ordinary 403.
    _throttle_bad_token_attempt()
    frappe.throw(
        _("This portal access token is invalid or inactive."),
        frappe.PermissionError,
    )


def resolve_portal_subject(audience: str, token=None, required=False):
    """Resolve a valid audience token to its active Employee or Salis Driver."""
    _require_audience(audience)
    raw, was_presented = presented_token(audience, token)
    if not was_presented:
        if required:
            frappe.throw(_("A portal access token is required."), frappe.PermissionError)
        return None
    if not raw:
        _reject_invalid_token()

    row = frappe.db.get_value(
        "Masar Worker Token",
        {
            "token": hash_token(raw),
            "enabled": 1,
            "holder_type": audience,
        },
        [
            "holder_type",
            "party_type",
            "party",
            "employee",
            "driver",
            "expires_on",
        ],
        as_dict=True,
    )
    if not row:
        _reject_invalid_token()

    subject = validate_subject_binding(
        row,
        audience,
        exception=frappe.PermissionError,
    )
    try:
        expires_on = frappe.utils.get_datetime(row.get("expires_on"))
    except Exception:
        _reject_invalid_token()
    if not expires_on or expires_on <= frappe.utils.now_datetime():
        _reject_invalid_token()

    subject_doctype = _SUBJECT_DOCTYPES[audience]
    if frappe.db.get_value(subject_doctype, subject, "status") != "Active":
        _reject_invalid_token()
    return subject


def throttle_entry_token(audience: str, raw: str) -> None:
    """Route a link opened at a www entry (/masar?w=, /driver?d=) through the shared
    bad-token throttle before it is parked in the cookie. A valid link resolves and is
    never charged; a failed/unknown one is charged (see resolve_portal_subject). The
    403 is swallowed so every well-formed link still redirects to the clean URL (the
    secret always leaves the address bar); the (N+1)th bad link's 429 propagates."""
    _require_audience(audience)
    try:
        resolve_portal_subject(audience, raw, required=True)
    except frappe.PermissionError:
        pass


def _deny_issuance(audience: str) -> None:
    frappe.throw(
        _("You are not permitted to issue {0} portal credentials.").format(
            audience
        ),
        frappe.PermissionError,
    )


def _lock_subject_row(audience: str, subject: str, *, require_active=False):
    """Lock and return one portal subject row."""
    _require_audience(audience)
    if not subject:
        return None
    row = frappe.db.get_value(
        _SUBJECT_DOCTYPES[audience],
        subject,
        ["name", "status"],
        as_dict=True,
        for_update=True,
    )
    if require_active and (not row or row.status != "Active"):
        _deny_issuance(audience)
    return row


def _lock_subject_token_rows(audience: str, subject: str):
    """Lock exact-audience token rows in a stable order."""
    Token = frappe.qb.DocType("Masar Worker Token")
    subject_field = getattr(Token, _TOKEN_SUBJECT_FIELDS[audience])
    return (
        frappe.qb.from_(Token)
        .select(Token.name, Token.enabled)
        .where(
            (Token.holder_type == audience)
            & (subject_field == subject)
        )
        .orderby(Token.name)
        .for_update()
        .run(as_dict=True)
    )


def revoke_subject_tokens(audience: str, subject: str) -> int:
    """Disable enabled credentials for one exact audience and subject."""
    _require_audience(audience)
    if not subject or not _lock_subject_row(audience, subject):
        return 0

    disabled = 0
    for row in _lock_subject_token_rows(audience, subject):
        if not row.enabled:
            continue
        frappe.db.set_value(
            "Masar Worker Token",
            row.name,
            "enabled",
            0,
            update_modified=False,
        )
        disabled += 1
    return disabled


def on_employee_change(doc, method=None) -> int:
    """Revoke worker and linked-driver credentials for a non-active Employee."""
    if not doc.name or doc.status == "Active":
        return 0

    disabled = revoke_subject_tokens(WORKER, doc.name)
    drivers = frappe.get_all(
        "Salis Driver",
        filters={"employee": doc.name},
        pluck="name",
        order_by="name asc",
    )
    for driver in drivers:
        disabled += revoke_subject_tokens(DRIVER, driver)
    return disabled


def on_salis_driver_change(doc, method=None) -> int:
    """Revoke driver credentials whenever a driver is not Active."""
    if not doc.name or doc.status == "Active":
        return 0
    return revoke_subject_tokens(DRIVER, doc.name)


def on_driver_suspension_submit(doc, method=None) -> int:
    """Revoke credentials after Driver Suspension performs its raw status write."""
    return revoke_subject_tokens(DRIVER, getattr(doc, "driver", None))


def authorize_issuance(audience: str, subject: str, user=None) -> bool:
    """Authorize one issuer and subject, returning whether scope is restricted."""
    _require_audience(audience)
    user = user or frappe.session.user
    frappe.has_permission(
        "Masar Worker Token", "write", user=user, throw=True
    )

    subject_row = _lock_subject_row(audience, subject, require_active=True)
    if not subject_row:
        _deny_issuance(audience)
    _lock_subject_token_rows(audience, subject)

    if user == "Administrator":
        return False

    roles = set(frappe.get_roles(user))
    if not roles.intersection(ISSUER_ROLES[audience]):
        _deny_issuance(audience)
    if roles.intersection(_UNSCOPED_ISSUER_ROLES[audience]):
        return False

    if audience == WORKER and "Resident Supervisor" in roles:
        from apex.habitat import permissions

        allowed = set(permissions._allowed_buildings(user))
        assignments = frappe.get_all(
            "Housing Assignment",
            filters={
                "employee": subject,
                "docstatus": 1,
                "check_out_date": ["is", "not set"],
            },
            pluck="building",
        )
        buildings = {building for building in assignments if building}
        if buildings and buildings.issubset(allowed):
            return True
        frappe.throw(
            _("Worker credential issuance requires an allowed Building."),
            frappe.PermissionError,
        )

    if audience == DRIVER and roles.intersection(
        {"Fleet Project Manager", "Fleet Supervisor"}
    ):
        from apex.salis import permissions

        project = frappe.db.get_value("Salis Driver", subject, "project")
        if project and project in set(permissions._allowed_projects(user)):
            return True
        frappe.throw(
            _("Driver credential issuance requires an allowed Project."),
            frappe.PermissionError,
        )

    _deny_issuance(audience)


def credential_delivery_destination(
    audience: str,
    subject: str,
    requested=None,
) -> str | None:
    """Return the stored subject phone and reject a different caller value."""
    _require_audience(audience)
    from apex.salis.api.messaging_gateway import _normalize_phone

    fieldname = "cell_number" if audience == WORKER else "phone"
    stored = _normalize_phone(
        frappe.db.get_value(_SUBJECT_DOCTYPES[audience], subject, fieldname)
    )
    if requested is not None and _normalize_phone(requested) != stored:
        frappe.throw(
            _("The requested phone does not match the subject's stored phone."),
            frappe.PermissionError,
        )
    return stored
