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

PARTY_EMPLOYEE = "Employee"
PARTY_TEMPORARY_WORKER = "Temporary Worker"


@frappe.whitelist()
def get_arrival_card(party_type=None, party=None, employee=None) -> dict:
    """Party-aware arrival snapshot for one worker (Employee or Temporary Worker)."""
    # [#e74n5x]
    if not party and employee:
        party_type, party = PARTY_EMPLOYEE, employee
    if not (party_type and party):
        frappe.throw(_("party_type and party are required."))

    if party_type == PARTY_EMPLOYEE:
        frappe.has_permission("Employee", "read", throw=True)
        info = frappe.db.get_value("Employee", party, ["employee_name", "image"], as_dict=True) or {}
        if not info:
            frappe.throw(_("Employee {0} does not exist.").format(party))
        worker_name, image = info.get("employee_name"), info.get("image")
    elif party_type == PARTY_TEMPORARY_WORKER:
        frappe.has_permission("Temporary Worker", "read", throw=True)
        info = frappe.db.get_value("Temporary Worker", party, ["worker_name"], as_dict=True) or {}
        if not info:
            frappe.throw(_("Temporary Worker {0} does not exist.").format(party))
        worker_name, image = info.get("worker_name"), None
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
    }


@frappe.whitelist()
def search_arrivals_workers(building=None, txt=None) -> list:
    """Combined worker lookup for the desk: registered Employees first, then active
    Temporary Workers, each tagged with ``party_type`` so the page can house either.
    Read-permission-gated per doctype (a user who cannot read a doctype gets none)."""
    txt = (txt or "").strip()
    results = []

    # [#jibprz]
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
        tws = frappe.get_all(
            "Temporary Worker",
            filters={"status": "Active"},
            or_filters=(
                [
                    ["worker_name", "like", f"%{txt}%"],
                    ["passport_number", "like", f"%{txt}%"],
                    ["name", "like", f"%{txt}%"],
                ]
                if txt
                else None
            ),
            fields=["name", "worker_name", "passport_number"],
            order_by="modified desc",
            limit_page_length=15,
        )
        results += [
            {
                "party_type": PARTY_TEMPORARY_WORKER,
                "party": t.name,
                "label": t.worker_name or t.name,
                "sub": _("Passport {0}").format(t.passport_number or "—"),
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
) -> dict:
    """Register a passport-only new arrival as a Temporary Worker, returned pre-selected
    for housing. A housing supervisor may create a Temporary Worker but NEVER an
    Employee — the doctype is hard-coded and Employee creation is HRMS-gated.
    The Temporary Worker controller enforces its own rules (unique passport, the
    30/90-day window, expiry computation)."""
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
    return {
        "party_type": PARTY_TEMPORARY_WORKER,
        "party": doc.name,
        "label": doc.worker_name,
        "expiry_date": doc.expiry_date,
    }


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


# [#6vab3q]


def _company_name() -> str:
    """The operating company for slip headers: prefer the Habitat Settings single,
    fall back to the global default company."""
    return (
        frappe.db.get_single_value("Habitat Settings", "company")
        or frappe.defaults.get_global_default("company")
        or ""
    )


ARRIVAL_SLIP_TEMPLATE = """
<div class="ax-slip" style="font-family: Arial, Helvetica, sans-serif; max-width: 480px; margin: 24px auto;
            border: 1px solid #ccc; border-radius: 8px; padding: 24px; color:#1a1a2e;">
  <h2 style="color:#1a1a2e; margin:0 0 4px;">Arrival Slip</h2>
  <div style="color:#555; font-size:12px; margin-bottom:16px;">{{ company }} &middot; {{ today }}</div>
  <table style="width:100%; font-size:14px; border-collapse:collapse;">
    <tr><td style="padding:4px 0; color:#555;">Worker</td><td style="padding:4px 0; font-weight:bold;">{{ worker_name }}</td></tr>
    <tr><td style="padding:4px 0; color:#555;">Type</td><td style="padding:4px 0;">{{ party_type }}</td></tr>
    {% if designation %}<tr><td style="padding:4px 0; color:#555;">Designation</td><td style="padding:4px 0;">{{ designation }}</td></tr>{% endif %}
    {% if passport_number %}<tr><td style="padding:4px 0; color:#555;">Passport</td><td style="padding:4px 0;">{{ passport_number }}</td></tr>{% endif %}
    {% if iqama_number %}<tr><td style="padding:4px 0; color:#555;">Iqama</td><td style="padding:4px 0;">{{ iqama_number }}</td></tr>{% endif %}
    {% if nationality %}<tr><td style="padding:4px 0; color:#555;">Nationality</td><td style="padding:4px 0;">{{ nationality }}</td></tr>{% endif %}
    <tr><td style="padding:4px 0; color:#555;">Building</td><td style="padding:4px 0;">{{ building }}</td></tr>
    <tr><td style="padding:4px 0; color:#555;">Bed</td><td style="padding:4px 0; font-weight:bold;">{{ bed }}</td></tr>
    <tr><td style="padding:4px 0; color:#555;">Project</td><td style="padding:4px 0;">{{ project }}</td></tr>
    {% if check_in_date %}<tr><td style="padding:4px 0; color:#555;">Check-in</td><td style="padding:4px 0;">{{ check_in_date }}</td></tr>{% endif %}
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
<div class="ax-slip" style="font-family: Arial, Helvetica, sans-serif; max-width: 560px; margin: 24px auto;
            border: 1px solid #ccc; border-radius: 8px; padding: 24px; color:#1a1a2e;">
  <h2 style="color:#1a1a2e; margin:0 0 4px;">Accommodation Check-in</h2>
  <div style="color:#555; font-size:12px; margin-bottom:16px;">{{ company }} &middot; {{ today }}</div>
  <table style="width:100%; font-size:14px; border-collapse:collapse;">
    <tr><td style="padding:4px 0; color:#555;">Worker</td><td style="padding:4px 0; font-weight:bold;">{{ worker_name }}</td></tr>
    <tr><td style="padding:4px 0; color:#555;">Type</td><td style="padding:4px 0;">{{ party_type }}</td></tr>
    <tr><td style="padding:4px 0; color:#555;">Building</td><td style="padding:4px 0;">{{ building }}</td></tr>
    {% if address %}<tr><td style="padding:4px 0; color:#555;">Address</td><td style="padding:4px 0;">{{ address }}</td></tr>{% endif %}
    {% if city %}<tr><td style="padding:4px 0; color:#555;">City</td><td style="padding:4px 0;">{{ city }}</td></tr>{% endif %}
    <tr><td style="padding:4px 0; color:#555;">Bed</td><td style="padding:4px 0; font-weight:bold;">{{ bed }}</td></tr>
    <tr><td style="padding:4px 0; color:#555;">Project</td><td style="padding:4px 0;">{{ project }}</td></tr>
    {% if check_in_date %}<tr><td style="padding:4px 0; color:#555;">Check-in</td><td style="padding:4px 0;">{{ check_in_date }}</td></tr>{% endif %}
  </table>

  <div style="margin-top:20px; border:1px solid #ccc; border-radius:6px; padding:14px 18px;">
    <div style="font-weight:bold; margin-bottom:8px; color:#1a1a2e;">Housing Terms &amp; Conditions</div>
    <ol style="margin:0; padding-left:18px; color:#1a1a2e; font-size:13px; line-height:1.6;">
      {% for term in terms %}<li>{{ term }}</li>{% endfor %}
    </ol>
  </div>

  <div style="margin-top:16px; font-size:13px; color:#1a1a2e;">
    I have read and accept these terms and conditions.
  </div>

  <table style="width:100%; margin-top:28px; font-size:13px; border-collapse:collapse;">
    <tr>
      <td style="padding-top:8px; border-top:1px solid #555; width:48%;">Worker signature</td>
      <td style="width:4%;"></td>
      <td style="padding-top:8px; border-top:1px solid #555; width:48%;">Date</td>
    </tr>
  </table>
  <table style="width:100%; margin-top:28px; font-size:13px; border-collapse:collapse;">
    <tr>
      <td style="padding-top:8px; border-top:1px solid #555; width:48%;">Supervisor signature</td>
      <td style="width:4%;"></td>
      <td style="padding-top:8px; border-top:1px solid #555; width:48%;">Date</td>
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
<div class="ax-slip" style="font-family: Arial, Helvetica, sans-serif; max-width: 600px; margin: 24px auto;
            border: 1px solid #ccc; border-radius: 8px; padding: 24px; color:#1a1a2e;">
  <h2 style="color:#1a1a2e; margin:0 0 4px;">Custody Handover</h2>
  <div style="color:#555; font-size:12px; margin-bottom:16px;">{{ company }} &middot; {{ today }}</div>
  <table style="width:100%; font-size:14px; border-collapse:collapse;">
    <tr><td style="padding:4px 0; color:#555;">Issued to</td><td style="padding:4px 0; font-weight:bold;">{{ worker_name }}</td></tr>
    <tr><td style="padding:4px 0; color:#555;">Reference</td><td style="padding:4px 0;">{{ custody_issue }}</td></tr>
    {% if building %}<tr><td style="padding:4px 0; color:#555;">Building</td><td style="padding:4px 0;">{{ building }}</td></tr>{% endif %}
    {% if issue_date %}<tr><td style="padding:4px 0; color:#555;">Issue date</td><td style="padding:4px 0;">{{ issue_date }}</td></tr>{% endif %}
  </table>

  <table style="width:100%; margin-top:18px; font-size:13px; border-collapse:collapse;">
    <thead>
      <tr style="border-bottom:1px solid #555; text-align:left;">
        <th style="padding:6px 4px; width:8%;">#</th>
        <th style="padding:6px 4px;">Article</th>
        <th style="padding:6px 4px; width:14%; text-align:right;">Qty</th>
        {% if show_uom %}<th style="padding:6px 4px; width:18%;">UOM</th>{% endif %}
      </tr>
    </thead>
    <tbody>
      {% for row in items %}
      <tr style="border-bottom:1px solid #ccc;">
        <td style="padding:6px 4px;">{{ loop.index }}</td>
        <td style="padding:6px 4px;">{{ row.article_name }}</td>
        <td style="padding:6px 4px; text-align:right;">{{ row.qty }}</td>
        {% if show_uom %}<td style="padding:6px 4px;">{{ row.uom }}</td>{% endif %}
      </tr>
      {% endfor %}
    </tbody>
  </table>

  <div style="margin-top:16px; font-size:13px; color:#1a1a2e;">
    I acknowledge that I have received the above items in good condition.
  </div>

  <table style="width:100%; margin-top:28px; font-size:13px; border-collapse:collapse;">
    <tr>
      <td style="padding-top:8px; border-top:1px solid #555; width:48%;">Worker signature</td>
      <td style="width:4%;"></td>
      <td style="padding-top:8px; border-top:1px solid #555; width:48%;">Date</td>
    </tr>
  </table>
  <table style="width:100%; margin-top:28px; font-size:13px; border-collapse:collapse;">
    <tr>
      <td style="padding-top:8px; border-top:1px solid #555; width:48%;">Supervisor signature</td>
      <td style="width:4%;"></td>
      <td style="padding-top:8px; border-top:1px solid #555; width:48%;">Date</td>
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
        "building": doc.building or "",
        "issue_date": frappe.utils.formatdate(doc.issue_date) if doc.issue_date else "",
        "company": _company_name(),
        "today": frappe.utils.formatdate(frappe.utils.today()),
        "items": items,
        "show_uom": show_uom,
    }
    return {"html": frappe.render_template(CUSTODY_HANDOVER_SLIP_TEMPLATE, ctx), "title": worker_name}
