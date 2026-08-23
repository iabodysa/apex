# Copyright (c) 2026, afmcoltd
"""Masar worker identity, the worker's own records, and the worker-write contract.

The fail-closed boundary every worker endpoint funnels through — a presented
personal token resolved to exactly one Employee — plus the readers and shapers
for the records that Employee owns.

Readers (``_active_assignment``, ``_custody_issued_by``, ``_building_in_charge``,
``_today_driver``) touch the database. Shapers
(``_iqama_of``, ``_worker_documents``, ``_net_custody_items``,
``_request_status_timeline``, ``_clean_adhoc_passengers``) take plain values and
return plain values, so each runs without a bench.

THE WORKER-WRITE CONTRACT. Every token-scoped endpoint in ``masar.py`` obeys all
four clauses, or is named an exception below. Breaking one is a defect.

1. Resolve first: call ``_resolve_worker(token)`` before reading or writing
   anything about a worker. Identity is established here and nowhere else.
2. Derive every scope server-side. An Employee id, building, trip or request name
   from the client is a parameter to VALIDATE against what the resolved worker
   owns — never a scope to trust.
3. Carry ``@rate_limit``: a passwordless bearer token on an unbounded endpoint is
   an unbounded credential. Writes are tighter than reads.
4. A system write is the framework's own ``ignore_permissions=True`` call, nothing
   wrapped and no per-call comment beside it: a comment drifts out of sync with the
   line it sits beside, and a wrapper can rename the grant without ever withdrawing
   one, hiding the true count behind a layer of indirection. The count that matters
   is the raw ``ignore_permissions=True`` count, not a named-helper count that can
   silently diverge from it.

Measured by AST over ``masar.py``: 17 whitelisted endpoints, 14
token-scoped, and all 14 resolve and rate-limit. The five writes
(``create_worker_request``, ``notify_hr_iqama_expiring``, ``confirm_boarding``,
``create_worker_transport_request``, ``submit_trip_rating``) write only after the
token has resolved to one worker.

Exceptions: ``get_my_worker_route_today`` and ``get_my_worker_route_summary`` run
on a logged-in staff session, not a token, so Frappe's session identity governs
them; ``get_enum_labels`` returns static labels and reads no worker record, so
there is no scope to derive.
"""

import os

import frappe
from frappe import _

from apex.apex_core.utils.portal_identity import (
    WORKER,
    TOKEN_COOKIES,
    presented_token,
    resolve_portal_subject,
)
from apex.salis.api.masar_routes import _worker_today_dispatch_trip
from apex.salis.utils import days_until as _days_until

MASAR_TOKEN_COOKIE = TOKEN_COOKIES[WORKER]

WORKER_PHOTO_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
WORKER_PHOTO_MAX_BYTES = 8 * 1024 * 1024

_RESIDENT_REQUEST_SETTLED_STATES = ("Resolved", "Rejected", "Closed")


def _token_from_request(token=None):
    """The personal token for this call: the explicit arg if given, else the
    httpOnly cookie. Returns '' when neither is present (resolver fails closed)."""
    return presented_token(WORKER, token)[0]


def _resolve_worker(token):
    """Resolve a required Worker credential to its exact active Employee.

    Every worker endpoint funnels through this fail-closed identity boundary; the
    client cannot widen its scope with an Employee id or another token audience.
    """
    return resolve_portal_subject(WORKER, token, required=True)


def _fmt_date(value):
    """Returns the value as a string, or None when it is blank.

    ``frappe.utils.cstr`` (frappe/utils/data.py:1041) stringifies ``None`` as
    ``""`` and a falsy value like ``0`` as its own string, neither of which JSON
    payload consumers can tell apart from a set value; this coalesces every
    blank input to ``None`` so the API response can say "no value" with a JSON
    null. Absorbed the identical definition that lived in
    ``apex.salis.api.driver_portal.profile``."""
    return frappe.utils.cstr(value) if value else None


def _iqama_of(emp):
    """The worker's Iqama number and expiry as a ``(number, expiry)`` pair.

    HR setups spell these fields differently — ``iqama`` or ``iqama_no`` for the
    number, ``iqama_expiry`` or ``valid_upto`` for the expiry — and the profile
    read and the HR alert must agree on which one is authoritative or a worker
    sees an expiry that HR is never told about. Reading them in one place is what
    keeps the two answers the same. Pure."""
    return (
        emp.get("iqama") or emp.get("iqama_no"),
        emp.get("iqama_expiry") or emp.get("valid_upto"),
    )


