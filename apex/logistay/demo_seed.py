# Copyright (c) 2026, AFMCO and contributors
"""Genericized end-to-end Logistay demo seeder (bench-executable).

Stands up ONE synthetic, coherent Logistay scenario and then EXERCISES every
committed engine that actually runs, stamping inspectable output records into
the Desk. It exists so the owner can SEE the rate / reconciliation / payroll /
governance engines working end-to-end on a demo bench.

    bench --site <site> execute apex.logistay.demo_seed.make_logistay_demo
    bench --site <site> execute apex.logistay.demo_seed.clear_logistay_demo

GENERICIZED — ZERO real AFMCO data. Every value here is an obviously-fake round
number or a name containing "Demo" (client, site, workers, rate value, IBAN,
DoA band). This mirrors the owner's rule: the COMMITTED demo carries only
synthetic structure; REAL rate tables / IBANs / establishments / client names
are seeded separately, OUT of the repo, never here.

WHAT IT DEMONSTRATES (real engine functions, not reimplementations):
  * Timesheet engine    - ``timesheet_engine.post_timesheet_ledger`` posts an
                          immutable Timesheet Ledger row per COMPLETE line.
  * Rate resolver       - ``rate_resolver.resolve_from_card`` converts a seeded
                          card value to a per-day rate under the div_31 basis and
                          the snapshot is written to a Rate Resolution.
  * Reconciliation      - a Reconciliation Run emits a client-side Billable Line
                          and worker-side Payable Lines off the SAME resolution;
                          ``reconciliation_engine.guard_basis_consistent`` and
                          ``should_apply_thresholds`` run on the real controller.
  * Payroll gates       - ``payroll_gate.enforce_declaration_gate`` (declaration),
                          ``route_deduction_component`` (component-7 Loan-Repayment
                          routing / #8 held), ``valid_sa_iban`` (consent format),
                          and the real ``additional_salary_validate`` consent
                          chokepoint firing on an unconsented deduction.
  * Governance          - ``logistay_governance.enforce_gate`` resolves a synthetic
                          DoA Band + SoD pair to ALLOW and writes an Audit Event;
                          a maker==checker call is shown fail-closed.
  * WPS SIF (partial)   - ``wps_sif.build_wps_sif`` / ``sif_reconciles`` grouped
                          over SYNTHETIC slip dicts (real Salary Slips are HRMS).
  * Invoice (partial)   - ``invoice_assembly.present_set_targets`` / ``naming_matches``
                          run pure; the ZATCA submit gate is SKIPPED (needs the
                          procured KSA e-invoice app + a Sales Invoice).

WHAT IT SKIPS (and says so, never fakes):
  * Sales Invoice ZATCA issuance leg  - needs the uninstalled procured KSA/ZATCA
    e-invoice app + Client Name Registry; ``enforce_issuance_gate`` is not driven.
  * Real Salary Slip generation       - external HRMS payroll; only the SIF
    grouping is demonstrated over synthetic slip dicts.

Idempotent: every record is get-or-created by a stable demo key, so a re-run
adds nothing. ``clear_logistay_demo`` removes exactly what this module creates
(using raw deletes for the append-only Rate Resolution / Audit Event ledgers,
which refuse a normal trash).
"""

from __future__ import annotations

from decimal import Decimal

import frappe
from frappe.utils import now_datetime, today

from apex.logistay import invoice_assembly, wps_sif
from apex.logistay.payroll_gate import (
    additional_salary_validate,
    enforce_declaration_gate,
    requires_declaration,
    route_deduction_component,
    valid_sa_iban,
)
from apex.logistay.rate_resolver import resolve_from_card
from apex.logistay.reconciliation_engine import (
    guard_basis_consistent,
    should_apply_thresholds,
)
from apex.logistay.timesheet_engine import post_timesheet_ledger

# Synthetic constants — obviously-fake round numbers + "Demo" names ONLY.
TAG = "LGZY-DEMO"  # stable id prefix + clear() key

CLIENT_CODE = f"{TAG}-CLIENT"
CLIENT_NAME = "Demo Logistay Client"
SITE_NAME = "Demo Central Site"
SITE_CODE = "DEMO-BR1"
PERIOD_LABEL = f"{TAG}-2026-06"
PERIOD_MONTH = "2026-06"
PERIOD_START = "2026-06-01"
PERIOD_END = "2026-06-30"
CARD_NAME = f"{TAG}-delivery-v1"
RUN_NAME = f"{TAG}-2026-06-v1"

