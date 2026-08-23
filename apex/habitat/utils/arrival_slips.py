# Copyright (c) 2026, afmcoltd
"""The printable slips the Arrivals Desk hands a worker, and the header they share.

Three slips carry the same masthead — worker, company, date, text direction and
language — so the masthead is built once by ``slip_context`` and each endpoint adds
only the rows peculiar to it. The templates sit beside it so the print chrome (the
``@media print`` rule, the frame, the type) can be compared across all three at
once; each template still carries its own copy of that chrome.
"""

from __future__ import annotations

import frappe
from frappe import _

from apex.apex_core.utils.party_link import PARTY_EMPLOYEE, PARTY_TEMPORARY_WORKER


def slip_company() -> str:
    """The operating company for slip headers, via the shared Habitat resolver
    (explicit Habitat Settings company -> user default -> global default)."""
    from apex.apex_core.utils.company import resolve_company

    return resolve_company("Habitat") or ""


def slip_direction() -> str:
    """Text direction for a printed slip, from the boot/user language (rtl for ar*)."""
    lang = (frappe.local.lang or "en").lower()
    return "rtl" if lang.startswith("ar") else "ltr"


def party_type_label(party_type) -> str:
    """Translatable label for a raw party-type doctype name."""
    if party_type == PARTY_EMPLOYEE:
        return _("Employee")
    if party_type == PARTY_TEMPORARY_WORKER:
        return _("Temporary Worker")
    return party_type or ""


def slip_context(worker_name, party_type=None) -> dict:
    """The masthead every slip carries. ``party_type`` is omitted on slips that
    identify the worker by a document reference instead of a party.

    Dates are rendered with ``frappe.utils.formatdate``, an alias for ``format_date``
    (frappe/utils/data.py:580), so a printed slip carries the site's date format
    rather than one this module invents. The direction and language are read from
    ``frappe.local.lang``, because a slip printed from a background job has no request
    to infer them from.
    """
    ctx = {"worker_name": worker_name}
    if party_type is not None:
        ctx["party_type"] = party_type
        ctx["party_type_label"] = party_type_label(party_type)
    ctx["dir"] = slip_direction()
    ctx["lang"] = frappe.local.lang or "en"
    ctx["company"] = slip_company()
    ctx["today"] = frappe.utils.formatdate(frappe.utils.today())
    return ctx


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


HOUSING_TERMS = [
    frappe._lt("Keep the accommodation and shared areas clean and tidy."),
    frappe._lt("No unauthorised guests or visitors are allowed in the accommodation."),
    frappe._lt("Report any damage, fault, or maintenance issue to the supervisor immediately."),
    frappe._lt("Comply with all fire, safety, and security rules and posted instructions."),
    frappe._lt("Do not tamper with fire alarms, smoke detectors, or safety equipment."),
    frappe._lt("Hand back all issued custody items in good condition on checkout."),
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
      {% for term in terms %}<li>{{ term }}</li>{% endfor %}
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
