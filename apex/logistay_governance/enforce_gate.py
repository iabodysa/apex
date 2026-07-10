# Copyright (c) 2026, AFMCO and contributors
"""Shared governance service — DoA / SoD / Audit / Export.

The one place the DoA + SoD + audit + export rules live, so the Reconciliation
(P-190), Invoice (P-191) and Payroll (P-192) engines all resolve authority
IDENTICALLY. Those engines carry the call-site fields (preparer/approver, band,
status); this module supplies the resolver they invoke.

Three public functions:

* ``enforce_gate`` — the DoA + SoD gate. HARD-BLOCKS (raises) on any SoD violation
  or unresolved authority; on ALLOW it writes a ``doa_approve`` Audit Event.
* ``write_audit`` — append one immutable Audit Event.
* ``gate_export`` — the privacy gate at the export boundary; fail-closed.

Fail-closed is the invariant everywhere: an unconfigured band, ambiguous authority,
or an unscanned export BLOCKS. Nothing here defaults to allow, and no real DoA
value lives in this file — bands are seeded out-of-repo.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt, getdate, now_datetime, nowdate

# The out-of-repo V2 leak scanner. It is a governance tool that does NOT live in
# this repo; wiring it (and closing its A4 coverage gaps: SA-IBAN pattern /
# ungrouped amount / PDF+xlsx content) is an integrator step. Until then any
# third-audience export is treated as UNSCANNED = fail-closed.
SCANNER = "scan_output_leak.py"


# --------------------------------------------------------------------------- #
# DoA + SoD gate                                                              #
# --------------------------------------------------------------------------- #
def enforce_gate(
    entity: str,
    entity_id: str,
    action: str,
    amount: float,
    preparer: str,
    approver: str,
    on_date: str | None = None,
) -> str:
    """Return ``"ALLOW"`` or raise. ``action`` is a DoA Band ``gov_action``.

    STEP 1 SoD: preparer must differ from approver, AND the preparer and approver
    role-sets must be DISJOINT over the action's controlling roles (SOD-ROLE-DISJOINT,
    A6) — a shared controlling role is a violation even for two distinct users.
    STEP 2 BAND: resolve to exactly one active DoA Band or BLOCK (fail-closed).
    STEP 3 ROLE: the approver must hold the band's required role or its escalation
    role — never an auto-approve.
    STEP 4: write a ``doa_approve`` Audit Event with the band + SoD pair.
    """
    on_date = getdate(on_date or nowdate())

    # STEP 1a — maker != checker.
    if preparer == approver:
        _sod_block(entity, entity_id, preparer, approver)
        frappe.throw(
            _("[SoD-VIOLATION] The preparer and the approver must be different users."),
            title=_("SoD Violation"),
        )

    # STEP 1b — SOD-ROLE-DISJOINT: no shared controlling role between the two.
    controlling = _controlling_roles(action)
    shared = set(frappe.get_roles(preparer)) & set(frappe.get_roles(approver)) & controlling
    if shared:
        _sod_block(entity, entity_id, preparer, approver)
        frappe.throw(
            _("[SoD-VIOLATION] The preparer and the approver share a controlling role: {0}.").format(
                ", ".join(sorted(shared))
            ),
            title=_("SoD Violation"),
        )

    # STEP 2 — resolve to exactly one active band (raises on unconfigured/ambiguous).
    band_name = _resolve_band(entity, entity_id, action, amount, on_date)
    band = frappe.get_cached_doc("DoA Band", band_name)

    # STEP 3 — approver must hold the band role or the escalation role.
    approver_roles = set(frappe.get_roles(approver))
    holds_band = band.gov_required_role in approver_roles
    holds_escalation = bool(band.gov_escalates_to) and band.gov_escalates_to in approver_roles
    if not (holds_band or holds_escalation):
        write_audit(
            entity, entity_id, "doa_block", None,
            subject_key="governance.authority.role_missing", doa_band=band_name,
            sod_pair=f"{preparer}::{approver}",
        )
        frappe.throw(
            _("[authority_unknown] The approver holds neither the required role nor the escalation role for this band."),
            title=_("DoA Block"),
        )

    # STEP 4 — record the approval.
    write_audit(
        entity, entity_id, "doa_approve", approver,
        subject_key="governance.authority.approved", doa_band=band_name,
        sod_pair=f"{preparer}::{approver}",
    )
    return "ALLOW"


def _controlling_roles(action: str) -> set[str]:
    """The role-set that governs ``action`` = every required/escalation role across
    that action's active DoA Bands. SoD role-disjointness is judged against this set.
    Reads config only (no PII), so get_all's permission bypass is acceptable here.
    """
    roles: set[str] = set()
    for band in frappe.get_all(
        "DoA Band",
        filters={"gov_action": action, "gov_active": 1},
        fields=["gov_required_role", "gov_escalates_to"],
    ):
        if band.gov_required_role:
            roles.add(band.gov_required_role)
        if band.gov_escalates_to:
            roles.add(band.gov_escalates_to)
    return roles


def _resolve_band(entity: str, entity_id: str, action: str, amount: float, on_date) -> str:
    """Resolve (action x amount x date) to exactly ONE active band name, or BLOCK.

    Fail-closed distinctions:
    * no band exists for the action at all -> ``doa_band_unconfigured``
    * bands exist but none / more-than-one match -> ``authority_unknown``
    Never returns a default approver.
    """
    configured = frappe.get_all("DoA Band", filters={"gov_action": action}, limit=1)
    if not configured:
        write_audit(
            entity, entity_id, "doa_block", None,
            subject_key="governance.authority.unconfigured",
        )
        frappe.throw(
            _("[doa_band_unconfigured] No DoA Band is configured for action {0}.").format(action),
            title=_("DoA Block"),
        )

    matches: list[str] = []
    for band in frappe.get_all(
        "DoA Band",
        filters={"gov_action": action, "gov_active": 1, "gov_effective_from": ["<=", on_date]},
        fields=["name", "gov_amount_from", "gov_amount_to", "gov_effective_to"],
    ):
        if band.gov_effective_to and getdate(band.gov_effective_to) < on_date:
            continue
        if flt(amount) < flt(band.gov_amount_from):
            continue
        # A blank upper bound is the open-ended top band.
        if band.gov_amount_to and flt(amount) > flt(band.gov_amount_to):
            continue
        matches.append(band.name)

    if not matches:
        write_audit(
            entity, entity_id, "doa_block", None,
            subject_key="governance.authority.unknown",
        )
        frappe.throw(
            _("[authority_unknown] Amount {0} falls outside every active DoA Band for {1}.").format(
                amount, action
            ),
            title=_("DoA Block"),
        )
    if len(matches) > 1:
        write_audit(
            entity, entity_id, "doa_block", None,
            subject_key="governance.authority.ambiguous",
        )
        frappe.throw(
            _("[authority_unknown] Amount {0} resolves to multiple active DoA Bands for {1}.").format(
                amount, action
            ),
            title=_("DoA Block"),
        )
    return matches[0]


def _sod_block(entity: str, entity_id: str, preparer: str, approver: str) -> None:
    write_audit(
        entity, entity_id, "sod_block", None,
        subject_key="governance.sod.violation", sod_pair=f"{preparer}::{approver}",
    )


# --------------------------------------------------------------------------- #
# Immutable audit                                                             #
# --------------------------------------------------------------------------- #
def write_audit(
    entity: str,
    entity_id: str,
    action: str,
    by: str | None,
    before: str | None = None,
    after: str | None = None,
    subject_key: str | None = None,
    doa_band: str | None = None,
    sod_pair: str | None = None,
) -> str:
    """Append one immutable Audit Event and return its name.

    A verbal/WhatsApp trigger with no in-system actor (``by`` is falsy) is tagged
    ``unverified_trigger`` and is NOT recorded as a real approval.
    """
    event = frappe.new_doc("Audit Event")
    event.gov_entity = entity
    event.gov_entity_id = entity_id
    event.gov_action = action
    event.gov_by = by or None
    event.gov_at = now_datetime()
    event.gov_before = before
    event.gov_after = after
    event.gov_subject_key = subject_key or ("unverified_trigger" if not by else None)
    event.gov_doa_band = doa_band
    event.gov_sod_pair = sod_pair
    # System-written governance record: insert past DocPerm, but the append-only
    # controller still blocks any later edit/delete.
    event.insert(ignore_permissions=True)
    return event.name


# --------------------------------------------------------------------------- #
# Export privacy gate                                                         #
# --------------------------------------------------------------------------- #
def gate_export(
    file_ref: str,
    audience: str,
    scanned_by: str | None = None,
    scanner_args: str | None = None,
) -> str:
    """Scan an export at the boundary. Return ``"pass"`` or raise (export HELD).

    owner_internal is informational (never blocked). employee/client/external must
    PASS the V2 scanner; an unavailable scanner or unsupported format is UNSCANNED
    = fail-closed (A4), never an implicit pass.
    """
    scan = frappe.new_doc("Export Leak Scan")
    scan.gov_export_ref = file_ref
    scan.gov_audience = audience
    scan.gov_scanner = SCANNER
    scan.gov_scanner_args = scanner_args
    scan.gov_scanned_by = scanned_by or frappe.session.user
    scan.gov_scanned_at = now_datetime()

    if audience == "owner_internal":
        scan.gov_verdict = "pass"
        scan.insert(ignore_permissions=True)
        return "pass"

    verdict, findings = _run_scanner(file_ref, audience, scanner_args)
    scan.gov_verdict = verdict
    scan.gov_findings = findings
    scan.insert(ignore_permissions=True)

    if verdict != "pass":
        write_audit(
            "Export Leak Scan", scan.name, "export_block", scan.gov_scanned_by,
            subject_key="governance.export.blocked",
        )
        frappe.throw(
            _("[export_leak_blocked] Export to {0} is held: {1}").format(
                audience, findings or _("unscanned (fail-closed)")
            ),
            title=_("Export Blocked"),
        )
    return "pass"


def _run_scanner(file_ref: str, audience: str, scanner_args: str | None):
    """Invoke the out-of-repo V2 scanner. It is NOT wired in this repo, so the
    honest structural default is UNSCANNED = fail-closed. The integrator replaces
    this body with the real ``scan_output_leak.py`` call once the tool is present
    and its A4 coverage gaps are closed.
    """
    return ("blocked", "scan_output_leak.py is not wired in this environment; fail-closed")
