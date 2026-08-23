# Copyright (c) 2026, afmcoltd
"""Arrivals Desk read + lookup API (party-aware).

A presentation/lookup layer for the unified worker-arrival desk page. The page's
WRITES go through existing whitelisted endpoints (the party-aware Front Desk
quick_check_in, the Custody Kiosk issue, the Masar worker-link issuer). This
module adds:

- ``get_arrival_card`` — the party-aware arrival snapshot (Employee | Temporary
  Worker), built from the same active-occupancy / custody / token semantics as the
  Front Desk board. ``employee=`` is kept as a legacy alias for an Employee party,
  and the legacy ``employee``/``employee_name`` keys stay in the response, so the
  old desk keeps working.
- ``search_arrivals_workers`` — one combined search returning registered Employees
  first, then active Temporary Workers, each tagged with its ``party_type``.
- ``register_temporary_worker`` — register a passport-only new arrival. A housing
  supervisor may create a Temporary Worker but NEVER an Employee (the doctype is
  hard-coded; Employee creation is HRMS-gated and unreachable here).

The printed slips live in ``habitat.utils.arrival_slips``; the occupancy and bed
rules in ``habitat.utils.occupancy``.
"""

from __future__ import annotations

import frappe
from frappe import _

from apex.apex_core.doctype.masar_worker_token.masar_worker_token import (
    masar_qr_data_uri,
    reshare_worker_link,
)
from apex.apex_core.utils.party_link import PARTY_EMPLOYEE, PARTY_TEMPORARY_WORKER
from apex.apex_core.utils.portal_identity import (
    WORKER,
    credential_delivery_destination,
)
from apex.habitat import permissions
from apex.habitat.utils import arrival_slips, occupancy
from apex.habitat.utils.arrival_slips import (
    ARRIVAL_SLIP_TEMPLATE,
    CHECKIN_SLIP_TEMPLATE,
    CUSTODY_HANDOVER_SLIP_TEMPLATE,
)
from apex.habitat.utils.housing_scope import active_building_scope

__all__ = [
    "ARRIVAL_SLIP_TEMPLATE",
    "CHECKIN_SLIP_TEMPLATE",
    "CUSTODY_HANDOVER_SLIP_TEMPLATE",
]

def _expiry_days(expiry_date) -> int | None:
    """Whole days from today until a Temporary Worker's window expiry.

    Negative once the window has lapsed, ``0`` on the expiry day, ``None`` when
    no expiry is set. Computed server-side so the desk renders a single source of
    truth (no client-side date math).

    ``frappe.utils.date_diff`` (frappe/utils/data.py:282) does the subtraction. The
    one thing it cannot do is distinguish "no expiry" from "expires today": handed a
    blank it raises rather than answering, so the ``None`` case is decided here."""
    if not expiry_date:
        return None
    return frappe.utils.date_diff(expiry_date, frappe.utils.today())

def _assert_party_in_scope(party_type, party) -> None:
    """Enforce per-doc BUILDING scope before any party PII / identity is returned.

    The desk lookups take a CLIENT-SUPPLIED docname. A type-level
    ``has_permission`` only proves the caller may read the doctype at all — it does
    NOT confine them to their own estate, so a scoped supervisor (or any low-role
    user with a type-level read) could otherwise harvest another building's worker
    identity, passport, and Iqama. This re-applies the same building scope the list
    views get via ``permission_query_conditions``. That hook runs inside
    ``DatabaseQuery`` (frappe/model/db_query.py), and the one thing it cannot do is
    reach a direct ``frappe.db.get_value`` — which is exactly the read below it, so
    the scope is asserted here or it is not asserted at all. Refusal raises
    ``frappe.PermissionError``, the class the framework itself uses.

    Unscoped oversight roles (HOUSING_UNSCOPED_ROLES) / Administrator pass through.
    Scoped-user rules per party type:

    * Temporary Worker — scoped on its own ``building`` field; a worker with no
      building (or one outside the caller's estate) is denied (a scoped user can
      never act on an estate-less party — mirrors permissions). The
      passport / Iqama leak (R1) lives here.
    * Employee — scoped on the building of its LIVE Accommodation Assignment. An
      employee actively housed in ANOTHER estate is denied (the real R2 leak). An
      employee with NO live assignment (a not-yet-housed arrival) is allowed, so
      the legitimate intake / check-in lookup the desk does before assigning a bed
      is never broken — that path exposes only name + photo, never PII.
    """
    user = frappe.session.user
    if permissions._building_is_unscoped(user):
        return

    allowed = set(permissions._allowed_buildings(user))

    if party_type == PARTY_TEMPORARY_WORKER:
        building = frappe.db.get_value("Temporary Worker", party, "building")
        if not building or building not in allowed:
            raise frappe.PermissionError(
                _("You are not permitted to access this worker's record.")
            )
        return

    if party_type == PARTY_EMPLOYEE:
        building = frappe.db.get_value(
            "Housing Assignment",
            occupancy.active_assignment_filters(party_type=PARTY_EMPLOYEE, party=party),
            "building",
        )
        if building and building not in allowed:
            raise frappe.PermissionError(
                _("You are not permitted to access this worker's record.")
            )
        return

