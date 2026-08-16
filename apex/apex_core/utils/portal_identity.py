# Copyright (c) 2026, afmcoltd
"""Shared authorization boundary for worker and driver portal bearer tokens.

``log_credential_event`` inserts with ``ignore_permissions`` because it records credential
issue, use and revocation — an audit trail written about the actor, never by them. The caller here
is usually a token holder with no user at all, and a role able to write this log could rewrite the
record of its own access, which is the one thing an audit trail must refuse.
"""

from __future__ import annotations

import hashlib
from contextlib import contextmanager

import frappe
from frappe import _

from apex.apex_core.utils.rate_window import charge_window

WORKER = "Worker"
DRIVER = "Driver"
TOKEN_COOKIES = {WORKER: "masar_wt", DRIVER: "masar_dt"}

# One login-disabled user per capacity, seeded by portal_identity_seed. A token carries WHO; these
# carry WHAT THAT CAPACITY MAY DO, so a portal write can be graded by a DocPerm instead of skipping
# permissions entirely.
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


def _throttle_bad_token_attempt() -> None:
    """Charge one failed portal-token attempt against this address's window; the
    (N+1)th raises RateLimitExceededError (HTTP 429). A caller with no request or no
    remote address cannot be attributed to an address, so it is a no-op there --
    console, scheduled-job and test callers are never throttled.

    The counting itself is the shared atomic window, NOT rate_limiter.py's
    read-then-write: this throttle exists to make a parallel flood visible, and the
    framework's shape goes quiet under exactly that load (see rate_window).
    """
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
    """Blocks an audience value that is neither Worker nor Driver."""
    if audience not in TOKEN_COOKIES:
        frappe.throw(
            _("Portal token audience must be Worker or Driver."),
            frappe.ValidationError,
        )


def hash_token(raw: str) -> str:
    """Return the SHA-256 digest persisted for a raw bearer token."""
    return hashlib.sha256((raw or "").encode("utf-8")).hexdigest()


PORTAL_ROOM_PREFIX = "apex-portal-"


def portal_room(audience: str, token=None) -> str:
    """The realtime room this portal session may join, or "" when it has no token.

    A portal session is a GUEST holding a token, not a permissioned user, so it can
    never join a doctype room: frappe's socket server gates doctype_subscribe and
    doc_subscribe on read permission, while task_subscribe
    (realtime/handlers/frappe_handlers.js) joins with no check at all. The task room is
    therefore the only native room a Guest may join, and it admits on knowledge of an
    unguessable id — which is what the token's stored SHA-256 hash already is.

    The RAW token never appears in a room id, and the client is handed this value by
    the context call that has already authenticated the token; it is never derived
    client-side.
    """
    _require_audience(audience)
    raw, was_presented = presented_token(audience, token)
    if not was_presented or not raw:
        return ""
    return PORTAL_ROOM_PREFIX + hash_token(raw)


def portal_rooms_for_subject(audience: str, subject: str) -> list:
    """Every live room belonging to one driver or employee.

    The room id is the token's stored hash, so it is read straight off the enabled
    token rows — the raw token is never needed and never leaves the holder's browser.
    A subject with a reissued link may hold more than one enabled row, so all of them
    are rung rather than guessing which browser is open.
    """
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
    """Ring one subject's own rooms. Returns how many were rung."""
    rooms = portal_rooms_for_subject(audience, subject)
    for room in rooms:
        frappe.publish_realtime(event, message or {}, room=room, after_commit=True)
    return len(rooms)


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
    """Throttles the failed attempt and raises a permission error for an invalid or inactive token."""
    _throttle_bad_token_attempt()
    frappe.throw(
        _("This portal access token is invalid or inactive."),
        frappe.PermissionError,
    )


