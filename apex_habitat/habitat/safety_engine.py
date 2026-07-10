# Copyright (c) 2026, AFMCO and contributors
"""Safety engine for the Habitat module.

Posts the Safety Finding Ledger: an immutable, system-written record of every
finding observed on a Safety Round, captured at the moment the round is submitted.

WHY: safety/audit findings otherwise live only on the mutable parent reports
(Inspection Finding Item rows on each Safety Task Execution), so a closed finding
can silently reopen or be edited and history is lost. Each finding is mirrored
here as one read-only row, so safety reports are stable.

Mirrors the Salis fuel ledger pattern
(``apex_habitat.salis.fuel_engine``): an idempotent ``_insert_ledger_row`` keyed
on ``(source_doctype, source_name, source_detail_no)`` and a reverse-not-delete
cancellation that posts a negating mirror row (``is_cancelled=1`` +
``reversal_of``) rather than deleting the original.

Fired from the Safety Round controller class methods (``on_submit`` /
``on_cancel``) — no hooks.py doc_events entry is needed because Safety Round
already owns those lifecycle methods.
"""

from __future__ import annotations

import frappe

from apex_habitat.apex_core.utils.company import company_for_building

LEDGER_DOCTYPE = "Safety Finding Ledger"
EXECUTION_DOCTYPE = "Safety Task Execution"

# A finding whose snapshot status is this value is recorded as resolved.
_RESOLVED_STATUS = "Resolved"


def _ledger_exists(source_doctype: str, source_name: str, source_detail_no: int) -> bool:
    """True if a ledger row already exists for this finding (idempotency key).

    The key is (source execution DocType, execution name, finding row idx): each
    finding row of each execution posts at most one original ledger row.
    """
    return bool(
        frappe.db.exists(
            LEDGER_DOCTYPE,
            {
                "source_doctype": source_doctype,
                "source_name": source_name,
                "source_detail_no": source_detail_no,
                "reversal_of": ["is", "not set"],
            },
        )
    )


def _insert_ledger_row(
    safety_round: str,
    building: str | None,
    company: str | None,
    posting_date,
    finding: str | None,
    severity: str | None,
    status: str | None,
    resolved: int,
    source_doctype: str,
    source_name: str,
    source_detail_no: int,
    logged_at,
) -> None:
    """Insert one immutable Safety Finding Ledger row (system-written)."""
    frappe.get_doc(
        {
            "doctype": LEDGER_DOCTYPE,
            "safety_round": safety_round,
            "building": building,
            "company": company,
            "posting_date": posting_date,
            "finding": finding,
            "severity": severity,
            "status": status,
            "resolved": resolved,
            "source_doctype": source_doctype,
            "source_name": source_name,
            "source_detail_no": source_detail_no,
            "logged_at": logged_at,
        }
    ).insert(ignore_permissions=True)  # audit-ok


def post_safety_findings(safety_round) -> int:
    """Post one immutable ledger row per finding on a submitted Safety Round.

    Reads every submitted Safety Task Execution linked to the round, then every
    Inspection Finding Item row on those executions, and posts an immutable
    snapshot of each. Idempotent on (execution DocType, execution name, finding
    idx): a finding already ledgered is skipped, so a re-submit-after-amend or a
    defensive re-run never duplicates a row.

    ``safety_round`` is the Safety Round document. Returns the number of rows
    posted on this call (0 if every finding was already ledgered).
    """
    from frappe.utils import now_datetime

    posting_date = safety_round.round_date
    building = safety_round.building
    company = company_for_building(building)

    executions = frappe.get_all(
        EXECUTION_DOCTYPE,
        filters={"safety_round": safety_round.name, "docstatus": 1},
        pluck="name",
    )

    posted = 0
    for execution_name in executions:
        # The findings live on the execution as Inspection Finding Item child
        # rows; read them in their stored row order so source_detail_no == idx.
        findings = frappe.get_all(
            "Inspection Finding Item",
            filters={"parent": execution_name, "parenttype": EXECUTION_DOCTYPE},
            fields=["idx", "description", "severity", "status"],
            order_by="idx asc",
        )
        for finding in findings:
            if _ledger_exists(EXECUTION_DOCTYPE, execution_name, finding.idx):
                continue
            _insert_ledger_row(
                safety_round=safety_round.name,
                building=building,
                company=company,
                posting_date=posting_date,
                finding=finding.description,
                severity=finding.severity,
                status=finding.status,
                resolved=1 if (finding.status or "") == _RESOLVED_STATUS else 0,
                source_doctype=EXECUTION_DOCTYPE,
                source_name=execution_name,
                source_detail_no=finding.idx,
                logged_at=now_datetime(),
            )
            posted += 1

    return posted


def reverse_safety_findings(safety_round_name: str) -> int:
    """Reverse the ledgered findings of a cancelled Safety Round.

    Posts a negating mirror row for each ORIGINAL ledger row of the round —
    flagged ``is_cancelled=1`` and linked back via ``reversal_of`` — so the
    finding is voided in any open/closed rollup while the original row is
    preserved for audit. Mirrors the Salis fuel ledger reversal idiom: a
    reversal, never a delete.

    Idempotent: only an ORIGINAL row (``reversal_of`` unset) is mirrored, and a
    row that already has a reversal pointing at it is skipped, so calling twice
    posts at most one reversal per original. Returns the number of reversal rows
    posted (0 if the round was never ledgered or is already fully reversed).
    """
    from frappe.utils import now_datetime

    originals = frappe.get_all(
        LEDGER_DOCTYPE,
        filters={
            "safety_round": safety_round_name,
            "reversal_of": ["is", "not set"],
        },
        fields=[
            "name",
            "safety_round",
            "building",
            "company",
            "posting_date",
            "finding",
            "severity",
            "status",
            "resolved",
            "source_doctype",
            "source_name",
            "source_detail_no",
        ],
    )

    posted = 0
    for row in originals:
        if frappe.db.exists(LEDGER_DOCTYPE, {"reversal_of": row.name}):
            continue
        frappe.get_doc(
            {
                "doctype": LEDGER_DOCTYPE,
                "safety_round": row.safety_round,
                "building": row.building,
                "company": row.company,
                "posting_date": row.posting_date,
                "finding": row.finding,
                "severity": row.severity,
                "status": row.status,
                "resolved": row.resolved,
                "source_doctype": row.source_doctype,
                "source_name": row.source_name,
                "source_detail_no": row.source_detail_no,
                "is_cancelled": 1,
                "reversal_of": row.name,
                "logged_at": now_datetime(),
            }
        ).insert(ignore_permissions=True)  # audit-ok
        posted += 1

    return posted