@frappe.whitelist()
def get_intake_settings() -> dict:
    """The Arrivals Desk feature flags, answered without exposing Habitat Settings.

    The desk reads ``enable_passport_mrz_ocr`` here rather than through
    ``frappe.client.get_single_value``, which needs read on the whole Single. Habitat
    Settings grants read to System Manager only, so routing through it would meet the
    Resident Supervisor the page is published to with a blocking permission dialog on
    every load — a client-side ``.catch()`` cannot suppress it, because the dialog is
    raised by the transport, not by the promise the caller holds.

    Only the one boolean is returned, and only to a caller who could actually use the
    passport register sheet it gates (the same ``Temporary Worker`` create right that
    ``register_temporary_worker`` and ``parse_passport`` already enforce). Anyone else
    is told the feature is off rather than refused, so the desk still renders.
    """
    if not frappe.has_permission(PARTY_TEMPORARY_WORKER, "create"):
        return {"enable_passport_mrz_ocr": False}
    return {
        "enable_passport_mrz_ocr": bool(
            frappe.db.get_single_value("Habitat Settings", "enable_passport_mrz_ocr")
        )
    }

@frappe.whitelist(methods=["POST"])
def send_masar_link_message(employee, phone=None) -> dict:
    """Send a worker their already-issued Masar link to their phone (WhatsApp/SMS).

    The per-row desk action on the QR block: resolves the worker's enabled Masar
    token (the link is server-produced, never trusted from the client — a missing
    or disabled token is refused), then hands it to the settings-driven messaging
    gateway. ``phone`` may be passed (the desk already has it from the link
    issuer); when omitted the Employee's ``cell_number`` is read server-side.

    Permission-gated on read of the Masar Worker Token (the same gate the slip QR
    uses). Returns the gateway queue/no-op result; when the gateway is not
    configured the send is a graceful no-op (``queued: False, reason:
    not_configured``) so the desk can message the operator to wire it, never
    erroring."""
    from apex.salis.api import messaging_gateway

    frappe.has_permission("Masar Worker Token", "read", throw=True)
    _assert_party_in_scope(PARTY_EMPLOYEE, employee)
    destination = credential_delivery_destination(
        WORKER, employee, requested=phone
    )
    gateway_configured = messaging_gateway.is_configured()
    if not destination:
        return {
            "gateway_configured": gateway_configured,
            "queued": False,
            "reason": "no_phone",
        }
    if not gateway_configured:
        return {
            "gateway_configured": False,
            "queued": False,
            "reason": "not_configured",
        }

    savepoint = "masar_link_delivery"
    frappe.db.savepoint(savepoint)
    try:
        link = reshare_worker_link(employee)
        if not link:
            frappe.throw(
                _("This worker has no active Masar link yet. Create the QR first.")
            )

        result = messaging_gateway.send_masar_link(
            employee, link, phone=destination
        )
        if not result.get("queued"):
            frappe.db.rollback(save_point=savepoint)
            return {"gateway_configured": True, **result}
        frappe.db.release_savepoint(savepoint)
        return {"gateway_configured": True, **result}
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise

def _arrival_identity(party_type, party):
    """``(worker_name, image, expiry_date)`` for one party, permission- and
    scope-gated before any identity leaves the server. Only a Temporary Worker has
    an expiry; only an Employee has a photo."""
    if party_type == PARTY_EMPLOYEE:
        frappe.has_permission("Employee", "read", throw=True)
        _assert_party_in_scope(party_type, party)
        info = frappe.db.get_value("Employee", party, ["employee_name", "image"], as_dict=True) or {}
        if not info:
            frappe.throw(_("Employee {0} does not exist.").format(party))
        return info.get("employee_name"), info.get("image"), None

    if party_type == PARTY_TEMPORARY_WORKER:
        frappe.has_permission("Temporary Worker", "read", throw=True)
        _assert_party_in_scope(party_type, party)
        info = frappe.db.get_value(
            "Temporary Worker", party, ["worker_name", "expiry_date"], as_dict=True
        ) or {}
        if not info:
            frappe.throw(_("Temporary Worker {0} does not exist.").format(party))
        return info.get("worker_name"), None, info.get("expiry_date")

    frappe.throw(_("Unknown party type: {0}").format(party_type))

def _custody_balance(party) -> int:
    """Net custody articles still on a worker: issues less returns, cancelled rows
    excluded."""
    rows = frappe.get_all(
        "Accommodation Stock Ledger",
        filters={"item_type": "Custody Article", "employee": party, "is_cancelled": 0},
        fields=["signed_qty"],
    )
    return int(sum(int(r.signed_qty or 0) for r in rows))

def _masar_is_enabled(party_type, party) -> bool:
    """True only when the worker holds a token AND it is still enabled."""
    token = (
        frappe.db.get_value(
            "Masar Worker Token", {"party_type": party_type, "party": party},
            ["token", "enabled"], as_dict=True
        )
        or {}
    )
    return bool(token.get("token")) and bool(token.get("enabled"))

