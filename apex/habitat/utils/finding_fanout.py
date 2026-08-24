# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _


_STE_DOCTYPE = "Safety Task Execution"
_SIR_DOCTYPE = "Safety Inspection Report"


def fan_out_findings(findings_rows, source_doc) -> list[str]:
    created: list[str] = []
    for finding in findings_rows or []:
        if not is_actionable(finding):
            continue
        if _already_linked(finding):
            continue
        mr_name = _spawn_request(finding, source_doc)
        finding.db_set("generated_maintenance_request", mr_name)
        created.append(mr_name)
    return created


def _spawn_request(finding, source_doc) -> str:
    mr = frappe.new_doc("Maintenance Request")
    mr.building = source_doc.get("building")
    mr.room = finding.room
    mr.issue_type = finding.issue_type
    mr.priority = finding.get("priority") or "Medium"
    mr.issue_description = finding.get("description") or _(
        "Auto-generated from {0} {1}"
    ).format(source_doc.doctype, source_doc.name)
    mr.reported_by = _reported_by(source_doc)
    mr.status = "Open"
    _stamp_source(mr, source_doc)
    mr.insert(ignore_permissions=True)
    return mr.name


def _stamp_source(mr, source_doc) -> None:
    if source_doc.doctype == _STE_DOCTYPE:
        mr.source_execution = source_doc.name
    elif source_doc.doctype == _SIR_DOCTYPE:
        mr.source_inspection = source_doc.name


def _reported_by(source_doc) -> str:
    return (
        source_doc.get("inspector")
        or source_doc.get("executed_by")
        or frappe.session.user
    )


def is_actionable(finding) -> bool:
    if not finding.get("issue_type"):
        return False
    if not finding.get("room"):
        return False
    if (finding.get("status") or "") == "Resolved":
        return False
    return True


def _already_linked(finding) -> bool:
    mr_name = finding.get("generated_maintenance_request")
    if not mr_name:
        return False
    return bool(frappe.db.exists("Maintenance Request", mr_name))
