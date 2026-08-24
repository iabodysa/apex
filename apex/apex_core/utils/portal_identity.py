# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import hashlib
from contextlib import contextmanager

import frappe
from frappe import _

from apex.apex_core.utils.phone import normalize_phone
from apex.apex_core.utils.rate_window import charge_window

WORKER = "Worker"
DRIVER = "Driver"
TOKEN_COOKIES = {WORKER: "masar_wt", DRIVER: "masar_dt"}

CAPACITY_USERS = {WORKER: "worker@apex.internal", DRIVER: "driver@apex.internal"}

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

BAD_TOKEN_ATTEMPTS_PER_MINUTE = 10
BAD_TOKEN_WINDOW_SECONDS = 60

BAD_TOKEN_WINDOW_KEY = "rl:apex-portal-bad-token:{0}"

def throttle_bad_token_attempt() -> None:
    if not getattr(frappe.local, "request", None):
        return
    ip = getattr(frappe.local, "request_ip", None)
    if not ip:
        return

    charge_window(
        BAD_TOKEN_WINDOW_KEY.format(ip),
        BAD_TOKEN_WINDOW_SECONDS,
        BAD_TOKEN_ATTEMPTS_PER_MINUTE,
    )

def _require_audience(audience: str) -> None:
    if audience not in TOKEN_COOKIES:
        frappe.throw(
            _("Portal token audience must be Worker or Driver."),
            frappe.ValidationError,
        )

def hash_token(raw: str) -> str:
    return hashlib.sha256((raw or "").encode("utf-8")).hexdigest()

PORTAL_ROOM_PREFIX = "apex-portal-"

def portal_room(audience: str, token=None) -> str:
    _require_audience(audience)
    raw, was_presented = presented_token(audience, token)
    if not was_presented or not raw:
        return ""
    return PORTAL_ROOM_PREFIX + hash_token(raw)

def portal_rooms_for_subject(audience: str, subject: str) -> list:
    _require_audience(audience)
    if not subject:
        return []
    field = "driver" if audience == DRIVER else "employee"
    hashes = frappe.get_all(
        "Masar Worker Token",
        filters={"holder_type": audience, "enabled": 1, field: subject},
        pluck="token",
    )
    return [PORTAL_ROOM_PREFIX + h for h in hashes if h]

def publish_to_portal_subject(audience: str, subject: str, event: str, message=None) -> int:
    rooms = portal_rooms_for_subject(audience, subject)
    for room in rooms:
        frappe.publish_realtime(event, message or {}, room=room, after_commit=True)
    return len(rooms)

def presented_token(audience: str, explicit=None) -> tuple[str, bool]:
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

def set_token_cookie(audience: str, token: str, max_age_seconds: int) -> None:
    _require_audience(audience)
    cm = getattr(frappe.local, "cookie_manager", None)
    if cm is None:
        return
    cm.set_cookie(
        TOKEN_COOKIES[audience],
        token,
        httponly=True,
        samesite="Lax",
        max_age=max_age_seconds,
    )

def delete_token_cookie(audience: str) -> None:
    _require_audience(audience)
    cm = getattr(frappe.local, "cookie_manager", None)
    if cm is not None:
        cm.delete_cookie(TOKEN_COOKIES[audience])

def validate_subject_binding(
    row,
    audience: str,
    *,
    exception=frappe.ValidationError,
) -> str:
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
    throttle_bad_token_attempt()
    frappe.throw(
        _("This portal access token is invalid or inactive."),
        frappe.PermissionError,
    )

@contextmanager
def as_capacity(audience: str, subject: str | None = None):
    _require_audience(audience)
    user = CAPACITY_USERS[audience]
    previous = frappe.session.user
    previous_subject = getattr(frappe.local, "apex_capacity_subject", None)
    frappe.set_user(user)
    frappe.local.apex_capacity_subject = (audience, subject) if subject else None
    try:
        yield user
    finally:
        frappe.set_user(previous)
        frappe.local.apex_capacity_subject = previous_subject