@frappe.whitelist()
def get_arrival_card(party_type=None, party=None, employee=None) -> dict:
    """Party-aware arrival snapshot for one worker (Employee or Temporary Worker)."""
    if not party and employee:
        party_type, party = PARTY_EMPLOYEE, employee
    if not (party_type and party):
        frappe.throw(_("party_type and party are required."))

    worker_name, image, tw_expiry = _arrival_identity(party_type, party)

    assignment = (
        frappe.db.get_value(
            "Housing Assignment",
            occupancy.active_assignment_filters(party_type=party_type, party=party),
            ["name", "project", "building", "bed", "check_in_date"],
            as_dict=True,
        )
        or {}
    )
    current_bed = assignment.get("bed")
    current_bed_code = (
        frappe.db.get_value("Bed", current_bed, "bed_code") if current_bed else None
    )

    custody_count = _custody_balance(party) if party_type == PARTY_EMPLOYEE else 0
    masar_enabled = _masar_is_enabled(party_type, party)

    return {
        "party_type": party_type,
        "party": party,
        "employee": party if party_type == PARTY_EMPLOYEE else None,
        "employee_name": worker_name,
        "worker_name": worker_name,
        "image": image,
        "project": assignment.get("project"),
        "current_building": assignment.get("building"),
        "current_bed": current_bed,
        "current_bed_code": current_bed_code,
        "check_in_date": (
            frappe.utils.formatdate(assignment.get("check_in_date")) if assignment.get("check_in_date") else None
        ),
        "has_housing": bool(current_bed),
        "custody_count": custody_count,
        "has_custody": bool(custody_count),
        "masar_enabled": masar_enabled,
        "masar_status": "issued" if masar_enabled else "pending",
        "expiry_date": frappe.utils.formatdate(tw_expiry) if tw_expiry else None,
        "expiry_days": _expiry_days(tw_expiry),
    }

def _housed_employees() -> set:
    """Every Employee holding a live bed, in any building.

    Deliberately unscoped, because the two axes this endpoint searches are excluded on
    different grounds. An Employee carries no building of their own, so the only question
    is whether they already hold a bed anywhere — offering one who is housed in another
    estate would name an out-of-estate worker AND propose a double assignment.
    """
    housed = frappe.get_all(
        "Housing Assignment",
        filters=occupancy.active_assignment_filters(),
        fields=["employee"],
    )
    return {h.employee for h in housed if h.employee}

def _housed_temporary_workers(restrict, allowed) -> set:
    """Temporary Workers holding a live bed inside the caller's estate.

    Scoped to match ``_temporary_worker_matches``, which filters the candidates on their
    own ``building`` field: a worker outside the estate is already absent from that list,
    so widening this read would exclude rows that were never offered.
    """
    filters = occupancy.active_assignment_filters(party_type="Temporary Worker")
    if restrict:
        filters["building"] = ["in", allowed]
    housed = frappe.get_all("Housing Assignment", filters=filters, fields=["party"])
    return {h.party for h in housed if h.party}

def _employee_matches(txt, excluded) -> list:
    """Active Employees matching the typed text who are not already housed.

    The exclusion is part of the QUERY, not a pass over its result: applied after the
    15-row limit it emptied the list whenever the first fifteen matches happened to be
    housed, and the desk was told there was nobody to house."""
    filters = {"status": "Active"}
    if excluded:
        filters["name"] = ["not in", sorted(excluded)]
    emps = frappe.get_all(
        "Employee",
        filters=filters,
        or_filters=(
            [["employee_name", "like", f"%{txt}%"], ["name", "like", f"%{txt}%"]] if txt else None
        ),
        fields=["name", "employee_name", "designation"],
        order_by="employee_name asc",
        limit_page_length=15,
    )
    return [
        {
            "party_type": PARTY_EMPLOYEE,
            "party": e.name,
            "label": e.employee_name or e.name,
            "sub": e.designation or e.name,
        }
        for e in emps
    ]

def _temporary_worker_matches(txt, restrict, allowed, housed_tw) -> list:
    """Active Temporary Workers matching the typed text (name, passport or id) who
    are not already housed, most recently touched first.

    Housed workers are excluded in the QUERY for the reason _employee_matches gives:
    dropping them from an already-limited page returns fewer rows than the page holds,
    and sometimes none at all.

    Dates are rendered with ``frappe.utils.formatdate``, a backwards-compatibility
    alias for ``format_date`` (frappe/utils/data.py:580); it applies the site's own
    date format, which a hand-built string cannot, so the desk shows one format
    everywhere the operator looks."""
    tw_filters = {"status": "Active"}
    if restrict:
        tw_filters["building"] = ["in", allowed]
    if housed_tw:
        tw_filters["name"] = ["not in", sorted(housed_tw)]
    tws = frappe.get_all(
        "Temporary Worker",
        filters=tw_filters,
        or_filters=(
            [
                ["worker_name", "like", f"%{txt}%"],
                ["passport_number", "like", f"%{txt}%"],
                ["name", "like", f"%{txt}%"],
            ]
            if txt
            else None
        ),
        fields=["name", "worker_name", "passport_number", "expiry_date"],
        order_by="modified desc",
        limit_page_length=15,
    )
    return [
        {
            "party_type": PARTY_TEMPORARY_WORKER,
            "party": t.name,
            "label": t.worker_name or t.name,
            "sub": _("Passport {0}").format(t.passport_number or "—"),
            "expiry_date": frappe.utils.formatdate(t.expiry_date) if t.expiry_date else None,
            "expiry_days": _expiry_days(t.expiry_date),
        }
        for t in tws
    ]