# Fake seeded monthly package value + div_31 basis -> day rate = 9300/31 = 300.00.
CARD_VALUE = 9300
DAY_RATE_BASIS = "div_31"
EXPECTED_DAY_RATE = Decimal("300.00")
PAYABLE_DAYS = 26
CYCLE_DAYS = 30

# Three synthetic temporary workers (passport-only arrivals).
WORKERS = (
    {"name": "Demo Worker Alpha", "passport": "DEMOPASS-A0001"},
    {"name": "Demo Worker Bravo", "passport": "DEMOPASS-B0002"},
    {"name": "Demo Worker Charlie", "passport": "DEMOPASS-C0003"},
)

# Governance fixture — a synthetic role/band/users, obviously fake.
GOV_ROLE = "LGZY Demo Approver"
GOV_ACTION = "reconciliation_post"
GOV_PREPARER = "demo.preparer@logistay.example"
GOV_APPROVER = "demo.approver@logistay.example"

# Planted synthetic SA-IBAN: 'SA' + 22 identical digits. NOT a real account.
PLANTED_IBAN = "SA" + "7" * 22


def _log(report: list, line: str) -> None:
    report.append(line)
    print(line)


def _goc(doctype: str, key: dict, make: dict):
    """Get-or-create by a stable key; returns the record name."""
    name = frappe.db.get_value(doctype, key, "name")
    if name:
        return name
    doc = frappe.get_doc({"doctype": doctype, **make})
    doc.insert(ignore_permissions=True)  # audit-ok: demo seeder
    return doc.name


# Master + transaction scaffold
def _client() -> str:
    return _goc(
        "Client",
        {"client_code": CLIENT_CODE},
        {"client_code": CLIENT_CODE, "client_name": CLIENT_NAME, "status": "Active"},
    )


def _branch_site(client: str) -> str:
    return _goc(
        "Branch Site",
        {"client": client, "site_code": SITE_CODE},
        {"client": client, "site_name": SITE_NAME, "site_code": SITE_CODE, "status": "Active"},
    )


def _period(client: str, branch: str) -> str:
    return _goc(
        "Timesheet Period",
        {"period_label": PERIOD_LABEL},
        {
            "period_label": PERIOD_LABEL,
            "client": client,
            "branch_site": branch,
            "month": PERIOD_MONTH,
            "status": "Open",
            "start_date": PERIOD_START,
            "end_date": PERIOD_END,
        },
    )


def _workers() -> list[str]:
    """One Temporary Worker + one canonical Worker identity per synthetic person."""
    names: list[str] = []
    for spec in WORKERS:
        temp = _goc(
            "Temporary Worker",
            {"passport_number": spec["passport"]},
            {
                "worker_name": spec["name"],
                "passport_number": spec["passport"],
                "arrival_date": today(),
                "window_days": 30,
                "status": "Active",
            },
        )
        worker = _goc(
            "Worker",
            {"worker_name": spec["name"]},
            {"worker_name": spec["name"], "status": "Active", "source_temporary_worker": temp},
        )
        names.append(worker)
    return names


def _rate_card(client: str, branch: str) -> str:
    return _goc(
        "Rate Card",
        {"rc_card_name": CARD_NAME},
        {
            "rc_card_name": CARD_NAME,
            "rc_client": client,
            "rc_branch_site": branch,
            "rc_service_line": "delivery",
            "rc_billing_unit": "package_day",
            "rc_rate_structure": "fixed_tier",
            "rc_status": "draft",
            "rc_effective_from": PERIOD_START,
            "rc_version": 1,
            "rc_components": [
                {
                    "rc_component": "day_rate",
                    "rc_unit": "per_period",
                    "rc_value": CARD_VALUE,
                    "rc_day_rate_basis": DAY_RATE_BASIS,
                    "rc_source_field": "Demo Rate/Day",
                }
            ],
        },
    )


def _recon_config(client: str) -> str:
    return _goc(
        "Client Reconciliation Config",
        {"rec_client": client},
        {"rec_client": client, "has_per_worker_feed": 1, "handoff_sla_days": 5},
    )