def capacity_subject(audience: str) -> str | None:
    _require_audience(audience)
    current = getattr(frappe.local, "apex_capacity_subject", None)
    if not current:
        return None
    bound_audience, subject = current
    return subject if bound_audience == audience else None

def resolve_portal_subject(audience: str, token=None, required=False):
    _require_audience(audience)
    raw, was_presented = presented_token(audience, token)
    if not was_presented:
        if required:
            frappe.throw(_("A portal access token is required."), frappe.PermissionError)
        return None
    if not raw:
        _reject_invalid_token()

    key_hash = hash_token(raw)
    row = frappe.db.get_value(
        "Masar Worker Token",
        {
            "token": key_hash,
            "enabled": 1,
            "holder_type": audience,
            "consumed_on": ["is", "not set"],
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
    if row:
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

    device_subject = _resolve_portal_device(audience, key_hash)
    if device_subject:
        return device_subject
    _reject_invalid_token()


def _resolve_portal_device(audience: str, key_hash: str) -> str | None:
    if not frappe.db.table_exists("Portal Device"):
        return None
    field = "employee" if audience == WORKER else "driver"
    row = frappe.db.get_value(
        "Portal Device",
        {"device_hash": key_hash, "holder_type": audience, "revoked": 0},
        ["name", field],
        as_dict=True,
    )
    if not row:
        return None
    subject = row.get(field)
    if not subject:
        return None
    if frappe.db.get_value(_SUBJECT_DOCTYPES[audience], subject, "status") != "Active":
        return None
    frappe.db.set_value(
        "Portal Device", row.name, "last_seen_on", frappe.utils.now_datetime(), update_modified=False
    )
    return subject

def _lock_subject_row(audience: str, subject: str, *, require_active=False):
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
        frappe.throw(
            _("You are not permitted to issue {0} portal credentials.").format(audience),
            frappe.PermissionError,
        )
    return row

def _lock_subject_token_rows(audience: str, subject: str):
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

ISSUED = "Issued"
REISSUED = "Reissued"
RESHARED = "Re-shared"
ROTATED = "Rotated"
REVOKED = "Revoked"

ENROLLED = "Enrolled"
ENROLMENT_REFUSED = "Enrolment Refused"
DEVICE_REVOKED = "Device Revoked"
DEVICE_EVICTED = "Device Evicted"

MAX_DEVICES_PER_SUBJECT = {WORKER: 3, DRIVER: 1}
"""How many un-revoked Portal Device rows one subject may hold before the oldest is
evicted -- this app's stand-in for ``User.simultaneous_sessions``
(frappe/sessions.py:66-79), which is read only inside a real login
(``Session.start``, frappe/sessions.py:212-247) that a worker or driver capacity
never makes (see ``portal_identity_seed.py``'s own DECISION note, and
``authenticate_for_2factor``/``LoginManager.authenticate``, neither of which this
app's Guest-token flow ever reaches). A per-``User Type`` default -- the spec's own
open decision -- needs one ``User`` per holder to hang a ``User Type`` off of,
which A-521.1 already refused; a flat per-audience constant is the nearest native
equivalent this architecture can actually carry."""

def _credential_event_subject(action: str, audience: str, subject: str) -> str:
    return {
        ISSUED: _("Portal credential issued for {0} {1}"),
        REISSUED: _("Portal credential reissued for {0} {1}"),
        RESHARED: _("Portal credential re-shared for {0} {1}"),
        ROTATED: _("Portal credential rotated for {0} {1}"),
        REVOKED: _("Portal credential revoked for {0} {1}"),
    }[action].format(_(audience), subject)

def log_credential_event(
    audience: str,
    subject: str,
    action: str,
    token_name=None,
    user=None,
) -> str | None:
    _require_audience(audience)
    if not subject:
        return None
    return frappe.get_doc(
        {
            "doctype": "Activity Log",
            "user": user or frappe.session.user,
            "subject": _credential_event_subject(action, audience, subject),
            "reference_doctype": "Masar Worker Token",
            "reference_name": token_name,
            "link_doctype": _SUBJECT_DOCTYPES[audience],
            "link_name": subject,
        }
    ).insert(ignore_links=True).name

def _portal_device_event_subject(action: str, audience: str, subject: str | None) -> str:
    return {
        ENROLLED: _("Portal device enrolled for {0} {1}"),
        ENROLMENT_REFUSED: _("Portal device enrolment refused for {0} {1}"),
        DEVICE_REVOKED: _("Portal device revoked for {0} {1}"),
        DEVICE_EVICTED: _("Portal device evicted for {0} {1}"),
    }[action].format(_(audience), subject or _("unknown"))


def log_portal_device_event(
    audience: str,
    subject: str | None,
    action: str,
    status: str,
    device_name: str | None = None,
    user=None,
    ignore_permissions: bool = True,
) -> str | None:
    _require_audience(audience)
    payload = {
        "doctype": "Activity Log",
        "user": user or frappe.session.user,
        "status": status,
        "subject": _portal_device_event_subject(action, audience, subject),
    }
    if subject:
        payload["link_doctype"] = _SUBJECT_DOCTYPES[audience]
        payload["link_name"] = subject
    if device_name and status != "Failed":
        payload["reference_doctype"] = "Portal Device"
        payload["reference_name"] = device_name
    return frappe.get_doc(payload).insert(ignore_permissions=ignore_permissions, ignore_links=True).name


def revoke_subject_devices(audience: str, subject: str) -> int:
    _require_audience(audience)
    if not subject or not frappe.db.table_exists("Portal Device"):
        return 0
    field = "employee" if audience == WORKER else "driver"
    Device = frappe.qb.DocType("Portal Device")
    rows = (
        frappe.qb.from_(Device)
        .select(Device.name)
        .where(
            (Device.holder_type == audience)
            & (getattr(Device, field) == subject)
            & (Device.revoked == 0)
        )
        .orderby(Device.name)
        .for_update()
        .run(as_dict=True)
    )
    revoked = 0
    for row in rows:
        frappe.db.set_value(
            "Portal Device",
            row.name,
            {"revoked": 1, "revoked_on": frappe.utils.now_datetime()},
            update_modified=False,
        )
        log_portal_device_event(audience, subject, DEVICE_REVOKED, "Linked", device_name=row.name)
        revoked += 1
    return revoked


def revoke_subject_tokens(audience: str, subject: str) -> int:
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
        log_credential_event(audience, subject, REVOKED, row.name)
        disabled += 1
    if frappe.db.table_exists("Portal Push Subscription"):
        from apex.salis.api.web_push import disable_subject_subscriptions

        disable_subject_subscriptions(audience, subject)
    revoke_subject_devices(audience, subject)
    return disabled

_CAPACITY_DESK_ROLES = {
    WORKER: (WORKER, "Portal Worker Capacity"),
    DRIVER: (DRIVER, "Portal Driver Capacity"),
}

def close_capacity_desk_access(audience: str) -> None:
    _require_audience(audience)
    for role in _CAPACITY_DESK_ROLES[audience]:
        if frappe.db.get_value("Role", role, "desk_access"):
            role_doc = frappe.get_doc("Role", role)
            role_doc.desk_access = 0
            role_doc.save(ignore_permissions=True)

def close_all_capacity_desk_access() -> None:
    for audience in _CAPACITY_DESK_ROLES:
        close_capacity_desk_access(audience)

def on_employee_change(doc, method=None) -> int:
    close_capacity_desk_access(WORKER)
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
    close_capacity_desk_access(DRIVER)
    if not doc.name or doc.status == "Active":
        return 0
    return revoke_subject_tokens(DRIVER, doc.name)

def on_driver_suspension_submit(doc, method=None) -> int:
    return revoke_subject_tokens(DRIVER, getattr(doc, "driver", None))

def authorize_issuance(
    audience: str,
    subject: str,
    user=None,
    *,
    require_active: bool = True,
) -> bool:
    _require_audience(audience)
    user = user or frappe.session.user
    frappe.has_permission(
        "Masar Worker Token", "write", user=user, throw=True
    )

    subject_row = _lock_subject_row(audience, subject, require_active=require_active)
    if not subject_row:
        frappe.throw(
            _("You are not permitted to issue {0} portal credentials.").format(audience),
            frappe.PermissionError,
        )
    _lock_subject_token_rows(audience, subject)

    if user == "Administrator":
        return False

    roles = set(frappe.get_roles(user))
    if not roles.intersection(ISSUER_ROLES[audience]):
        frappe.throw(
            _("You are not permitted to issue {0} portal credentials.").format(audience),
            frappe.PermissionError,
        )
    if roles.intersection(_UNSCOPED_ISSUER_ROLES[audience]):
        return False

    if audience == WORKER and "Resident Supervisor" in roles:
        from apex.habitat import permissions

        allowed = set(permissions.allowed_buildings(user))
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
        if project and project in set(permissions.allowed_projects(user)):
            return True
        frappe.throw(
            _("Driver credential issuance requires an allowed Project."),
            frappe.PermissionError,
        )

    frappe.throw(
        _("You are not permitted to issue {0} portal credentials.").format(audience),
        frappe.PermissionError,
    )

def authorize_revocation(audience: str, subject: str, user=None) -> bool:
    return authorize_issuance(audience, subject, user, require_active=False)

def _audience_scope_clause(audience: str, user: str, roles: set) -> str:
    if roles.intersection(_UNSCOPED_ISSUER_ROLES[audience]):
        return "`holder_type` = '{0}'".format(audience)

    if audience == DRIVER:
        from apex.salis import permissions as salis_permissions

        projects = salis_permissions.allowed_projects(user)
        if not projects:
            return "1=0"
        escaped = ", ".join(frappe.db.escape(v) for v in projects)
        return (
            "(`holder_type` = 'Driver' and `driver` in ("
            "select `name` from `tabSalis Driver` where `project` in ({0})))"
        ).format(escaped)

    from apex.habitat import permissions as habitat_permissions

    buildings = habitat_permissions.allowed_buildings(user)
    if not buildings:
        return "1=0"
    escaped = ", ".join(frappe.db.escape(v) for v in buildings)
    return (
        "(`holder_type` = 'Worker' and `employee` in ("
        "select `employee` from `tabHousing Assignment` where `docstatus` = 1 "
        "and `check_out_date` is null and `building` in ({0})))"
    ).format(escaped)

def masar_worker_token_scope_query(user=None, doctype=None) -> str:
    del doctype
    user = user or frappe.session.user
    if user == "Administrator":
        return ""
    roles = set(frappe.get_roles(user))

    clauses = []
    for audience in (DRIVER, WORKER):
        if roles.intersection(ISSUER_ROLES[audience]):
            clauses.append(_audience_scope_clause(audience, user, roles))
    if not clauses:
        return "1=0"
    return "({0})".format(" or ".join(clauses))

def masar_worker_token_has_permission(doc, ptype, user=None):
    if ptype not in ("read", "report", "print"):
        return None
    user = user or frappe.session.user
    if user == "Administrator":
        return None
    roles = set(frappe.get_roles(user))
    audience = getattr(doc, "holder_type", None)
    return _issuer_scoped_verdict(doc, audience, user, roles)


def _issuer_scoped_verdict(doc, audience: str, user: str, roles: set):
    if audience not in ISSUER_ROLES or not roles.intersection(ISSUER_ROLES[audience]):
        return False
    if roles.intersection(_UNSCOPED_ISSUER_ROLES[audience]):
        return None

    if audience == DRIVER:
        from apex.salis import permissions as salis_permissions

        driver = getattr(doc, "driver", None)
        project = frappe.db.get_value("Salis Driver", driver, "project") if driver else None
        if project and project in set(salis_permissions.allowed_projects(user)):
            return None
        return False

    from apex.habitat import permissions as habitat_permissions

    employee = getattr(doc, "employee", None)
    if not employee:
        return False
    assignments = frappe.get_all(
        "Housing Assignment",
        filters={"employee": employee, "docstatus": 1, "check_out_date": ["is", "not set"]},
        pluck="building",
    )
    buildings = {b for b in assignments if b}
    allowed = set(habitat_permissions.allowed_buildings(user))
    return None if buildings and buildings.issubset(allowed) else False


def portal_device_scope_query(user=None, doctype=None) -> str:
    del doctype
    from apex.apex_core.utils.permission_scope import is_portal_capacity

    user = user or frappe.session.user
    if user == "Administrator":
        return ""
    if is_portal_capacity(user):
        audience = WORKER if user == CAPACITY_USERS[WORKER] else DRIVER
        field = "employee" if audience == WORKER else "driver"
        bound = capacity_subject(audience)
        if not bound:
            return "1=0"
        return "`{0}` = {1}".format(field, frappe.db.escape(bound))

    roles = set(frappe.get_roles(user))
    clauses = []
    for audience in (DRIVER, WORKER):
        if roles.intersection(ISSUER_ROLES[audience]):
            clauses.append(_audience_scope_clause(audience, user, roles))
    if not clauses:
        return "1=0"
    return "({0})".format(" or ".join(clauses))


def portal_device_has_permission(doc, ptype, user=None):
    from apex.apex_core.utils.permission_scope import is_portal_capacity, portal_capacity_verdict

    user = user or frappe.session.user
    if is_portal_capacity(user):
        verdict = portal_capacity_verdict(ptype)
        if verdict is False:
            return False
        audience = WORKER if user == CAPACITY_USERS[WORKER] else DRIVER
        field = "employee" if audience == WORKER else "driver"
        bound = capacity_subject(audience)
        if bound and getattr(doc, field, None) == bound:
            return verdict
        return False

    if ptype not in ("read", "report", "print", "write"):
        return None
    if user == "Administrator":
        return None
    roles = set(frappe.get_roles(user))
    audience = getattr(doc, "holder_type", None)
    return _issuer_scoped_verdict(doc, audience, user, roles)


def credential_delivery_destination(
    audience: str,
    subject: str,
    requested=None,
) -> str | None:
    _require_audience(audience)

    fieldname = "cell_number" if audience == WORKER else "phone"
    stored = normalize_phone(
        frappe.db.get_value(_SUBJECT_DOCTYPES[audience], subject, fieldname)
    )
    if requested is not None and normalize_phone(requested) != stored:
        frappe.throw(
            _("The requested phone does not match the subject's stored phone."),
            frappe.PermissionError,
        )
    return stored

_PUSH_SUBSCRIPTION_SUBJECT_FIELDS = {WORKER: "employee", DRIVER: "driver"}


def portal_push_subscription_scope_query(user=None, doctype=None) -> str:
    del doctype
    from apex.apex_core.utils.permission_scope import is_portal_capacity, resolve_user

    if is_portal_capacity(resolve_user(user)):
        return "1=0"
    return None


def portal_push_subscription_has_permission(doc, ptype, user=None):
    from apex.apex_core.utils.permission_scope import (
        is_portal_capacity,
        portal_capacity_verdict,
    )

    user = user or frappe.session.user
    if not is_portal_capacity(user):
        return None

    verdict = portal_capacity_verdict(ptype)
    if verdict is False:
        return False

    audience = WORKER if user == CAPACITY_USERS[WORKER] else DRIVER
    field = _PUSH_SUBSCRIPTION_SUBJECT_FIELDS[audience]
    bound = capacity_subject(audience)
    if bound and getattr(doc, field, None) == bound:
        return verdict
    return False