@frappe.whitelist()
def search_arrivals_workers(building=None, txt=None) -> list:
    """Combined worker lookup for the desk: registered Employees first, then active
    Temporary Workers, each tagged with ``party_type`` so the page can house either.
    Read-permission-gated per doctype (a user who cannot read a doctype gets none).

    The two axes are read SEPARATELY because they are scoped differently. An Employee is
    excluded when housed anywhere; a Temporary Worker is excluded when housed inside the
    caller's estate, which is the only place their own list can reach.
    """
    txt = (txt or "").strip()
    results = []

    restrict, allowed = permissions.report_building_scope(frappe.session.user)
    if restrict and not allowed:
        return []

    if frappe.has_permission("Employee", "read"):
        results += _employee_matches(txt, _housed_employees())

    if frappe.has_permission("Temporary Worker", "read"):
        results += _temporary_worker_matches(
            txt, restrict, allowed, _housed_temporary_workers(restrict, allowed)
        )

    return results

@frappe.whitelist(methods=["POST"])
def register_temporary_worker(
    worker_name,
    passport_number,
    nationality=None,
    labour_supplier=None,
    building=None,
    project=None,
    cell_number=None,
    iqama_number=None,
    batch_row=None,
) -> dict:
    """Register a passport-only new arrival as a Temporary Worker, returned pre-selected
    for housing. A housing supervisor may create a Temporary Worker but NEVER an
    Employee — the doctype is hard-coded and Employee creation is HRMS-gated.
    The Temporary Worker controller enforces its own rules (unique passport, the
    30/90-day window, expiry computation).

    ``batch_row`` (optional) is an Arrival Batch Worker manifest line tapped on the
    desk; on success its ``temporary_worker`` link is set so the manifest line ticks."""
    frappe.has_permission("Temporary Worker", "create", throw=True)
    doc = frappe.get_doc(
        {
            "doctype": "Temporary Worker",
            "worker_name": worker_name,
            "passport_number": passport_number,
            "nationality": nationality,
            "labour_supplier": labour_supplier,
            "building": building,
            "project": project,
            "cell_number": cell_number,
            "iqama_number": iqama_number,
        }
    )
    doc.insert()
    _link_manifest_row(batch_row, doc.name)
    return {
        "party_type": PARTY_TEMPORARY_WORKER,
        "party": doc.name,
        "label": doc.worker_name,
        "expiry_date": frappe.utils.formatdate(doc.expiry_date) if doc.expiry_date else None,
    }

def _link_manifest_row(batch_row, temporary_worker) -> None:
    """Tick a tapped Arrival Batch manifest line by linking it to the registered
    Temporary Worker. Permission-gated on the parent Arrival Batch; best-effort
    (a missing or already-linked row is a no-op, never blocks the registration)."""
    if not (batch_row and temporary_worker):
        return
    parent = frappe.db.get_value("Arrival Batch Worker", batch_row, "parent")
    if not parent:
        return
    if not frappe.has_permission("Arrival Batch", "write", doc=parent):
        return
    frappe.db.set_value("Arrival Batch Worker", batch_row, "temporary_worker", temporary_worker)

_MRZ_NATIONALITY = {
    "IND": "Indian",
    "PAK": "Pakistani",
    "BGD": "Bangladeshi",
    "NPL": "Nepali",
    "LKA": "Sri Lankan",
    "PHL": "Filipino",
    "EGY": "Egyptian",
    "SDN": "Sudanese",
    "YEM": "Yemeni",
    "IDN": "Indonesian",
    "ETH": "Ethiopian",
    "KEN": "Kenyan",
    "UGA": "Ugandan",
    "SAU": "Saudi",
}

def _mrz_yymmdd_to_date(value: str, is_expiry: bool) -> str | None:
    """Convert an MRZ ``YYMMDD`` field to an ISO ``YYYY-MM-DD`` date, or None.

    MRZ carries only a two-digit year. A birth date is always in the past; an
    expiry is always in the future — so the century is inferred from that, not
    guessed. Returns None on any non-numeric or out-of-range field rather than
    raising (a bad scan must degrade to manual entry, never error)."""
    import datetime

    value = (value or "").strip()
    if len(value) != 6 or not value.isdigit():
        return None
    yy, mm, dd = int(value[:2]), int(value[2:4]), int(value[4:6])
    if not (1 <= mm <= 12 and 1 <= dd <= 31):
        return None
    current_yy = frappe.utils.now_datetime().year % 100
    if is_expiry:
        century = 2000
    else:
        century = 2000 if yy <= current_yy else 1900
    try:
        return datetime.date(century + yy, mm, dd).isoformat()
    except ValueError:
        return None

def parse_mrz_text(text: str) -> dict:
    """Parse passport MRZ text into ``{worker_name, passport_number, nationality,
    expiry_date}``. Pure + deterministic — the testable core of the feature.

    Handles the TD3 passport format (two 44-char lines). Line 1 carries the issuing
    country and the name (``SURNAME<<GIVEN<NAMES``); line 2 the passport number,
    nationality, birth date, sex, and expiry. The scan is rarely perfect, so each
    field is extracted defensively and missing/garbled fields come back as None —
    the desk pre-fills what parsed and the supervisor confirms the rest. Returns
    only the keys that parsed (plus ``raw_lines`` for debugging)."""
    import re

    lines = [
        re.sub(r"[^A-Z0-9<]", "", ln.strip().upper())
        for ln in (text or "").splitlines()
        if ln.strip()
    ]
    mrz_lines = [ln for ln in lines if len(ln) >= 30 and "<" in ln]
    out: dict = {"raw_lines": mrz_lines}
    if len(mrz_lines) < 2:
        return out

    line1, line2 = mrz_lines[0], mrz_lines[1]

    name_part = line1
    m = re.match(r"^P[A-Z<]([A-Z]{3})(.*)$", line1)
    if m:
        out["nationality"] = _MRZ_NATIONALITY.get(m.group(1), m.group(1))
        name_part = m.group(2)
    if "<<" in name_part:
        surname, _, given = name_part.partition("<<")
        surname = surname.replace("<", " ").strip()
        given = given.replace("<", " ").strip()
        full = " ".join(p for p in (given, surname) if p)
        if full:
            out["worker_name"] = full

    passport_no = line2[:9].replace("<", "").strip()
    if passport_no:
        out["passport_number"] = passport_no
    if len(line2) >= 13 and "nationality" not in out:
        nat = line2[10:13].replace("<", "").strip()
        if nat:
            out["nationality"] = _MRZ_NATIONALITY.get(nat, nat)
    if len(line2) >= 27:
        expiry = _mrz_yymmdd_to_date(line2[21:27], is_expiry=True)
        if expiry:
            out["expiry_date"] = expiry
    return out