def _timesheet_lines(period: str, workers: list[str]) -> list[str]:
    lines: list[str] = []
    for worker in workers:
        existing = frappe.db.get_value(
            "Timesheet Line", {"ts_period": period, "ts_worker": worker}, "name"
        )
        if existing:
            lines.append(existing)
            continue
        doc = frappe.get_doc(
            {
                "doctype": "Timesheet Line",
                "ts_period": period,
                "ts_worker": worker,
                "ts_role_package": "delivery",
                "ts_completeness": "COMPLETE",
                "ts_payable_days": PAYABLE_DAYS,
                "ts_shifts": PAYABLE_DAYS,
                "ts_ot_hours": 10,
            }
        )
        doc.insert(ignore_permissions=True)  # audit-ok: demo seeder
        lines.append(doc.name)
    return lines


def _declaration(client: str, period: str) -> str:
    return _goc(
        "Deduction Declaration",
        {"pay_client": client, "pay_period": period},
        {
            "pay_client": client,
            "pay_period": period,
            "pay_declaration_type": "clear",
            "pay_no_deductions_stated": 1,
            "pay_status": "received",
            "pay_declaration_msg_ref": "Demo: ops contact stated no deductions this period.",
        },
    )


# Engine exercises
def _exercise_timesheet_engine(report: list) -> None:
    posted = post_timesheet_ledger()
    _log(report, f"[timesheet] post_timesheet_ledger posted {posted} ledger row(s) from COMPLETE lines.")


def _exercise_rate_resolver(report: list, card: str, period: str) -> str:
    """Resolve the demo card's day-rate line and stamp a Rate Resolution."""
    card_doc = frappe.get_doc("Rate Card", card)
    snapshot = resolve_from_card(card_doc, cycle_days=CYCLE_DAYS)
    applied = snapshot["rc_day_rate_applied"]
    _log(
        report,
        f"[rate] resolve_from_card: {CARD_VALUE} / div_31 = {applied} "
        f"(basis {snapshot['rc_day_rate_basis_applied']}); expected {EXPECTED_DAY_RATE}.",
    )
    existing = frappe.db.get_value(
        "Rate Resolution", {"rc_resolved_card": card, "rc_period": period}, "name"
    )
    if existing:
        return existing
    res = frappe.get_doc(
        {
            "doctype": "Rate Resolution",
            "rc_resolved_card": card,
            "rc_resolved_version": 1,
            "rc_period": period,
            "rc_billing_unit": "package_day",
            "rc_day_rate_applied": float(applied),
            "rc_day_rate_basis_applied": snapshot["rc_day_rate_basis_applied"],
            "rc_resolved_at": now_datetime(),
            "rc_resolved_by": "Administrator",
        }
    )
    res.insert(ignore_permissions=True)  # audit-ok: demo seeder
    return res.name


def _exercise_reconciliation(report: list, client, branch, period, resolution, workers) -> str:
    """One run, two outputs: a Billable Line + a Payable Line per worker, off the
    SAME resolution/basis, then run the real basis-consistent + fed guards."""
    run = frappe.db.get_value("Reconciliation Run", {"rec_run_name": RUN_NAME}, "name")
    if not run:
        doc = frappe.get_doc(
            {
                "doctype": "Reconciliation Run",
                "rec_run_name": RUN_NAME,
                "rec_client": client,
                "rec_branch_site": branch,
                "rec_service_line": "delivery",
                "rec_period": period,
                "rec_period_cutoff": PERIOD_END,
                "rec_version": 1,
                "rec_status": "draft",
                "rec_open_flags": 0,
            }
        )
        doc.insert(ignore_permissions=True)  # audit-ok: demo seeder
        run = doc.name

    billed_days = PAYABLE_DAYS * len(workers)
    billable_amount = float(EXPECTED_DAY_RATE) * billed_days
    if not frappe.db.exists("Billable Line", {"rec_run": run}):
        frappe.get_doc(
            {
                "doctype": "Billable Line",
                "rec_run": run,
                "rec_component": "timesheet",
                "rec_resolution_ref": resolution,
                "rec_billed_days": billed_days,
                "rec_qty": billed_days,
                "rec_day_rate_applied": float(EXPECTED_DAY_RATE),
                "rec_day_rate_basis_applied": DAY_RATE_BASIS,
                "rec_amount": billable_amount,
            }
        ).insert(ignore_permissions=True)  # audit-ok: demo seeder

    per_worker_gross = float(EXPECTED_DAY_RATE) * PAYABLE_DAYS
    for worker in workers:
        if frappe.db.exists("Payable Line", {"rec_run": run, "rec_worker": worker}):
            continue
        frappe.get_doc(
            {
                "doctype": "Payable Line",
                "rec_run": run,
                "rec_worker": worker,
                "rec_partial_reason": "full_month",
                "rec_resolution_ref": resolution,
                "rec_payable_days": PAYABLE_DAYS,
                "rec_monthly_package": CARD_VALUE,
                "rec_prorated_gross": per_worker_gross,
                "rec_day_rate_basis_applied": DAY_RATE_BASIS,
            }
        ).insert(ignore_permissions=True)  # audit-ok: demo seeder

    # Real guard: both sides share the div_31 basis on the same resolution -> passes.
    guard_basis_consistent(run)
    _log(report, f"[recon] guard_basis_consistent({run}) passed (billable & payable agree on {DAY_RATE_BASIS}).")

    applies = should_apply_thresholds(client)
    _log(report, f"[recon] should_apply_thresholds({client}) = {applies} (client has per-worker feed).")

    # Advance the run to 'rated' and stamp totals; validate() re-runs the guard and
    # snapshots the FED-PRECONDITION flag on the controller.
    total_payable = per_worker_gross * len(workers)
    run_doc = frappe.get_doc("Reconciliation Run", run)
    run_doc.rec_status = "rated"
    run_doc.rec_line_count = 1 + len(workers)
    run_doc.rec_total_billable = billable_amount
    run_doc.rec_total_payable = total_payable
    run_doc.rec_prepared_by = "Administrator"
    run_doc.rec_prepared_at = now_datetime()
    run_doc.save(ignore_permissions=True)  # audit-ok: demo seeder
    _log(
        report,
        f"[recon] run {run} rated: billable {billable_amount}, payable {total_payable}, "
        f"fed_precondition_met={run_doc.rec_fed_precondition_met}.",
    )
    return run