def _worker_documents(emp):
    """The worker's identity documents with days-to-expiry, profile order.

    An Iqama is listed when either its number or its expiry is on file (an expiry
    alone still needs renewing); a passport only when its number is, since a bare
    passport expiry names no document. Pure: ``emp`` is the whole input and no
    field is read that is not read defensively."""
    documents = []
    iqama_no, iqama_expiry = _iqama_of(emp)
    if iqama_no or iqama_expiry:
        documents.append(
            {
                "type": "iqama",
                "number": iqama_no,
                "expiry": _fmt_date(iqama_expiry),
                "days_left": _days_until(iqama_expiry),
            }
        )
    passport_no = emp.get("passport_number")
    passport_expiry = emp.get("passport_expiry")
    if passport_no:
        documents.append(
            {
                "type": "passport",
                "number": passport_no,
                "expiry": _fmt_date(passport_expiry),
                "days_left": _days_until(passport_expiry),
            }
        )
    return documents


def _active_assignment(employee):
    """The worker's current (submitted, not checked-out) Accommodation Assignment,
    or None. Scoped strictly to the resolved employee."""
    rows = frappe.get_all(
        "Housing Assignment",
        filters={
            "employee": employee,
            "docstatus": 1,
            "check_out_date": ["is", "not set"],
        },
        fields=[
            "name",
            "building",
            "room",
            "bed",
            "project",
            "check_in_date",
            "stay_type",
            "expected_checkout_date",
            "notes",
        ],
        order_by="check_in_date desc",
        limit=1,
    )
    return rows[0] if rows else None


def _request_status_timeline(req):
    """A simple created -> current timeline for one resident request.

    The DocType has no explicit per-status history table, so we build the
    timeline from the available date fields: always a 'created' point (creation),
    and — when the request has reached a settled state — a 'closed' point
    (closed_on, falling back to modified). The current status is always carried
    as the active step so the UI can highlight where the request stands. Each
    point is ``{"key", "status", "timestamp"}`` with a bare string timestamp the
    client localizes; ordered oldest -> newest. Pure."""
    timeline = [
        {
            "key": "created",
            "status": "New",
            "timestamp": frappe.utils.cstr(req.get("creation")) if req.get("creation") else None,
        }
    ]
    status = req.get("status")
    if status in _RESIDENT_REQUEST_SETTLED_STATES:
        timeline.append(
            {
                "key": "closed",
                "status": status,
                "timestamp": frappe.utils.cstr(req.get("closed_on") or req.get("modified"))
                if (req.get("closed_on") or req.get("modified"))
                else None,
            }
        )
    else:
        if status and status != "New":
            timeline.append(
                {
                    "key": "current",
                    "status": status,
                    "timestamp": frappe.utils.cstr(req.get("modified"))
                    if req.get("modified")
                    else None,
                }
            )
    return timeline


def _net_custody_items(rows):
    """Net still-held custody per (building, article) from stock-ledger rows.

    Issues add, returns reverse, and a bucket whose net has fallen to zero or
    below is dropped — what survives is what is still out. ``received_date`` and
    ``_issue_voucher`` track the LATEST issue row, so a re-issue after a return
    dates from the re-issue. Rows arrive oldest-first; buckets come back in the
    order their article was first seen, and the caller names the issuer and sorts.

    Pure: ``rows`` is the whole input, so the net-balance rule can be exercised
    without a ledger."""
    from frappe.utils import flt

    agg = {}
    for r in rows:
        key = (r.building, r.item)
        bucket = agg.setdefault(
            key,
            {
                "item": r.item,
                "item_name": r.item_name,
                "building": r.building,
                "uom": r.uom,
                "qty": 0.0,
                "received_date": None,
                "_issue_voucher": None,
            },
        )
        bucket["qty"] += flt(r.signed_qty)
        if flt(r.signed_qty) > 0:
            bucket["received_date"] = _fmt_date(r.posting_date)
            if r.voucher_type == "Custody Issue" and r.voucher_no:
                bucket["_issue_voucher"] = r.voucher_no
    return [bucket for bucket in agg.values() if bucket["qty"] >= 1e-9]


def _custody_issued_by(custody_issue, building):
    """Name the supervisor who issued a held article to the worker.

    Custody Issue has no dedicated 'issued by' field, so the issuer is its
    ``owner`` (the user who created/submitted it), resolved to a person name.
    Falls back to the building's responsible facility supervisor, then None when
    nothing resolves (the client renders its own placeholder). Never throws —
    the worker view degrades gracefully.

    ``frappe.utils.get_fullname`` (frappe/utils/__init__.py:47) turns the user id into
    the name a person recognises. The one thing it cannot do is fail loudly: it
    returns the id back when no User row exists, which is why the caller treats a
    value equal to the id as "unresolved" rather than as a name."""
    owner = None
    if custody_issue:
        owner = frappe.db.get_value("Custody Issue", custody_issue, "owner")
    if owner:
        return frappe.utils.get_fullname(owner) or owner
    if building:
        sup = frappe.db.get_value(
            "Building", building, "responsible_supervisor"
        )
        if sup:
            return frappe.utils.get_fullname(sup) or sup
    return None