def _ocr_image_to_text(image: str) -> str | None:
    """Best-effort OCR of a base64 passport image to raw text, or None.

    The OCR engine is OPTIONAL and operator-provided: this tries the engines that
    might be installed on the bench (``pytesseract`` over Pillow) and returns None
    when none is available — at which point ``parse_passport`` reports that the
    OCR engine must be enabled, and the desk falls back to manual entry. Kept fully
    defensive so a missing dependency degrades gracefully rather than 500-ing."""
    import base64
    import io

    payload = image.split(",", 1)[1] if image.startswith("data:") and "," in image else image
    try:
        raw = base64.b64decode(payload)
    except Exception:
        return None

    try:
        import pytesseract
        from PIL import Image

        img = Image.open(io.BytesIO(raw))
        return pytesseract.image_to_string(img)
    except Exception:
        return None

@frappe.whitelist(methods=["POST"])
def parse_passport(image) -> dict:
    """Read a passport's MRZ from a captured image and return autofill fields.

    The Arrivals Desk camera-capture endpoint: feature-flagged by Habitat
    Settings ``enable_passport_mrz_ocr`` (a disabled flag returns
    ``ok=False, reason=disabled`` so the desk keeps manual entry). Permission-gated
    on create of Temporary Worker — the same right needed to register the arrival
    this autofills. Runs OCR on the supplied base64 image, then the deterministic
    MRZ parser, and returns ``{worker_name, passport_number, nationality,
    expiry_date}`` for the register form to pre-fill. Nothing is written and the
    image is not persisted; the supervisor reviews and submits the form. When no
    OCR engine is available it returns ``ok=False, reason=ocr_unavailable`` so the
    desk degrades to manual entry rather than erroring."""
    frappe.has_permission("Temporary Worker", "create", throw=True)
    if not frappe.db.get_single_value("Habitat Settings", "enable_passport_mrz_ocr"):
        return {"ok": False, "reason": "disabled"}

    image = (image or "").strip()
    if not image:
        frappe.throw(_("No image was captured."))

    text = _ocr_image_to_text(image)
    if text is None:
        return {"ok": False, "reason": "ocr_unavailable"}

    fields = parse_mrz_text(text)
    parsed = {
        k: fields.get(k)
        for k in ("worker_name", "passport_number", "nationality", "expiry_date")
        if fields.get(k)
    }
    return {"ok": bool(parsed), "fields": parsed}

@frappe.whitelist(methods=["POST"])
def house_over_capacity(room, party_type, party, project, check_in_date=None) -> dict:
    """House a worker beyond a full room's physical capacity by minting a TEMPORARY
    (virtual, ``is_temporary``) Accommodation Bed in the room and assigning to it.

    The building's over-capacity headroom is enforced by Accommodation
    Assignment.validate (building-level projected occupancy vs ``total_capacity``
    and ``over_capacity_allowed``). quick_check_in performs no intermediate commit,
    so when that gate rejects the assignment the whole request — including the
    just-minted bed — rolls back. ``total_capacity`` is a stored building field and
    is NOT inflated by the temporary bed, so the cap is measured against true
    capacity. Each worker still gets his own bed, so the assignment bed-lock and
    occupancy controllers are untouched.
    """
    from apex.habitat.api.front_desk import quick_check_in

    frappe.has_permission("Bed", "create", throw=True)
    if not frappe.db.exists("Room", room):
        frappe.throw(_("Room {0} does not exist.").format(room))

    n = frappe.db.count("Bed", {"room": room, "is_temporary": 1}) + 1
    bed = frappe.get_doc(
        {
            "doctype": "Bed",
            "room": room,
            "bed_code": f"{room}-OC{n}",
            "status": "Available",
            "is_temporary": 1,
        }
    )
    bed.insert()

    result = quick_check_in(
        bed=bed.name,
        party_type=party_type,
        party=party,
        project=project,
        check_in_date=check_in_date,
    )
    return {**result, "is_temporary": True, "bed_code": bed.bed_code}

def _arrival_supplier(arrival, tw_supplier):
    """Who supplied this arrival: a Temporary Worker's own labour supplier, or the
    supplier an externally-billed Employee is charged to. Neither means direct hire."""
    if arrival.party_type == PARTY_TEMPORARY_WORKER:
        return tw_supplier.get(arrival.party)
    if arrival.is_external_supplier:
        return arrival.billed_to_supplier
    return None