def _exercise_payroll_gates(report: list, period: str, declaration: str) -> None:
    # 1) Declaration gate — pre-slip states pass; slip-build blocks without a
    #    RECEIVED declaration; the demo declaration is received -> passes.
    received = frappe.db.get_value("Deduction Declaration", declaration, "pay_status") == "received"
    try:
        enforce_declaration_gate("Slips Built", declaration_received=False)
        _log(report, "[payroll] UNEXPECTED: declaration gate did not block a slip-build with no declaration.")
    except frappe.ValidationError:
        _log(report, "[payroll] declaration gate blocked 'Slips Built' with no declaration (fail-closed).")
    enforce_declaration_gate("Slips Built", declaration_received=received)
    _log(
        report,
        f"[payroll] declaration gate passed 'Slips Built' with received declaration "
        f"(requires_declaration={requires_declaration('Slips Built')}, received={received}).",
    )

    # 2) Component routing — synthetic map: #7 -> Loan Repayment, #8 held.
    routing = {7: "Loan Repayment", 3: "Operational Deduction"}
    held = {8}
    seven = route_deduction_component(7, routing, held)
    eight = route_deduction_component(8, routing, held)
    _log(report, f"[payroll] route_deduction_component: #7 -> {seven}; #8 -> {eight} (held).")

    # 3) Consent format leg — pure SA-IBAN format rule (WPS release precondition).
    _log(
        report,
        f"[payroll] valid_sa_iban(planted synthetic) = {valid_sa_iban(PLANTED_IBAN)}; "
        f"valid_sa_iban('SA123') = {valid_sa_iban('SA123')}.",
    )

    # 4) Real consent chokepoint — an unconsented P-192 deduction must not post.
    try:
        additional_salary_validate(
            frappe._dict(
                type="Deduction",
                pay_category="Advance Recovery",  # synthetic non-held category
                pay_consent=None,
                amount=100,
                payroll_date=PERIOD_END,
            )
        )
        _log(report, "[payroll] NOTE: consent chokepoint did not block (policy master may be unseeded).")
    except frappe.ValidationError:
        _log(report, "[payroll] additional_salary_validate blocked an unconsented deduction (consent gate fired).")
    except Exception as exc:  # noqa: BLE001 - master may be absent on a bare bench
        _log(report, f"[payroll] SKIP consent chokepoint: {type(exc).__name__} (Salary Deduction Policy unseeded).")