@contextmanager
def as_capacity(audience: str):
    """Run a block as the capacity user, then hand the session back.

    Only ever open this AFTER a token has been resolved: the token is the authentication and this
    is the authorisation that follows it. The restore is in a ``finally`` because a scheduler or a
    request worker is reused, and a session left elevated would carry into whatever ran next.

    There is deliberately no existence check on the identity. ``portal_identity_seed`` creates it
    on install and on every migrate, so a missing one is an installation fault, and the write
    inside would fail with a permission error naming the DocType — which is the more useful
    message anyway. A guard here would cost a query on every portal write to restate that.
    """
    _require_audience(audience)
    user = CAPACITY_USERS[audience]
    previous = frappe.session.user
    frappe.set_user(user)
    try:
        yield user
    finally:
        frappe.set_user(previous)


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


def _deny_issuance(audience: str) -> None:
    """Raises a permission error naming the audience whose portal credential issuance is denied."""
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


ISSUED = "Issued"
REISSUED = "Reissued"
RESHARED = "Re-shared"
ROTATED = "Rotated"
REVOKED = "Revoked"


def _credential_event_subject(action: str, audience: str, subject: str) -> str:
    """The Activity Log sentence for one credential action.

    Five whole literal sentences rather than a shared frame plus a translated verb:
    Arabic inflects a verb with its noun, and the app's existing ``Issued`` row
    already means dispensed-from-stores, so a shared verb would render the wrong
    word here. An unknown action raises rather than logging a vague line -- the only
    callers are the constants above.
    """
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
    """Record WHO moved a portal credential and FOR WHOM, in the native Activity Log.

    The token row carries only ``last_generated_by``/``last_generated_on`` -- one
    slot, overwritten by the next action -- and revocation writes with
    ``update_modified=False``, so before this the strongest surviving statement about
    a passwordless bearer credential was "someone, at some point". Activity Log is
    Frappe's own append-only actor trail: System Manager is its ONLY reading role
    (activity_log.json permissions), native Log Settings ages it out, and
    ``link_doctype``/``link_name`` make "every move on this driver" one query.

    The raw token is not a parameter here, so no call site can log the secret: the row
    names the SUBJECT and the token ROW, never the credential. ``operation`` and
    ``status`` are left to Frappe -- both are closed Selects, and a value outside the
    set is swallowed silently on insert.
    """
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
    ).insert(ignore_permissions=True, ignore_links=True).name


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
        log_credential_event(audience, subject, REVOKED, row.name)
        disabled += 1
    if frappe.db.table_exists("Portal Push Subscription"):
        from apex.salis.api.web_push import disable_subject_subscriptions

        disable_subject_subscriptions(audience, subject)
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


def authorize_issuance(
    audience: str,
    subject: str,
    user=None,
    *,
    require_active: bool = True,
) -> bool:
    """Authorize one issuer and subject, returning whether scope is restricted."""
    _require_audience(audience)
    user = user or frappe.session.user
    frappe.has_permission(
        "Masar Worker Token", "write", user=user, throw=True
    )

    subject_row = _lock_subject_row(audience, subject, require_active=require_active)
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


def authorize_revocation(audience: str, subject: str, user=None) -> bool:
    """Authorize a MANUAL revocation: same issuer roles, same project/building scope.

    Identical to issuance except that the subject need not still be Active. Requiring
    Active would make the desk kill switch unreachable in exactly the cases it exists
    for -- a driver already Released by a clearance, or Stopped mid-investigation --
    while the automatic hooks that revoke on those transitions are the very reason a
    non-Active subject is the normal state at revocation time. Withdrawing a bearer
    credential is the safe direction; the scope check still stops a supervisor
    reaching a driver outside their project, so this widens WHEN, never WHO.

    Deliberately reuses issuance's deny path so an out-of-scope caller cannot tell
    the two apart, and so there is only one refusal to keep correct.

    DRIVER only today, and not safe to wire to WORKER unexamined: the Resident
    Supervisor scope branch admits a worker only through a live Housing Assignment
    (submitted, no check-out date), so dropping the Active requirement would not
    actually reach a checked-out worker -- the case a worker revocation is for. That
    branch needs its own carve-out before this is offered for WORKER.
    """
    return authorize_issuance(audience, subject, user, require_active=False)


