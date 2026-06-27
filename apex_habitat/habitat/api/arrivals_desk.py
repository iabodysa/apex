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
"""

from __future__ import annotations

import frappe
from frappe import _

from apex_habitat.apex_core.doctype.masar_worker_token.masar_worker_token import (
    _worker_link,
    masar_qr_data_uri,
)
from apex_habitat.habitat import permissions

PARTY_EMPLOYEE = "Employee"
PARTY_TEMPORARY_WORKER = "Temporary Worker"


def _expiry_days(expiry_date) -> int | None:
    """Whole days from today until a Temporary Worker's window expiry.

    Negative once the window has lapsed, ``0`` on the expiry day, ``None`` when
    no expiry is set. Computed server-side so the desk renders a single source of
    truth (no client-side date math)."""
    if not expiry_date:
        return None
    return frappe.utils.date_diff(expiry_date, frappe.utils.today())


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
    from apex_habitat.salis.api import messaging_gateway

    frappe.has_permission("Masar Worker Token", "read", throw=True)
    token = (
        frappe.db.get_value(
            "Masar Worker Token", {"employee": employee}, ["token", "enabled"], as_dict=True
        )
        or {}
    )
    if not token.get("token") or not token.get("enabled"):
        frappe.throw(_("This worker has no active Masar link yet. Create the QR first."))

    result = messaging_gateway.send_masar_link(
        employee, _worker_link(token["token"]), phone=phone
    )
    return {"gateway_configured": messaging_gateway.is_configured(), **result}


@frappe.whitelist()
def get_arrival_card(party_type=None, party=None, employee=None) -> dict:
    """Party-aware arrival snapshot for one worker (Employee or Temporary Worker)."""
    # [#e74n5x]
    if not party and employee:
        party_type, party = PARTY_EMPLOYEE, employee
    if not (party_type and party):
        frappe.throw(_("party_type and party are required."))

    tw_expiry = None
    if party_type == PARTY_EMPLOYEE:
        frappe.has_permission("Employee", "read", throw=True)
        info = frappe.db.get_value("Employee", party, ["employee_name", "image"], as_dict=True) or {}
        if not info:
            frappe.throw(_("Employee {0} does not exist.").format(party))
        worker_name, image = info.get("employee_name"), info.get("image")
    elif party_type == PARTY_TEMPORARY_WORKER:
        frappe.has_permission("Temporary Worker", "read", throw=True)
        info = frappe.db.get_value(
            "Temporary Worker", party, ["worker_name", "expiry_date"], as_dict=True
        ) or {}
        if not info:
            frappe.throw(_("Temporary Worker {0} does not exist.").format(party))
        worker_name, image = info.get("worker_name"), None
        tw_expiry = info.get("expiry_date")
    else:
        frappe.throw(_("Unknown party type: {0}").format(party_type))

    # [#e8oxzs]
    assignment = (
        frappe.db.get_value(
            "Accommodation Assignment",
            {"party_type": party_type, "party": party, "docstatus": 1, "check_out_date": ["is", "not set"]},
            ["name", "project", "building", "bed", "check_in_date"],
            as_dict=True,
        )
        or {}
    )
    current_bed = assignment.get("bed")
    current_bed_code = (
        frappe.db.get_value("Accommodation Bed", current_bed, "bed_code") if current_bed else None
    )

    # [#rx0tdj]
    custody_count = 0
    if party_type == PARTY_EMPLOYEE:
        rows = frappe.get_all(
            "Accommodation Stock Ledger",
            filters={"item_type": "Custody Article", "employee": party, "is_cancelled": 0},
            fields=["qty"],
        )
        custody_count = int(sum(int(r.qty or 0) for r in rows))

    token = (
        frappe.db.get_value(
            "Masar Worker Token", {"party_type": party_type, "party": party}, ["token", "enabled"], as_dict=True
        )
        or {}
    )
    masar_enabled = bool(token.get("token")) and bool(token.get("enabled"))

    return {
        "party_type": party_type,
        "party": party,
        "employee": party if party_type == PARTY_EMPLOYEE else None,  # [#nzy15g]
        "employee_name": worker_name,  # [#nzy15g]
        "worker_name": worker_name,
        "image": image,
        "project": assignment.get("project"),
        "current_building": assignment.get("building"),
        "current_bed": current_bed,
        "current_bed_code": current_bed_code,
        # [#g5e2pw]
        "check_in_date": (
            frappe.utils.formatdate(assignment.get("check_in_date")) if assignment.get("check_in_date") else None
        ),
        "has_housing": bool(current_bed),
        "custody_count": custody_count,
        "has_custody": bool(custody_count),
        "masar_enabled": masar_enabled,
        "masar_status": "issued" if masar_enabled else "pending",
        # Temporary-window telemetry for the desk's expiry chip.
        "expiry_date": frappe.utils.formatdate(tw_expiry) if tw_expiry else None,
        "expiry_days": _expiry_days(tw_expiry),
    }


@frappe.whitelist()
def search_arrivals_workers(building=None, txt=None) -> list:
    """Combined worker lookup for the desk: registered Employees first, then active
    Temporary Workers, each tagged with ``party_type`` so the page can house either.
    Read-permission-gated per doctype (a user who cannot read a doctype gets none)."""
    txt = (txt or "").strip()
    results = []

    # [#wave-b2] get_all forces ignore_permissions, so the building row-scoping the
    # Accommodation Assignment / Temporary Worker lists get via
    # permission_query_conditions is bypassed here. Re-apply it report-side so a
    # building-scoped supervisor sees only their estates' workers; the oversight roles
    # in HOUSING_UNSCOPED_ROLES stay unrestricted. A scoped user with no allowed
    # building gets nothing.
    restrict, allowed = permissions.report_building_scope(frappe.session.user)
    if restrict and not allowed:
        return []

    # [#jibprz] The housed-exclusion set stays UNSCOPED: a worker housed in ANY
    # building must be excluded from the arrival-candidate lists (a worker already
    # housed elsewhere is not an arrival here). Scoping it would wrongly resurface
    # other-estate housed workers as available candidates.
    housed = frappe.get_all(
        "Accommodation Assignment",
        filters={"docstatus": 1, "check_out_date": ["is", "not set"]},
        fields=["party_type", "party", "employee"],
    )
    housed_emp = {h.employee for h in housed if h.employee}
    housed_tw = {h.party for h in housed if h.party_type == "Temporary Worker" and h.party}

    if frappe.has_permission("Employee", "read"):
        emps = frappe.get_all(
            "Employee",
            filters={"status": "Active"},
            or_filters=(
                [["employee_name", "like", f"%{txt}%"], ["name", "like", f"%{txt}%"]] if txt else None
            ),
            fields=["name", "employee_name", "designation"],
            order_by="employee_name asc",
            limit_page_length=15,
        )
        results += [
            {
                "party_type": PARTY_EMPLOYEE,
                "party": e.name,
                "label": e.employee_name or e.name,
                "sub": e.designation or e.name,
            }
            for e in emps
            if e.name not in housed_emp
        ]

    if frappe.has_permission("Temporary Worker", "read"):
        # [#wave-b2] Temporary Worker carries its own `building`; confine a scoped
        # supervisor's candidate list to their estates (Employee has no building
        # field — its other-estate housed rows are already removed by housed_emp).
        tw_filters = {"status": "Active"}
        if restrict:
            tw_filters["building"] = ["in", allowed]
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
        results += [
            {
                "party_type": PARTY_TEMPORARY_WORKER,
                "party": t.name,
                "label": t.worker_name or t.name,
                "sub": _("Passport {0}").format(t.passport_number or "—"),
                # So a search row can flag a worker whose window is closing/lapsed.
                "expiry_date": frappe.utils.formatdate(t.expiry_date) if t.expiry_date else None,
                "expiry_days": _expiry_days(t.expiry_date),
            }
            for t in tws
            if t.name not in housed_tw
        ]

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
        "expiry_date": doc.expiry_date,
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


# Passport MRZ (machine-readable zone) autofill for the register sheet.
#
# The MRZ is the two/three fixed-width OCR-B lines at the foot of a passport. The
# PARSER below is pure, deterministic, and testable; the image->text OCR step is
# pluggable (an optional bench engine) so the heavy/optional dependency is wired
# by the operator, while the parse + the desk scaffold ship now. Feature-flagged
# by Habitat Settings.enable_passport_mrz_ocr; manual entry always remains.

# ISO 3166 alpha-3 -> human nationality, for the handful of labour-supply
# nationalities the desk sees most; an unmapped code passes through as the raw
# 3-letter code (still useful, never wrong).
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
    # A passport expiry is always 20xx (none are 19xx, and 21xx is decades off),
    # so the two-digit year maps straight onto the 2000s. A birth date is in the
    # past: this-century only if not future, else last century.
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

    # Keep only plausible MRZ characters and split into the long fixed-width lines.
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

    # Line 1: 'P<XXX' issuing-country prefix, then SURNAME<<GIVEN<NAMES.
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

    # Line 2: passport_no(9) check(1) nationality(3) dob(6) check(1) sex(1)
    #         expiry(6) check(1) ...
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
        import pytesseract  # optional, operator-installed
        from PIL import Image

        img = Image.open(io.BytesIO(raw))
        return pytesseract.image_to_string(img)
    except Exception:
        # No OCR engine on the bench (or it failed) — signal "unavailable".
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
        # Flag is on but no engine is wired — honest signal, manual entry stays.
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
    from apex_habitat.habitat.api.front_desk import quick_check_in

    frappe.has_permission("Accommodation Bed", "create", throw=True)
    if not frappe.db.exists("Accommodation Room", room):
        frappe.throw(_("Room {0} does not exist.").format(room))

    n = frappe.db.count("Accommodation Bed", {"room": room, "is_temporary": 1}) + 1
    bed = frappe.get_doc(
        {
            "doctype": "Accommodation Bed",
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


@frappe.whitelist()
def get_arrival_summary(date=None, building=None) -> dict:
    """Read-only arrival telemetry for a manager strip / daily ops view.

    Returns, for ``date`` (default today) and an optional ``building`` scope:
    today's housed count, a by-supplier breakdown, manifest-completion %, and the
    over-capacity placement count. Built from a BOUNDED set of bulk queries (no
    per-row round trips), mirroring get_building_grid. Creates and locks nothing.
    """
    frappe.has_permission("Accommodation Assignment", "read", throw=True)
    if building:
        frappe.has_permission("Accommodation Building", "read", doc=building, throw=True)
    date = date or frappe.utils.today()

    filters = {"check_in_date": date, "docstatus": 1}
    if building:
        filters["building"] = building
    arrivals = frappe.get_all(
        "Accommodation Assignment",
        filters=filters,
        fields=["name", "bed", "party_type", "party", "is_external_supplier", "billed_to_supplier"],
    )
    housed_count = len(arrivals)

    # Resolve each arrival's supplier in bulk: Temporary Worker -> labour_supplier,
    # external-billed Employee -> billed_to_supplier, else Direct.
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
        if a.party_type == PARTY_TEMPORARY_WORKER:
            sup = tw_supplier.get(a.party)
        elif a.is_external_supplier:
            sup = a.billed_to_supplier
        else:
            sup = None
        counts[sup] = counts.get(sup, 0) + 1

    sup_ids = [s for s in counts if s]
    sup_names = {}
    if sup_ids:
        for row in frappe.get_all(
            "Supplier", filters={"name": ["in", sup_ids]}, fields=["name", "supplier_name"]
        ):
            sup_names[row.name] = row.supplier_name
    by_supplier = sorted(
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

    # Over-capacity placements = today's arrivals housed in a minted is_temporary
    # bed (house_over_capacity), counted via one bulk bed lookup.
    bed_ids = [a.bed for a in arrivals if a.bed]
    over_capacity_count = 0
    if bed_ids:
        over_capacity_count = frappe.db.count(
            "Accommodation Bed", {"name": ["in", list(set(bed_ids))], "is_temporary": 1}
        )

    # Manifest completion needs the pre-arrival manifest source (Arrival Batch).
    # Until that DocType lands it is unmeasurable -> report None, never fake.
    manifest_completion_pct = None
    manifest_expected = None
    if frappe.db.exists("DocType", "Arrival Batch"):
        batch_filters = {"expected_date": date}
        if building:
            batch_filters["building"] = building
        expected = 0
        for b in frappe.get_all("Arrival Batch", filters=batch_filters, fields=["expected_count"]):
            expected += int(b.get("expected_count") or 0)
        manifest_expected = expected
        if expected:
            manifest_completion_pct = round(min(housed_count, expected) / expected * 100, 1)

    return {
        "date": date,
        "building": building,
        "housed_count": housed_count,
        "by_supplier": by_supplier,
        "over_capacity_count": over_capacity_count,
        "manifest_expected": manifest_expected,
        "manifest_completion_pct": manifest_completion_pct,
    }


@frappe.whitelist()
def get_expected_arrivals(date=None, building=None) -> dict:
    """Today's pre-arrival manifest (Arrival Batch) for the Intake zone.

    Returns the expected workers for ``date`` (default today), optionally scoped to
    one ``building``, each flagged ``arrived`` once its row has been matched to a
    registered Temporary Worker (the batch row's ``temporary_worker`` link), plus a
    running ``arrived``/``pending``/``total`` tally. Read-only; bounded queries; the
    Arrival Batch DocType may not exist yet (returns an empty manifest then)."""
    if not frappe.db.exists("DocType", "Arrival Batch"):
        return {"date": date or frappe.utils.today(), "workers": [], "total": 0, "arrived": 0, "pending": 0}
    frappe.has_permission("Arrival Batch", "read", throw=True)
    if building:
        frappe.has_permission("Accommodation Building", "read", doc=building, throw=True)
    date = date or frappe.utils.today()

    filters = {"expected_date": date}
    if building:
        filters["building"] = building
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
                    # Matched to a registered arrival -> this manifest line is ticked.
                    "arrived": bool(r.temporary_worker),
                    "temporary_worker": r.temporary_worker,
                }
            )
    arrived = sum(1 for w in workers if w["arrived"])
    total = len(workers)
    return {
        "date": date,
        "building": building,
        "workers": workers,
        "total": total,
        "arrived": arrived,
        "pending": total - arrived,
    }


# [#6vab3q]


def _company_name() -> str:
    """The operating company for slip headers: prefer the Habitat Settings single,
    fall back to the global default company."""
    return (
        frappe.db.get_single_value("Habitat Settings", "company")
        or frappe.defaults.get_global_default("company")
        or ""
    )


def _slip_dir() -> str:
    """Text direction for a printed slip, from the boot/user language (rtl for ar*)."""
    lang = (frappe.local.lang or "en").lower()
    return "rtl" if lang.startswith("ar") else "ltr"


def _party_type_label(party_type) -> str:
    """Translatable label for a raw party-type doctype name."""
    if party_type == PARTY_EMPLOYEE:
        return _("Employee")
    if party_type == PARTY_TEMPORARY_WORKER:
        return _("Temporary Worker")
    return party_type or ""


ARRIVAL_SLIP_TEMPLATE = """
<div class="ax-slip" dir="{{ dir }}" lang="{{ lang }}" style="font-family: Arial, Helvetica, sans-serif; max-width: 480px; margin: 24px auto;
            border: 1px solid #ccc; border-radius: 8px; padding: 24px; color:#1a1a2e;">
  <h2 style="color:#1a1a2e; margin:0 0 4px;">{{ _("Arrival Slip") }}</h2>
  <div style="color:#555; font-size:12px; margin-bottom:16px;">{{ company | e }} &middot; {{ today | e }}</div>
  <table style="width:100%; font-size:14px; border-collapse:collapse;">
    <tr><td style="padding:4px 0; color:#555;">{{ _("Worker") }}</td><td style="padding:4px 0; font-weight:bold;">{{ worker_name | e }}</td></tr>
    <tr><td style="padding:4px 0; color:#555;">{{ _("Type") }}</td><td style="padding:4px 0;">{{ party_type_label | e }}</td></tr>
    {% if designation %}<tr><td style="padding:4px 0; color:#555;">{{ _("Designation") }}</td><td style="padding:4px 0;">{{ designation | e }}</td></tr>{% endif %}
    {% if passport_number %}<tr><td style="padding:4px 0; color:#555;">{{ _("Passport") }}</td><td style="padding:4px 0;">{{ passport_number | e }}</td></tr>{% endif %}
    {% if iqama_number %}<tr><td style="padding:4px 0; color:#555;">{{ _("Iqama") }}</td><td style="padding:4px 0;">{{ iqama_number | e }}</td></tr>{% endif %}
    {% if nationality %}<tr><td style="padding:4px 0; color:#555;">{{ _("Nationality") }}</td><td style="padding:4px 0;">{{ nationality | e }}</td></tr>{% endif %}
    <tr><td style="padding:4px 0; color:#555;">{{ _("Building") }}</td><td style="padding:4px 0;">{{ building | e }}</td></tr>
    <tr><td style="padding:4px 0; color:#555;">{{ _("Bed") }}</td><td style="padding:4px 0; font-weight:bold;">{{ bed | e }}</td></tr>
    <tr><td style="padding:4px 0; color:#555;">{{ _("Project") }}</td><td style="padding:4px 0;">{{ project | e }}</td></tr>
    {% if check_in_date %}<tr><td style="padding:4px 0; color:#555;">{{ _("Check-in") }}</td><td style="padding:4px 0;">{{ check_in_date | e }}</td></tr>{% endif %}
  </table>
  {% if qr %}<div style="margin-top:16px;"><img src="{{ qr }}" style="width:120px;height:120px"></div>{% endif %}
  <style>@media print { body { margin:0; } .ax-slip { border:none; margin:0; max-width:none; } }</style>
</div>
"""


@frappe.whitelist()
def get_arrival_slip(party_type, party) -> dict:
    """Render the on-demand arrival slip (HTML) for a housed worker. Reuses the
    party-aware get_arrival_card for identity + active housing, then renders the
    slip template; the desk opens the HTML in a print window.

    An Employee with an enabled Masar token gets his personal-link QR on the slip
    plus his designation; a Temporary Worker gets his passport / Iqama / nationality
    instead (and no QR — his Masar link issues only once he is registered)."""
    card = get_arrival_card(party_type=party_type, party=party)
    ctx = {
        "worker_name": card.get("worker_name") or card.get("party"),
        "party_type": party_type,
        "party_type_label": _party_type_label(party_type),
        "dir": _slip_dir(),
        "lang": frappe.local.lang or "en",
        "building": card.get("current_building") or "",
        "bed": card.get("current_bed_code") or card.get("current_bed") or "",
        "project": card.get("project") or "",
        "check_in_date": card.get("check_in_date") or "",
        "company": _company_name(),
        "today": frappe.utils.formatdate(frappe.utils.today()),
        "designation": None,
        "passport_number": None,
        "iqama_number": None,
        "nationality": None,
        "qr": None,
    }

    if party_type == PARTY_EMPLOYEE:
        ctx["designation"] = frappe.db.get_value("Employee", party, "designation")
        frappe.has_permission("Masar Worker Token", "read", throw=True)
        token = (
            frappe.db.get_value("Masar Worker Token", {"employee": party}, ["token", "enabled"], as_dict=True)
            or {}
        )
        if token.get("token") and token.get("enabled"):
            ctx["qr"] = masar_qr_data_uri(_worker_link(token.get("token")))
    elif party_type == PARTY_TEMPORARY_WORKER:
        frappe.has_permission("Temporary Worker", "read", throw=True)
        tw = (
            frappe.db.get_value(
                "Temporary Worker", party, ["passport_number", "iqama_number", "nationality"], as_dict=True
            )
            or {}
        )
        ctx["passport_number"] = tw.get("passport_number")
        ctx["iqama_number"] = tw.get("iqama_number")
        ctx["nationality"] = tw.get("nationality")

    return {"html": frappe.render_template(ARRIVAL_SLIP_TEMPLATE, ctx), "title": ctx["worker_name"]}


# [#25mjhm]
HOUSING_TERMS = [
    "Keep the accommodation and shared areas clean and tidy.",
    "No unauthorised guests or visitors are allowed in the accommodation.",
    "Report any damage, fault, or maintenance issue to the supervisor immediately.",
    "Comply with all fire, safety, and security rules and posted instructions.",
    "Do not tamper with fire alarms, smoke detectors, or safety equipment.",
    "Hand back all issued custody items in good condition on checkout.",
]


CHECKIN_SLIP_TEMPLATE = """
<div class="ax-slip" dir="{{ dir }}" lang="{{ lang }}" style="font-family: Arial, Helvetica, sans-serif; max-width: 560px; margin: 24px auto;
            border: 1px solid #ccc; border-radius: 8px; padding: 24px; color:#1a1a2e;">
  <h2 style="color:#1a1a2e; margin:0 0 4px;">{{ _("Accommodation Check-in") }}</h2>
  <div style="color:#555; font-size:12px; margin-bottom:16px;">{{ company | e }} &middot; {{ today | e }}</div>
  <table style="width:100%; font-size:14px; border-collapse:collapse;">
    <tr><td style="padding:4px 0; color:#555;">{{ _("Worker") }}</td><td style="padding:4px 0; font-weight:bold;">{{ worker_name | e }}</td></tr>
    <tr><td style="padding:4px 0; color:#555;">{{ _("Type") }}</td><td style="padding:4px 0;">{{ party_type_label | e }}</td></tr>
    <tr><td style="padding:4px 0; color:#555;">{{ _("Building") }}</td><td style="padding:4px 0;">{{ building | e }}</td></tr>
    {% if address %}<tr><td style="padding:4px 0; color:#555;">{{ _("Address") }}</td><td style="padding:4px 0;">{{ address | e }}</td></tr>{% endif %}
    {% if city %}<tr><td style="padding:4px 0; color:#555;">{{ _("City") }}</td><td style="padding:4px 0;">{{ city | e }}</td></tr>{% endif %}
    <tr><td style="padding:4px 0; color:#555;">{{ _("Bed") }}</td><td style="padding:4px 0; font-weight:bold;">{{ bed | e }}</td></tr>
    <tr><td style="padding:4px 0; color:#555;">{{ _("Project") }}</td><td style="padding:4px 0;">{{ project | e }}</td></tr>
    {% if check_in_date %}<tr><td style="padding:4px 0; color:#555;">{{ _("Check-in") }}</td><td style="padding:4px 0;">{{ check_in_date | e }}</td></tr>{% endif %}
  </table>

  <div style="margin-top:20px; border:1px solid #ccc; border-radius:6px; padding:14px 18px;">
    <div style="font-weight:bold; margin-bottom:8px; color:#1a1a2e;">{{ _("Housing Terms & Conditions") }}</div>
    <ol style="margin:0; padding-inline-start:18px; color:#1a1a2e; font-size:13px; line-height:1.6;">
      {% for term in terms %}<li>{{ _(term) }}</li>{% endfor %}
    </ol>
  </div>

  <div style="margin-top:16px; font-size:13px; color:#1a1a2e;">
    {{ _("I have read and accept these terms and conditions.") }}
  </div>

  <table style="width:100%; margin-top:28px; font-size:13px; border-collapse:collapse;">
    <tr>
      <td style="padding-top:8px; border-top:1px solid #555; width:48%;">{{ _("Worker signature") }}</td>
      <td style="width:4%;"></td>
      <td style="padding-top:8px; border-top:1px solid #555; width:48%;">{{ _("Date") }}</td>
    </tr>
  </table>
  <table style="width:100%; margin-top:28px; font-size:13px; border-collapse:collapse;">
    <tr>
      <td style="padding-top:8px; border-top:1px solid #555; width:48%;">{{ _("Supervisor signature") }}</td>
      <td style="width:4%;"></td>
      <td style="padding-top:8px; border-top:1px solid #555; width:48%;">{{ _("Date") }}</td>
    </tr>
  </table>
  <style>@media print { body { margin:0; } .ax-slip { border:none; margin:0; max-width:none; } }</style>
</div>
"""


@frappe.whitelist()
def get_checkin_slip(party_type, party) -> dict:
    """Render the accommodation check-in acknowledgment slip (HTML) for a housed
    worker: identity + bed + project + check-in date, the standard housing terms,
    an acceptance line, and worker / supervisor signature lines. Reuses
    get_arrival_card for identity and reads the building address/city for the
    header. The desk opens the HTML in a print window."""
    from apex_habitat.apex_core.utils.addresses import get_address_text

    card = get_arrival_card(party_type=party_type, party=party)
    building = card.get("current_building")
    if building:
        # [#t07zu3]
        frappe.has_permission("Accommodation Building", "read", doc=building, throw=True)
    bldg = (
        frappe.db.get_value("Accommodation Building", building, ["city"], as_dict=True)
        if building
        else None
    ) or {}
    ctx = {
        "worker_name": card.get("worker_name") or card.get("party"),
        "party_type": party_type,
        "party_type_label": _party_type_label(party_type),
        "dir": _slip_dir(),
        "lang": frappe.local.lang or "en",
        "building": building or "",
        "address": get_address_text("Accommodation Building", building),
        "city": bldg.get("city") or "",
        "bed": card.get("current_bed_code") or card.get("current_bed") or "",
        "project": card.get("project") or "",
        "check_in_date": card.get("check_in_date") or "",
        "company": _company_name(),
        "today": frappe.utils.formatdate(frappe.utils.today()),
        "terms": HOUSING_TERMS,
    }
    return {"html": frappe.render_template(CHECKIN_SLIP_TEMPLATE, ctx), "title": ctx["worker_name"]}


CUSTODY_HANDOVER_SLIP_TEMPLATE = """
<div class="ax-slip" dir="{{ dir }}" lang="{{ lang }}" style="font-family: Arial, Helvetica, sans-serif; max-width: 600px; margin: 24px auto;
            border: 1px solid #ccc; border-radius: 8px; padding: 24px; color:#1a1a2e;">
  <h2 style="color:#1a1a2e; margin:0 0 4px;">{{ _("Custody Handover") }}</h2>
  <div style="color:#555; font-size:12px; margin-bottom:16px;">{{ company | e }} &middot; {{ today | e }}</div>
  <table style="width:100%; font-size:14px; border-collapse:collapse;">
    <tr><td style="padding:4px 0; color:#555;">{{ _("Issued to") }}</td><td style="padding:4px 0; font-weight:bold;">{{ worker_name | e }}</td></tr>
    <tr><td style="padding:4px 0; color:#555;">{{ _("Reference") }}</td><td style="padding:4px 0;">{{ custody_issue | e }}</td></tr>
    {% if building %}<tr><td style="padding:4px 0; color:#555;">{{ _("Building") }}</td><td style="padding:4px 0;">{{ building | e }}</td></tr>{% endif %}
    {% if issue_date %}<tr><td style="padding:4px 0; color:#555;">{{ _("Issue date") }}</td><td style="padding:4px 0;">{{ issue_date | e }}</td></tr>{% endif %}
  </table>

  <table style="width:100%; margin-top:18px; font-size:13px; border-collapse:collapse;">
    <thead>
      <tr style="border-bottom:1px solid #555; text-align:start;">
        <th style="padding:6px 4px; width:8%;">#</th>
        <th style="padding:6px 4px;">{{ _("Article") }}</th>
        <th style="padding:6px 4px; width:14%; text-align:end;">{{ _("Qty") }}</th>
        {% if show_uom %}<th style="padding:6px 4px; width:18%;">{{ _("UOM") }}</th>{% endif %}
      </tr>
    </thead>
    <tbody>
      {% for row in items %}
      <tr style="border-bottom:1px solid #ccc;">
        <td style="padding:6px 4px;">{{ loop.index }}</td>
        <td style="padding:6px 4px;">{{ row.article_name | e }}</td>
        <td style="padding:6px 4px; text-align:end;">{{ row.qty }}</td>
        {% if show_uom %}<td style="padding:6px 4px;">{{ row.uom | e }}</td>{% endif %}
      </tr>
      {% endfor %}
    </tbody>
  </table>

  <div style="margin-top:16px; font-size:13px; color:#1a1a2e;">
    {{ _("I acknowledge that I have received the above items in good condition.") }}
  </div>

  <table style="width:100%; margin-top:28px; font-size:13px; border-collapse:collapse;">
    <tr>
      <td style="padding-top:8px; border-top:1px solid #555; width:48%;">{{ _("Worker signature") }}</td>
      <td style="width:4%;"></td>
      <td style="padding-top:8px; border-top:1px solid #555; width:48%;">{{ _("Date") }}</td>
    </tr>
  </table>
  <table style="width:100%; margin-top:28px; font-size:13px; border-collapse:collapse;">
    <tr>
      <td style="padding-top:8px; border-top:1px solid #555; width:48%;">{{ _("Supervisor signature") }}</td>
      <td style="width:4%;"></td>
      <td style="padding-top:8px; border-top:1px solid #555; width:48%;">{{ _("Date") }}</td>
    </tr>
  </table>
  <style>@media print { body { margin:0; } .ax-slip { border:none; margin:0; max-width:none; } }</style>
</div>
"""


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

    # [#7oz3gh]
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
    show_uom = any(it["uom"] for it in items)

    ctx = {
        "worker_name": worker_name,
        "custody_issue": doc.name,
        "dir": _slip_dir(),
        "lang": frappe.local.lang or "en",
        "building": doc.building or "",
        "issue_date": frappe.utils.formatdate(doc.issue_date) if doc.issue_date else "",
        "company": _company_name(),
        "today": frappe.utils.formatdate(frappe.utils.today()),
        "items": items,
        "show_uom": show_uom,
    }
    return {"html": frappe.render_template(CUSTODY_HANDOVER_SLIP_TEMPLATE, ctx), "title": worker_name}