def _exercise_governance(report: list, run: str) -> None:
    from apex.logistay_governance.enforce_gate import enforce_gate, write_audit

    role = _goc("Role", {"role_name": GOV_ROLE}, {"role_name": GOV_ROLE})
    preparer = _demo_user(GOV_PREPARER)  # no controlling role
    approver = _demo_user(GOV_APPROVER, roles=[role])  # holds the band role
    _demo_band(role)

    amount = float(EXPECTED_DAY_RATE) * PAYABLE_DAYS * len(WORKERS)  # 23400
    # DoA + SoD gate -> ALLOW (writes a doa_approve Audit Event). Robust: if the
    # bench already carries seeded bands for this action the resolution can be
    # ambiguous; fall back to a direct audit write rather than fail the demo.
    try:
        verdict = enforce_gate("Reconciliation Run", run, GOV_ACTION, amount, preparer, approver)
        _log(report, f"[gov] enforce_gate ALLOW for {run} (amount {amount}); doa_approve Audit Event written.")
        assert verdict == "ALLOW"
    except frappe.ValidationError as exc:
        _log(report, f"[gov] enforce_gate could not resolve deterministically ({exc}); writing a plain audit instead.")
        write_audit("Reconciliation Run", run, "reconciliation_post", approver, subject_key=f"{TAG}.recon.posted")

    # SoD fail-closed — maker == checker is blocked (writes an sod_block event).
    try:
        enforce_gate("Reconciliation Run", run, GOV_ACTION, amount, approver, approver)
        _log(report, "[gov] UNEXPECTED: SoD gate allowed maker==checker.")
    except frappe.ValidationError:
        _log(report, "[gov] SoD gate blocked maker==checker (fail-closed).")

    # Guarantee at least one governance Audit Event tied to the demo run exists.
    write_audit("Reconciliation Run", run, "reconciliation_post", approver, subject_key=f"{TAG}.recon.reviewed")
    _log(report, "[gov] write_audit recorded an immutable Audit Event for the demo run.")


def _exercise_wps_sif(report: list) -> None:
    # Synthetic slip dicts (real Salary Slips are external HRMS). Two establishments.
    slips = [
        {"establishment": "DEMO-EST-1", "net": 7800.00},
        {"establishment": "DEMO-EST-1", "net": 7800.00},
        {"establishment": "DEMO-EST-2", "net": 7800.00},
    ]
    sif = wps_sif.build_wps_sif(slips)
    ok = wps_sif.sif_reconciles(sif, slips)
    _log(
        report,
        f"[wps] build_wps_sif grand_total_net={sif['grand_total_net']} across "
        f"{len(sif['establishments'])} establishments; sif_reconciles={ok}.",
    )


def _exercise_invoice_partial(report: list) -> None:
    # Pure invoice-assembly logic (no ZATCA app needed).
    rules = [
        {"inv_component": "timesheet", "inv_target_document": "main_timesheet", "inv_is_enabled": 1, "inv_rides_on": "own_document"},
        {"inv_component": "gosi_fee", "inv_target_document": "own", "inv_is_enabled": 1, "inv_rides_on": "own_document"},
        {"inv_component": "levy", "inv_target_document": "levy_doc", "inv_is_enabled": 0, "inv_rides_on": "own_document"},
    ]
    targets = invoice_assembly.present_set_targets(rules, fired_components=["timesheet", "gosi_fee", "levy"])
    match = invoice_assembly.naming_matches(
        "Demo Logistay Client LLC", "300000000000003",
        "Demo Logistay Client LLC", "300000000000003",
    )
    _log(report, f"[invoice] present_set_targets -> {targets}; naming_matches(exact)={match}.")
    _log(
        report,
        "[invoice] SKIP ZATCA issuance leg: enforce_issuance_gate needs the procured "
        "KSA/ZATCA e-invoice app + a stock Sales Invoice + Client Name Registry (not driven).",
    )
    _log(report, "[payroll] SKIP real Salary Slip generation: external HRMS payroll engine.")


def _demo_user(email: str, roles=None) -> str:
    if not frappe.db.exists("User", email):
        frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": "Demo " + email.split(".")[1].split("@")[0].title(),
                "send_welcome_email": 0,
            }
        ).insert(ignore_permissions=True)  # audit-ok: demo seeder
    if roles:
        frappe.get_doc("User", email).add_roles(*roles)
    return email


def _demo_band(role: str) -> str:
    existing = frappe.db.get_value(
        "DoA Band", {"gov_action": GOV_ACTION, "gov_required_role": role}, "name"
    )
    if existing:
        return existing
    band = frappe.get_doc(
        {
            "doctype": "DoA Band",
            "gov_action": GOV_ACTION,
            "gov_band_seq": 1,
            "gov_active": 1,
            "gov_amount_from": 0,
            "gov_amount_to": 1_000_000,
            "gov_required_role": role,
            "gov_effective_from": "2020-01-01",
        }
    )
    band.insert(ignore_permissions=True)  # audit-ok: demo seeder
    return band.name


