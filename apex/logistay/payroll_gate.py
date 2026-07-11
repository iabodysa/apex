# Copyright (c) 2026, AFMCO and contributors
"""Shared payroll gates for P-192 (Logistay Payroll + WPS).

Two chokepoints live here so the rule lives ONCE:

1. ``additional_salary_validate`` - the HARD maker-checker consent gate. A stock
   Additional Salary of type Deduction that carries a P-192 ``pay_category`` cannot
   save unless a verified, in-window, within-cap Deduction Consent is linked. The
   consent record is the reused apex_core ``Employee Deduction Acknowledgment``,
   extended with ``pay_*`` custom fields. Category 8 (iqama-renewal-recharge) is held
   closed until the D9 legality flag on the Salary Deduction Policy is set.

2. ``enforce_release_gate`` + IBAN helpers - the WPS-COMPLETE precondition and the
   P-193 DoA release gate, invoked by the Payroll Run controller.

No real value (cap amount, IBAN, DoA threshold, worker name) is embedded; only the
structural rules. The IBAN check is a pure format rule.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt, getdate

# Category-8 (iqama-renewal-recharge) is HELD until the D9 legality decision is seeded.
IQAMA_RECHARGE_CATEGORY = "Iqama Renewal Recharge"
CONSENT_DOCTYPE = "Employee Deduction Acknowledgment"

# Payroll Run states at or beyond which slips exist and money can flow; every one of
# these requires a RECEIVED deduction declaration for the period. States BEFORE this
# set (Draft / Declaration Requested / Declaration Received) do not build slips yet.
SLIP_BUILD_STATES = frozenset(
    {
        "Slips Built",
        "Consent Checked",
        "Netted",
        "Awaiting Approval",
        "WPS Generated",
        "Released",
        "Confirmed",
    }
)


def valid_sa_iban(iban: str | None) -> bool:
    """Pure SA IBAN format check (fail-closed). No real IBAN is stored anywhere.

    A Saudi IBAN is ``SA`` followed by 22 digits (24 chars total). Anything else -
    including a missing value - is invalid, which blocks the WPS release.
    """
    value = (iban or "").replace(" ", "").upper()
    return len(value) == 24 and value[:2] == "SA" and value[2:].isdigit()


def employee_iban(employee: str | None) -> str | None:
    """Read the worker IBAN (PII, seeded out-of-repo) off the stock Employee."""
    if not employee:
        return None
    return frappe.db.get_value("Employee", employee, "iban")


def additional_salary_validate(doc, method=None) -> None:
    """doc_events hook on stock Additional Salary. Enforces the consent gate."""
    if (doc.type or "").strip() != "Deduction":
        return
    # Only P-192 payroll-category deductions route through this gate; other
    # Deduction-type Additional Salary (e.g. structure components) is untouched.
    if not getattr(doc, "pay_category", None):
        return
    _block_held_category(doc)
    _apply_component_routing(doc)
    _require_verified_consent(doc)


def _block_held_category(doc) -> None:
    if doc.pay_category == IQAMA_RECHARGE_CATEGORY:
        cleared = frappe.db.get_single_value("Salary Deduction Policy", "pay_category_8_legal_cleared")
        if not cleared:
            frappe.throw(
                _("Iqama-renewal-recharge deductions are held pending the legal-clearance decision.")
            )


def _require_verified_consent(doc) -> None:
    if not doc.pay_consent:
        frappe.throw(_("A verified Deduction Consent is required before this deduction can post."))
    consent = frappe.get_doc(CONSENT_DOCTYPE, doc.pay_consent)

    # Verified = submitted, internally approved, and worker consent captured.
    if consent.docstatus != 1 or consent.approval_status != "Approved" or not consent.consent_given:
        frappe.throw(_("The linked Deduction Consent is not verified and approved."))

    # Maker-checker: whoever obtained the consent cannot be its verifier.
    if consent.pay_obtained_by and consent.pay_verified_by and consent.pay_obtained_by == consent.pay_verified_by:
        frappe.throw(_("Deduction Consent must be verified by someone other than who obtained it."))

    # Effective-dated: an out-of-window consent authorizes nothing.
    ref_date = getdate(doc.payroll_date or frappe.utils.today())
    if consent.pay_valid_from and ref_date < getdate(consent.pay_valid_from):
        frappe.throw(_("The Deduction Consent is not yet in effect for this pay date."))
    if consent.pay_valid_to and ref_date > getdate(consent.pay_valid_to):
        frappe.throw(_("The Deduction Consent has expired for this pay date."))

    # Category parity between the consent and the deduction being applied.
    if consent.pay_category and doc.pay_category and consent.pay_category != doc.pay_category:
        frappe.throw(_("The Deduction Consent category does not match this deduction."))

    # Within cap: the acknowledged amount bounds what may be withheld.
    if consent.pay_cap_amount and flt(doc.amount) > flt(consent.pay_cap_amount):
        frappe.throw(_("The deduction amount exceeds the amount the worker consented to."))


def requires_declaration(status) -> bool:
    """True when the Payroll Run status is at/after slip-build, so a RECEIVED
    deduction declaration is a precondition. Pure lookup, no bench needed."""
    return status in SLIP_BUILD_STATES


def enforce_declaration_gate(status, declaration_received: bool) -> None:
    """Slips are held until the period's Deduction Declaration is RECEIVED.

    Silence is never clear: a missing declaration, or one still only 'requested',
    blocks every state from Slips Built onward. States before slip-build pass through.
    Pure decision (status + a resolved boolean) so it is unit-testable off-bench; the
    controller supplies the boolean via a DB lookup.
    """
    if requires_declaration(status) and not declaration_received:
        frappe.throw(
            _("Slips are held until the period's deduction declaration is received.")
        )


def route_deduction_component(component, routing_map, held=None):
    """Resolve which HRMS Salary Component a numbered deduction component posts as.

    The D-taxonomy numbers each operational deduction component; each routes to a
    stock HRMS Salary Component. ``routing_map`` is that map as DATA (seeded
    out-of-repo / read from ``Salary Deduction Type Rule.salary_component``) - no
    component->component pair is hardcoded here. Example (data): ``{7: "Loan
    Repayment"}`` routes component #7 (advance / loan recovery) onto the stock Loan
    Repayment component.

    ``held`` is the set of components withheld from payroll (e.g. #8
    iqama-renewal-recharge, held until the D9 legal decision). A held component routes
    NOWHERE and returns ``None``. A non-held component with no mapping is a
    configuration error and fails closed.
    """
    if held and component in held:
        return None
    target = routing_map.get(component) if routing_map else None
    if not target:
        frappe.throw(
            _("No salary-component routing is configured for deduction component {0}.").format(
                component
            )
        )
    return target


def _load_deduction_routing():
    """Build the deduction routing map + held set from committed DATA.

    Source is the ``Salary Deduction Policy`` Single and its ``type_rules`` child
    rows (``Salary Deduction Type Rule``). Each enabled row with a target contributes
    one ``category -> Salary Component`` pair; a disabled row's category is HELD. No
    pair is hardcoded here - every pair is a DB value seeded out-of-repo. Category-8
    (iqama-renewal-recharge) is additionally held until its D9 legal flag is set.
    """
    routing_map: dict = {}
    held: set = set()
    policy = frappe.get_cached_doc("Salary Deduction Policy")
    for row in policy.get("type_rules") or []:
        category = row.deduction_type
        if not category:
            continue
        if row.enabled and row.salary_component:
            routing_map[category] = row.salary_component
        else:
            held.add(category)
    if not policy.get("pay_category_8_legal_cleared"):
        held.add(IQAMA_RECHARGE_CATEGORY)
    return routing_map, held


def _apply_component_routing(doc) -> None:
    """Route a P-192 deduction onto its target HRMS Salary Component (the real wiring).

    An ``Additional Salary`` of type Deduction is the row HRMS pulls onto a Salary
    Slip; its ``salary_component`` is what that slip line posts as. So resolving it
    here IS resolving the slip deduction's component. Only categories the policy
    governs (mapped or held) are touched - anything else keeps the chosen component,
    so non-P-192 structure deductions and un-seeded categories are never disturbed. A
    mapped category has its component overwritten with the routed target; a held
    category routes NOWHERE (``_block_held_category`` stops it posting).
    """
    routing_map, held = _load_deduction_routing()
    category = doc.pay_category
    if category not in routing_map and category not in held:
        return
    target = route_deduction_component(category, routing_map, held)
    if target and getattr(doc, "salary_component", None) != target:
        doc.salary_component = target


def enforce_release_gate(run) -> None:
    """Resolve the P-193 DoA gate for a WPS release. Fails closed.

    P-193 is integrated AFTER P-192; until its shared service is importable, a
    release is blocked rather than allowed by default.
    """
    try:
        from apex.logistay_governance.enforce_gate import enforce_gate  # P-193, wired at integration
    except ImportError:
        frappe.throw(_("WPS release governance (P-193) is not available yet; release is blocked."))
        return

    verdict = enforce_gate(
        run.name,
        "wps_release",
        run.pay_total_net,
        run.pay_prepared_by,
        run.pay_approved_by,
    )
    if verdict != "ALLOW":
        frappe.throw(_("WPS release blocked by governance: {0}").format(verdict))