def _supplier_breakdown(arrivals) -> list:
    """Today's arrivals counted per supplier, biggest first, each named. Two bounded
    lookups regardless of how many arrivals there are."""
    tw_parties = [a.party for a in arrivals if a.party_type == PARTY_TEMPORARY_WORKER and a.party]
    tw_supplier = {}
    if tw_parties:
        for row in frappe.get_all(
            "Temporary Worker",
            filters={"name": ["in", list(set(tw_parties))]},
            fields=["name", "labour_supplier"],
        ):
            tw_supplier[row.name] = row.labour_supplier

    counts: dict[str | None, int] = {}
    for a in arrivals:
        sup = _arrival_supplier(a, tw_supplier)
        counts[sup] = counts.get(sup, 0) + 1

    sup_ids = [s for s in counts if s]
    sup_names = {}
    if sup_ids:
        for row in frappe.get_all(
            "Supplier", filters={"name": ["in", sup_ids]}, fields=["name", "supplier_name"]
        ):
            sup_names[row.name] = row.supplier_name

    return sorted(
        (
            {
                "supplier": s,
                "supplier_name": sup_names.get(s) if s else _("Direct / Company"),
                "count": c,
            }
            for s, c in counts.items()
        ),
        key=lambda r: r["count"],
        reverse=True,
    )

def _over_capacity_count(bed_ids) -> int:
    """How many of today's placements went onto a virtual over-capacity bed.

    ``frappe.db.count`` (frappe/database/database.py:1269) counts in the database
    rather than by the length of a fetched list, so a busy day does not pull every bed
    row into memory to be counted. The one thing it cannot do is apply row scope,
    which is safe here only because the bed ids were produced by an already-scoped
    read — never call this with client-supplied ids.
    """
    if not bed_ids:
        return 0
    return frappe.db.count("Bed", {"name": ["in", list(set(bed_ids))], "is_temporary": 1})

def _empty_arrival_summary(date, building):
    """The summary a scoped supervisor holding no building sees: zeroes, not the estate."""
    return {
        "date": date,
        "building": building,
        "housed_count": 0,
        "by_supplier": [],
        "over_capacity_count": 0,
        "manifest_expected": None,
        "manifest_completion_pct": None,
    }

def _manifest_progress(date, building_filter, housed_count):
    """``(expected, completion_pct)`` against the day's Arrival Batch manifests.
    Both are None when no manifest DocType is installed; the percentage is None when
    nothing was expected, since 0/0 is not 0%.

    ``building_filter`` is a filter VALUE, not a building name: one building, or the
    ``["in", [...]]`` the caller's building scope resolved to, or None for unscoped."""
    if not frappe.db.exists("DocType", "Arrival Batch"):
        return None, None
    batch_filters = {"expected_date": date}
    if building_filter:
        batch_filters["building"] = building_filter
    expected = 0
    for b in frappe.get_all("Arrival Batch", filters=batch_filters, fields=["expected_count"]):
        expected += int(b.get("expected_count") or 0)
    if not expected:
        return expected, None
    return expected, round(min(housed_count, expected) / expected * 100, 1)

@frappe.whitelist()
def get_arrival_summary(date=None, building=None) -> dict:
    """Read-only arrival telemetry for a manager strip / daily ops view.

    Returns, for ``date`` (default today) and an optional ``building`` scope:
    today's housed count, a by-supplier breakdown, manifest-completion %, and the
    over-capacity placement count. Built from a BOUNDED set of bulk queries (no
    per-row round trips), mirroring get_building_grid. Creates and locks nothing.

    ``building`` is OPTIONAL: when omitted, the scope comes from
    ``permissions.report_building_scope`` and is spliced into the filter explicitly, the
    same way dashboard.py does it, because ``frappe.get_all`` hardcodes
    ``ignore_permissions=True`` (frappe/__init__.py:2050) and the registered
    permission_query_conditions never runs here. Removing that splice would show a
    building-scoped supervisor the whole estate's housed count, per-supplier split,
    over-capacity placements and manifest expectation.
    """
    frappe.has_permission("Housing Assignment", "read", throw=True)
    if building:
        frappe.has_permission("Building", "read", doc=building, throw=True)
    date = date or frappe.utils.today()

    restrict, allowed = permissions.report_building_scope(
        frappe.session.user, doctype="Housing Assignment"
    )
    if building:
        building_filter = building
    elif restrict:
        if not allowed:
            return _empty_arrival_summary(date, building)
        building_filter = ["in", allowed]
    else:
        building_filter = None

    filters = {"check_in_date": date, "docstatus": 1}
    if building_filter:
        filters["building"] = building_filter
    arrivals = frappe.get_all(
        "Housing Assignment",
        filters=filters,
        fields=["name", "bed", "party_type", "party", "is_external_supplier", "billed_to_supplier"],
    )
    housed_count = len(arrivals)

    by_supplier = _supplier_breakdown(arrivals)
    over_capacity_count = _over_capacity_count([a.bed for a in arrivals if a.bed])
    manifest_expected, manifest_completion_pct = _manifest_progress(
        date, building_filter, housed_count
    )

    return {
        "date": date,
        "building": building,
        "housed_count": housed_count,
        "by_supplier": by_supplier,
        "over_capacity_count": over_capacity_count,
        "manifest_expected": manifest_expected,
        "manifest_completion_pct": manifest_completion_pct,
    }

def _empty_manifest(date, building=None):
    """The manifest with nothing on it: no Arrival Batch DocType, or no building in scope."""
    return {
        "date": date,
        "building": building,
        "workers": [],
        "total": 0,
        "arrived": 0,
        "housed": 0,
        "pending": 0,
    }