def _audience_scope_clause(audience: str, user: str, roles: set) -> str:
    """The ``holder_type``-guarded WHERE fragment for one audience the caller may issue for.

    ``audience`` is always ``DRIVER`` or ``WORKER`` here (the loop in
    :func:`masar_worker_token_scope_query` supplies nothing else), so it is interpolated
    as a literal rather than escaped, matching every other hardcoded fragment in this
    module.
    """
    if roles.intersection(_UNSCOPED_ISSUER_ROLES[audience]):
        return "`holder_type` = '{0}'".format(audience)

    if audience == DRIVER:
        from apex.salis import permissions as salis_permissions

        projects = salis_permissions._allowed_projects(user)
        if not projects:
            return "1=0"
        escaped = ", ".join(frappe.db.escape(v) for v in projects)
        return (
            "(`holder_type` = 'Driver' and `driver` in ("
            "select `name` from `tabSalis Driver` where `project` in ({0})))"
        ).format(escaped)

    from apex.habitat import permissions as habitat_permissions

    buildings = habitat_permissions._allowed_buildings(user)
    if not buildings:
        return "1=0"
    escaped = ", ".join(frappe.db.escape(v) for v in buildings)
    return (
        "(`holder_type` = 'Worker' and `employee` in ("
        "select `employee` from `tabHousing Assignment` where `docstatus` = 1 "
        "and `check_out_date` is null and `building` in ({0})))"
    ).format(escaped)


def masar_worker_token_scope_query(user=None, doctype=None) -> str:
    """WHERE fragment scoping the Masar Worker Token list/report view.

    Registered in ``hooks.py`` (``permission_query_conditions``), paired with
    :func:`masar_worker_token_has_permission`. Masar Worker Token has no Project or
    Building column of its own, and its two holder types sit on two different tenancy
    axes, so this dispatches per row's ``holder_type`` rather than delegating to
    ``apex.salis.permissions`` or ``apex.habitat.permissions``' own DocType-keyed
    fragments: Driver rows scope through ``Salis Driver.project``, Worker rows through
    the employee's live Housing Assignment building — the SAME two reads
    :func:`authorize_issuance` performs on write, off the SAME ``ISSUER_ROLES`` /
    ``_UNSCOPED_ISSUER_ROLES`` tables, so a row a caller may not issue for is never a
    row they may list.

    A role absent from ``ISSUER_ROLES[audience]`` contributes no clause for that
    audience, so a caller holding neither set sees no rows at all — "1=0". A role in
    ``_UNSCOPED_ISSUER_ROLES[audience]`` sees every row of that audience unrestricted
    (HR User over every Worker row, Fleet Manager over every Driver row), exactly as
    ``authorize_issuance`` defers those roles' write. Everyone else is confined to the
    Project / Building they hold a User Permission for.
    """
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
    """Deny reading, reporting or printing a Masar Worker Token row outside issuer scope.

    Registered in ``hooks.py`` (``has_permission``), paired with
    :func:`masar_worker_token_scope_query` — same tables, same verdicts, so a row
    hidden from the list can never still open on the form or print. Only ``read`` /
    ``report`` / ``print`` are gated: ``create`` / ``write`` / ``delete`` stay exactly
    as they run today, decided by the DocPerm plus :func:`authorize_issuance`'s own
    explicit project/building check on every issuance and rotation, which this must
    not duplicate or disagree with.

    Returns False to block, or None to defer to Frappe's default resolution (the
    DocPerm). Never True.
    """
    if ptype not in ("read", "report", "print"):
        return None
    user = user or frappe.session.user
    if user == "Administrator":
        return None
    roles = set(frappe.get_roles(user))
    audience = getattr(doc, "holder_type", None)
    if audience not in ISSUER_ROLES or not roles.intersection(ISSUER_ROLES[audience]):
        return False
    if roles.intersection(_UNSCOPED_ISSUER_ROLES[audience]):
        return None

    if audience == DRIVER:
        from apex.salis import permissions as salis_permissions

        driver = getattr(doc, "driver", None)
        project = frappe.db.get_value("Salis Driver", driver, "project") if driver else None
        if project and project in set(salis_permissions._allowed_projects(user)):
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
    allowed = set(habitat_permissions._allowed_buildings(user))
    return None if buildings and buildings.issubset(allowed) else False


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
