# Copyright (c) 2026, AFMCO and contributors
"""Logistay Invoice Generator - component assembler + fail-closed issue gates (P-191).

Custom code is deliberately thin (native-first): stock ERPNext Sales Invoice
computes every amount/tax/total, the procured KSA/ZATCA e-invoice app fills the
``inv_zatca_*`` fields, and the stock statutory 15% VAT template supplies the
rate. This module owns only the three things the stock stack cannot express:

  1. ``present_set_targets`` - the D8 present-set filter: which of the up-to-4
     documents a client actually receives, driven by Component Routing Rule
     (never code).
  2. ``naming_matches`` - the pre-issue naming gate: the built legal name + VAT
     must equal the Client Name Registry (exact, or trim/case/whitespace only -
     never fuzzy).
  3. ``enforce_issuance_gate`` - the DoA/SoD issue gate wired to the shared
     P-193 ``enforce_gate`` service, FAIL-CLOSED: any unresolved authority,
     unconfigured band, SoD violation, missing registry, or an unavailable
     governance service BLOCKS the Sales Invoice submit. No amount is ever
     written here.

Wiring (integrator, hooks.py doc_events):
    "Sales Invoice": {"before_submit": "apex.logistay.invoice_assembly.enforce_issuance_gate"}
"""

from __future__ import annotations

import frappe
from frappe import _

# Components that never get their own invoice - they ride on the main timesheet
# document (spec FOUR-DOC-SPLIT: gosi_fee + charge_fee ride on main).
_RIDER_COMPONENTS = {"gosi_fee", "charge_fee"}


def present_set_targets(rules, fired_components):
    """D8 present-set filter (pure, side-effect free).

    ``rules`` - iterable of Component Routing Rule dicts, each with keys
        ``inv_component`` / ``inv_target_document`` / ``inv_is_enabled`` /
        ``inv_rides_on``.
    ``fired_components`` - the components that actually fired this period (from
        the POSTED Reconciliation Run; ``eos`` only when a transfer event fired).

    Returns ``{target_document: [component, ...]}`` for the documents to produce -
    only components that are BOTH enabled in the routing rule AND fired this
    period. Riders (gosi_fee / charge_fee, or any rule with
    ``inv_rides_on == 'main_timesheet'``) collapse onto ``main_timesheet``
    instead of spawning their own document.
    """
    fired = set(fired_components or ())
    targets: dict[str, list] = {}
    for rule in rules:
        component = rule.get("inv_component")
        if not rule.get("inv_is_enabled"):
            continue  # D8: an unenabled component is not part of this client's set
        if component not in fired:
            continue  # never bill a component that did not fire this period
        rides_on = rule.get("inv_rides_on") or "own_document"
        if component in _RIDER_COMPONENTS or rides_on == "main_timesheet":
            target = "main_timesheet"
        else:
            target = rule.get("inv_target_document") or "main_timesheet"
        targets.setdefault(target, []).append(component)
    return targets


def naming_matches(required_legal, required_vat, built_legal, built_vat, match_rule="exact"):
    """Naming gate (pure). ``exact`` = byte-for-byte; ``normalized`` = trim / case /
    whitespace only. Never fuzzy."""
    if match_rule == "normalized":
        def _norm(value):
            return " ".join((value or "").split()).casefold()

        return _norm(required_legal) == _norm(built_legal) and _norm(required_vat) == _norm(built_vat)
    return (required_legal or "") == (built_legal or "") and (required_vat or "") == (built_vat or "")


def enforce_issuance_gate(doc, method=None):
    """``before_submit`` doc_event on stock Sales Invoice (integrator wires it).

    Only Logistay-assembled invoices (those carrying ``inv_assembly_run``) are
    gated; a plain ERPNext Sales Invoice is out of scope and passes through
    unchanged. FAIL-CLOSED throughout - anything unresolved BLOCKS the submit.
    """
    assembly = doc.get("inv_assembly_run")
    if not assembly:
        return  # not a Logistay-assembled invoice; leave stock behaviour untouched

    # D4 - eos is event-triggered only: an eos line MUST carry its transfer ref.
    if doc.get("inv_component_type") == "eos" and not doc.get("inv_eos_transfer_ref"):
        frappe.throw(_("EOS invoice requires a sponsorship-transfer reference (event-triggered only)."))

    run = frappe.db.get_value(
        "Invoice Assembly Run",
        assembly,
        ["inv_client", "inv_prepared_by"],
        as_dict=True,
    ) or frappe._dict()

    _naming_gate(doc, run.get("inv_client"))
    _doa_gate(doc, run.get("inv_prepared_by"))


def _naming_gate(doc, client):
    """Built legal name + VAT must equal the Client Name Registry before issue.
    A missing registry = cannot verify = FAIL-CLOSED (held)."""
    registry = None
    if client:
        registry = frappe.db.get_value(
            "Client Name Registry",
            {"inv_client": client},
            ["inv_required_legal_name", "inv_required_vat_reg", "inv_match_rule"],
            as_dict=True,
        )
    if not registry:
        frappe.throw(_("No Client Name Registry for this client; issuance held (fail-closed)."))
    if not naming_matches(
        registry.get("inv_required_legal_name"),
        registry.get("inv_required_vat_reg"),
        doc.get("customer_name"),
        doc.get("tax_id"),
        registry.get("inv_match_rule") or "exact",
    ):
        frappe.throw(_("Client legal name / VAT does not match the Client Name Registry; issuance held."))


def _doa_gate(doc, preparer):
    """Resolve the DoA band through the shared P-193 governance service, FAIL-CLOSED.

    ``enforce_gate`` raises on a SoD violation, an unconfigured band, or unknown
    authority; an unavailable governance service is treated as unresolved and
    also blocks. Only an explicit ALLOW clears the invoice for issue."""
    doc.inv_doa_status = "authority_unknown"
    try:
        from apex.logistay_governance.enforce_gate import enforce_gate
    except Exception:
        frappe.throw(_("Governance gate unavailable; invoice issuance blocked (fail-closed)."))
    enforce_gate(
        entity="Sales Invoice",
        entity_id=doc.name,
        action="invoice_issuance",
        amount=doc.get("grand_total"),
        preparer=preparer,
        approver=frappe.session.user,
    )
    doc.inv_doa_status = "within_authority"