@frappe.whitelist()
def get_expected_arrivals(date=None, building=None) -> dict:
    """Today's pre-arrival manifest (Arrival Batch) for the Intake zone.

    Returns the expected workers for ``date`` (default today), optionally scoped to
    one ``building``, each flagged ``arrived`` once its row has been matched to a
    registered Temporary Worker (the batch row's ``temporary_worker`` link), and
    ``housed`` once that worker has an active Housing Assignment. Includes running
    registration and housing tallies. Read-only; bounded queries; the
    Arrival Batch DocType may not exist yet (returns an empty manifest then).

    ``building`` is OPTIONAL: when omitted, the scope is spliced into the filter
    explicitly, exactly as ``get_arrival_summary`` above does it, because neither
    registered scope primitive can reach this read. ``frappe.get_all`` hardcodes
    ``ignore_permissions=True`` (frappe/__init__.py:2050), so the
    ``permission_query_conditions`` fragment never runs, and the ``has_permission``
    hook is dispatched only from ``get_doc_permissions`` (frappe/permissions.py:206),
    which ``frappe.has_permission`` reaches only when it is given a doc — the
    type-level gate below passes none. Skipping the splice would hand a
    building-scoped supervisor every building's manifest for the date, each row
    carrying the expected worker's name, passport number and nationality."""
    date = date or frappe.utils.today()
    if not frappe.db.exists("DocType", "Arrival Batch"):
        return _empty_manifest(date, building)
    frappe.has_permission("Arrival Batch", "read", throw=True)
    if building:
        frappe.has_permission("Building", "read", doc=building, throw=True)

    restrict, allowed = permissions.report_building_scope(
        frappe.session.user, doctype="Arrival Batch"
    )
    filters = {"expected_date": date}
    if building:
        filters["building"] = building
    elif restrict:
        if not allowed:
            return _empty_manifest(date, building)
        filters["building"] = ["in", allowed]
    batches = frappe.get_all(
        "Arrival Batch", filters=filters, fields=["name", "building", "labour_supplier", "project"]
    )
    workers: list[dict] = []
    if batches:
        batch_meta = {b.name: b for b in batches}
        rows = frappe.get_all(
            "Arrival Batch Worker",
            filters={"parent": ["in", [b.name for b in batches]], "parenttype": "Arrival Batch"},
            fields=["name", "parent", "worker_name", "passport_number", "nationality", "temporary_worker"],
            order_by="idx asc",
        )
        registered_parties = [r.temporary_worker for r in rows if r.temporary_worker]
        housed_parties = set()
        if registered_parties:
            housed_parties = set(
                frappe.get_list(
                    "Housing Assignment",
                    filters=occupancy.active_assignment_filters(
                        party_type=PARTY_TEMPORARY_WORKER,
                        party=["in", registered_parties],
                    ),
                    pluck="party",
                )
            )
        for r in rows:
            b = batch_meta.get(r.parent)
            workers.append(
                {
                    "batch": r.parent,
                    "row": r.name,
                    "worker_name": r.worker_name,
                    "passport_number": r.passport_number,
                    "nationality": r.nationality,
                    "building": b.building if b else None,
                    "labour_supplier": b.labour_supplier if b else None,
                    "project": b.project if b else None,
                    "arrived": bool(r.temporary_worker),
                    "housed": r.temporary_worker in housed_parties,
                    "temporary_worker": r.temporary_worker,
                }
            )
    arrived = sum(1 for w in workers if w["arrived"])
    housed = sum(1 for w in workers if w.get("housed"))
    total = len(workers)
    return {
        "date": date,
        "building": building,
        "workers": workers,
        "total": total,
        "arrived": arrived,
        "housed": housed,
        "pending": total - arrived,
    }

@frappe.whitelist(methods=["POST"])
def get_arrival_slip(party_type, party) -> dict:
    """Render the on-demand arrival slip (HTML) for a housed worker. Reuses the
    party-aware get_arrival_card for identity + active housing, then renders the
    slip template; the desk opens the HTML in a print window.

    An Employee with an enabled Masar token gets his personal-link QR on the slip
    plus his designation; a Temporary Worker gets his passport / Iqama / nationality
    instead (and no QR — his Masar link issues only once he is registered)."""
    card = get_arrival_card(party_type=party_type, party=party)
    ctx = arrival_slips.slip_context(
        card.get("worker_name") or card.get("party"), party_type
    )
    ctx.update({
        "building": card.get("current_building") or "",
        "bed": card.get("current_bed_code") or card.get("current_bed") or "",
        "project": card.get("project") or "",
        "check_in_date": card.get("check_in_date") or "",
        "designation": None,
        "passport_number": None,
        "iqama_number": None,
        "nationality": None,
        "qr": None,
    })

    if party_type == PARTY_EMPLOYEE:
        ctx["designation"] = frappe.db.get_value("Employee", party, "designation")
        frappe.has_permission("Masar Worker Token", "read", throw=True)
        link = reshare_worker_link(party)
        if link:
            ctx["qr"] = masar_qr_data_uri(link)
    elif party_type == PARTY_TEMPORARY_WORKER:
        frappe.has_permission("Temporary Worker", "read", throw=True)
        _assert_party_in_scope(party_type, party)
        tw = (
            frappe.db.get_value(
                "Temporary Worker", party, ["passport_number", "iqama_number", "nationality"], as_dict=True
            )
            or {}
        )
        ctx["passport_number"] = tw.get("passport_number")
        ctx["iqama_number"] = tw.get("iqama_number")
        ctx["nationality"] = tw.get("nationality")

    return {
        "html": frappe.render_template(arrival_slips.ARRIVAL_SLIP_TEMPLATE, ctx),
        "title": ctx["worker_name"],
        "card": ctx,
    }