# Entry points
def make_logistay_demo() -> dict:
    """Build the synthetic scenario and exercise every runnable Logistay engine.

    Returns a summary dict; the per-engine trace is also printed to the console.
    """
    report: list[str] = []
    _log(report, "=== make_logistay_demo (genericized, synthetic-only) ===")

    client = _client()
    branch = _branch_site(client)
    period = _period(client, branch)
    workers = _workers()
    card = _rate_card(client, branch)
    _recon_config(client)
    _timesheet_lines(period, workers)
    declaration = _declaration(client, period)
    _log(report, f"[scaffold] client={client}, branch={branch}, period={period}, card={card}, workers={workers}.")

    _exercise_timesheet_engine(report)
    resolution = _exercise_rate_resolver(report, card, period)
    run = _exercise_reconciliation(report, client, branch, period, resolution, workers)
    _exercise_payroll_gates(report, period, declaration)
    _exercise_governance(report, run)
    _exercise_wps_sif(report)
    _exercise_invoice_partial(report)

    frappe.db.commit()
    _log(report, "=== demo ready — open the Desk lists for Rate Resolution, Reconciliation Run, "
                 "Billable/Payable Line, Timesheet Ledger, Audit Event, DoA Band ===")
    return {"client": client, "period": period, "card": card, "run": run, "resolution": resolution, "trace": report}


def clear_logistay_demo() -> dict:
    """Remove exactly what ``make_logistay_demo`` created. Idempotent.

    Uses raw ``frappe.db.delete`` for the append-only Rate Resolution / Audit
    Event ledgers (their controllers refuse a normal trash), and ``delete_doc``
    for everything else, in dependency order.
    """
    removed: list[str] = []

    def _drop(doctype: str, filters: dict, raw: bool = False) -> None:
        names = frappe.get_all(doctype, filters=filters, pluck="name")
        for name in names:
            if raw:
                frappe.db.delete(doctype, {"name": name})
            else:
                frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)  # audit-ok: demo seeder
        if names:
            removed.append(f"{doctype}: {len(names)}")

    run = frappe.db.get_value("Reconciliation Run", {"rec_run_name": RUN_NAME}, "name")
    if run:
        _drop("Billable Line", {"rec_run": run}, raw=True)
        _drop("Payable Line", {"rec_run": run}, raw=True)

    # Audit Events + Rate Resolution are append-only: raw delete only.
    _drop("Audit Event", {"gov_entity_id": RUN_NAME}, raw=True)
    _drop("Audit Event", {"gov_subject_key": ["like", f"{TAG}.%"]}, raw=True)
    card = frappe.db.get_value("Rate Card", {"rc_card_name": CARD_NAME}, "name")
    if card:
        _drop("Rate Resolution", {"rc_resolved_card": card}, raw=True)

    period = frappe.db.get_value("Timesheet Period", {"period_label": PERIOD_LABEL}, "name")
    if period:
        line_names = frappe.get_all("Timesheet Line", filters={"ts_period": period}, pluck="name")
        for lname in line_names:
            _drop("Timesheet Ledger", {"source_name": lname}, raw=True)
        _drop("Timesheet Line", {"ts_period": period})
        _drop("Deduction Declaration", {"pay_period": period})

    if run:
        _drop("Reconciliation Run", {"name": run})
    _drop("Rate Card", {"rc_card_name": CARD_NAME})
    client = frappe.db.get_value("Client", {"client_code": CLIENT_CODE}, "name")
    if client:
        _drop("Client Reconciliation Config", {"rec_client": client})
    if period:
        _drop("Timesheet Period", {"period_label": PERIOD_LABEL})
    for spec in WORKERS:
        _drop("Worker", {"worker_name": spec["name"]})
        _drop("Temporary Worker", {"passport_number": spec["passport"]})
    _drop("Branch Site", {"site_code": SITE_CODE})
    _drop("Client", {"client_code": CLIENT_CODE})

    # Governance fixture last (users own the audit events removed above).
    _drop("DoA Band", {"gov_action": GOV_ACTION, "gov_required_role": GOV_ROLE})
    for email in (GOV_PREPARER, GOV_APPROVER):
        _drop("User", {"name": email})
    _drop("Role", {"role_name": GOV_ROLE})

    frappe.db.commit()
    summary = {"removed": removed}
    print(f"clear_logistay_demo removed: {removed}")
    return summary