def _attach_worker_photo(doc, photo, photo_filename):
    """Attach a guest-supplied request photo to ``doc`` and set ``doc.attachment``.

    The image rides in as a ``data:`` URI on the same token-scoped POST that created
    the request — there is NO separate guest upload surface to harden. The BYTES are
    what decides: the shared driver-portal verifier re-decodes them, opens the
    container and matches its real format against the declared content type, so a
    text file renamed ``.jpg`` is refused rather than stored. The extension written to
    disk is then DERIVED from the verified format, never taken from the caller's
    filename, so nothing can be laundered into an image name. A photo that fails
    refuses the request instead of being dropped silently: storing a non-image under an
    image name is worse than making the worker re-attach.

    The File is PRIVATE and created through the framework's ``save_file`` (which
    re-checks the site max-file-size); its path is written back to ``attachment`` so
    the existing detail view renders it."""
    from frappe.utils.file_manager import save_file

    from apex.salis.api.driver_portal.images import verified_image_type

    photo = (photo or "").strip()
    if not photo:
        return

    content_type = verified_image_type(photo, max_bytes=WORKER_PHOTO_MAX_BYTES)

    stem = (photo_filename or "request-photo").strip() or "request-photo"
    stem = stem.replace("\\", "/").split("/")[-1]
    stem = os.path.splitext(stem)[0] or "request-photo"
    fname = f"{stem}{WORKER_PHOTO_EXTENSIONS[content_type]}"

    saved = save_file(
        fname,
        photo,
        doc.doctype,
        doc.name,
        decode=True,
        is_private=1,
        df="attachment",
    )
    doc.db_set("attachment", saved.file_url)


def _clean_adhoc_passengers(passengers):
    """Validate + normalize the client's ad-hoc passenger rows. Returns a list of
    clean dicts ready to append to the request's ``adhoc_passengers`` table; throws
    on a row missing a name or ID, or carrying an unparseable expiry.

    ``frappe.parse_json`` (frappe/__init__.py:2491) accepts the string the portal
    posts. The one thing it cannot do is validate the rows: it produces whatever
    shape the client sent, so every field is checked here before any of it reaches a
    child table the framework would then accept without comment."""
    passengers = frappe.parse_json(passengers or "[]")
    rows = []
    for p in passengers or []:
        full_name = (p.get("full_name") or "").strip()
        id_number = (p.get("id_number") or "").strip()
        if not full_name or not id_number:
            frappe.throw(_("Each additional passenger needs a name and an ID number."))
        expiry = (p.get("id_expiry") or "").strip() or None
        if expiry:
            try:
                expiry = frappe.utils.getdate(expiry).isoformat()
            except Exception:
                frappe.throw(_("An additional passenger's ID expiry is not a valid date."))
        rows.append(
            {
                "full_name": full_name[:140],
                "id_number": id_number[:64],
                "id_expiry": expiry,
                "nationality": (p.get("nationality") or "").strip()[:64] or None,
                "phone": (p.get("phone") or "").strip()[:32] or None,
            }
        )
    return rows


def _building_in_charge(employee):
    """The worker's current building in-charge contact, or None. Resolved from the
    active assignment's building (``responsible_supervisor`` User), the
    same source the accommodation screen uses.

    ``frappe.utils.get_fullname`` (frappe/utils/__init__.py:47) renders the contact.
    Only the name and the contact fields are returned, never the User record: this is
    read by a worker's portal, and the one thing the framework will not do for us is
    decide which of a User's fields a non-User audience may see."""
    assignment = _active_assignment(employee)
    user = assignment and frappe.db.get_value(
        "Building", assignment.get("building"), "responsible_supervisor"
    )
    if not user:
        return None
    return {
        "name": frappe.utils.get_fullname(user) or user,
        "phone": frappe.db.get_value("User", user, "mobile_no"),
    }


def _today_driver(employee):
    """The driver of the worker's today Dispatch Trip, or None. Resolved forward
    from today's trip on the worker's OWN manifest (via ``_worker_today_dispatch_trip``),
    so it can never reach a driver the worker is not riding with today."""
    resolved = _worker_today_dispatch_trip(employee)
    if not resolved:
        return None
    driver = frappe.db.get_value("Dispatch Trip", resolved[0], "driver")
    if not driver:
        return None
    d = frappe.db.get_value("Salis Driver", driver, ["full_name", "phone"], as_dict=True)
    return d or None