@frappe.whitelist()
def get_checkin_slip(party_type, party) -> dict:
    """Render the accommodation check-in acknowledgment slip (HTML) for a housed
    worker: identity + bed + project + check-in date, the standard housing terms,
    an acceptance line, and worker / supervisor signature lines. Reuses
    get_arrival_card for identity and reads the building address/city for the
    header. The desk opens the HTML in a print window."""
    from apex.apex_core.utils.addresses import get_address_text

    card = get_arrival_card(party_type=party_type, party=party)
    building = card.get("current_building")
    if building:
        frappe.has_permission("Building", "read", doc=building, throw=True)
    bldg = (
        frappe.db.get_value("Building", building, ["city"], as_dict=True)
        if building
        else None
    ) or {}
    address = get_address_text("Building", building)

    ctx = arrival_slips.slip_context(
        card.get("worker_name") or card.get("party"), party_type
    )
    ctx.update({
        "building": building or "",
        "address": address,
        "city": bldg.get("city") or "",
        "bed": card.get("current_bed_code") or card.get("current_bed") or "",
        "project": card.get("project") or "",
        "check_in_date": card.get("check_in_date") or "",
        "terms": arrival_slips.HOUSING_TERMS,
    })
    return {
        "html": frappe.render_template(arrival_slips.CHECKIN_SLIP_TEMPLATE, ctx),
        "title": ctx["worker_name"],
    }

def _custody_slip_items(doc):
    """``(items, show_uom)`` for the handover table. Article names and UOMs come
    from the master in ONE lookup; a line keeps its own captured name when the
    master has none, and the UOM column is dropped when no line carries one."""
    article_ids = list({row.article for row in doc.items if row.article})
    masters = {}
    if article_ids:
        for a in frappe.get_all(
            "Custody Article",
            filters={"name": ["in", article_ids]},
            fields=["name", "article_name", "unit_of_measure"],
        ):
            masters[a.name] = a

    items = []
    for row in doc.items:
        m = masters.get(row.article, {})
        items.append(
            {
                "article_name": row.article_name or m.get("article_name") or row.article,
                "qty": row.qty,
                "uom": m.get("unit_of_measure") or "",
            }
        )
    return items, any(it["uom"] for it in items)

@frappe.whitelist()
def get_custody_handover_slip(custody_issue) -> dict:
    """Render the custody-handover acknowledgment slip (HTML) for a Custody Issue:
    a line-item table (article, qty, UOM), an acknowledgment line, and worker /
    supervisor signature lines. Permission-gated on read of the specific Custody
    Issue. The desk opens the HTML in a print window."""
    frappe.has_permission("Custody Issue", "read", doc=custody_issue, throw=True)
    doc = frappe.get_doc("Custody Issue", custody_issue)
    if not doc.issued_to_employee:
        frappe.throw(_("This Custody Issue has no issued-to Employee; nothing to hand over."))

    worker_name = (
        frappe.db.get_value("Employee", doc.issued_to_employee, "employee_name")
        or doc.issued_to_name
        or doc.issued_to_employee
    )

    items, show_uom = _custody_slip_items(doc)

    ctx = arrival_slips.slip_context(worker_name)
    ctx.update({
        "custody_issue": doc.name,
        "building": doc.building or "",
        "issue_date": frappe.utils.formatdate(doc.issue_date) if doc.issue_date else "",
        "items": items,
        "show_uom": show_uom,
    })
    return {
        "html": frappe.render_template(arrival_slips.CUSTODY_HANDOVER_SLIP_TEMPLATE, ctx),
        "title": worker_name,
    }

@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def buildings_with_capacity(doctype, txt, searchfield, start, page_len, filters):
    """Link query for the Arrivals Desk building picker — only buildings that still
    have at least one available (green) bed.

    A standard Frappe Link query (the `get_query` contract) so the picker offers no
    full building. Scope mirrors ``front_desk.list_supervisor_buildings``: an
    unscoped oversight role sees every Active building, a building-scoped user only
    their User-Permission buildings, a scoped user with none sees nothing. Free-bed
    availability is computed from the same ``occupancy.bed_color`` rules as the board
    (one bounded bed/room aggregate, not a per-building round trip), so a building is
    offered only when its green-bed count is > 0.
    """
    scope = active_building_scope(frappe.session.user)
    if scope.filters is None:
        return []

    f = dict(scope.filters)
    if txt:
        f["building_name"] = ["like", f"%{txt}%"]

    buildings = frappe.get_all(
        "Building", filters=f, fields=["name", "building_name"]
    )
    if not buildings:
        return []
    building_names = [b.name for b in buildings]

    mix = occupancy.bed_mix(occupancy.bed_mix_rows(building_names), building_names)

    rows = [
        (b.name, b.building_name or b.name)
        for b in buildings
        if mix[b.name]["available"] > 0
    ]
    rows.sort(key=lambda r: str(r[1]))
    return rows[start : start + page_len] if page_len else rows
