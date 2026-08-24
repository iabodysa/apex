# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.utils import now_datetime

from apex.apex_core.utils.company import company_for_building


LEDGER_DOCTYPE = "Safety Finding Ledger"
EXECUTION_DOCTYPE = "Safety Task Execution"

_RESOLVED_STATUS = "Resolved"


def post_safety_findings(safety_round) -> int:
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
        findings = frappe.get_all(
            "Inspection Finding Item",
            filters={"parent": execution_name, "parenttype": EXECUTION_DOCTYPE},
            fields=["idx", "description", "severity", "status"],
            order_by="idx asc",
        )
        for finding in findings:
            if frappe.db.exists(
                LEDGER_DOCTYPE,
                {
                    "source_doctype": EXECUTION_DOCTYPE,
                    "source_name": execution_name,
                    "source_detail_no": finding.idx,
                    "reversal_of": ["is", "not set"],
                },
            ):
                continue
            frappe.get_doc(
                {
                    "doctype": LEDGER_DOCTYPE,
                    "safety_round": safety_round.name,
                    "building": building,
                    "company": company,
                    "posting_date": posting_date,
                    "finding": finding.description,
                    "severity": finding.severity,
                    "status": finding.status,
                    "resolved": 1 if (finding.status or "") == _RESOLVED_STATUS else 0,
                    "source_doctype": EXECUTION_DOCTYPE,
                    "source_name": execution_name,
                    "source_detail_no": finding.idx,
                    "logged_at": now_datetime(),
                }
            ).insert(ignore_permissions=True)
            posted += 1

    return posted


def reverse_safety_findings(safety_round_name: str) -> int:
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
        ).insert(ignore_permissions=True)
        posted += 1

    return posted
