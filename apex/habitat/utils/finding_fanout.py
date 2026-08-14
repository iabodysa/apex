# Copyright (c) 2026, afmcoltd
"""Shared maintenance fan-out for inspection findings.

A single actionable Inspection Finding Item (one carrying an issue_type and a
room, not yet resolved, and not already linked to a live Maintenance Request)
spawns exactly ONE Maintenance Request. The source document's identity is
stamped on the ticket so the chain is traceable both ways:

  * a Safety Task Execution stamps ``source_execution``;
  * a Safety Inspection Report stamps ``source_inspection``.

The finding's ``generated_maintenance_request`` back-link is written so the
fan-out is idempotent: a finding already pointing at a live ticket is never
re-spawned (covers re-submit-after-amend, where the back-link is copied
forward, and any defensive re-run).

This logic was lifted out of the deprecated Safety Inspection Report controller
so both the report and the live Safety Task Execution path share one
implementation. The conversion pattern (frappe.new_doc + insert + back-link
stamp) mirrors accommodation_resident_request.convert_request rather than
get_mapped_doc, because one source spawns N tickets — a one-source-to-one-target
mapper does not fit.

The insert passes ``ignore_permissions`` because the ticket is spawned by the framework on the
source document's submit, not filed by the inspector: the permission that mattered was checked
when they submitted the round. An inspector able to create Maintenance Requests directly could
raise them with no finding behind them.
"""

from __future__ import annotations

import frappe
from frappe import _


_STE_DOCTYPE = "Safety Task Execution"
_SIR_DOCTYPE = "Safety Inspection Report"


def fan_out_findings(findings_rows, source_doc) -> list[str]:
    """Create one Maintenance Request per actionable finding in ``findings_rows``.

    Args:
        findings_rows: an iterable of Inspection Finding Item child rows (e.g.
            ``self.findings`` on a Safety Task Execution or one of the SIR
            finding tables).
        source_doc: the parent Document driving the fan-out (a Safety Task
            Execution or a Safety Inspection Report). Used to map shared fields
            (building, inspector) and to decide which source back-link to stamp.

    Returns:
        The names of the Maintenance Requests created on this call (findings
        skipped as not-actionable or already-linked are not included).

    Idempotent: a finding already carrying a live generated_maintenance_request
    is skipped; only actionable findings (see :func:`is_actionable`) spawn a
    ticket.
    """
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
    """Build, insert, and return the name of the MR for one finding.

    Maps room / issue_type / priority / building and stamps the source-specific
    back-link field (source_execution for an STE, source_inspection for a SIR)."""
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
    """Stamp the Maintenance Request with the source-specific back-link.

    A Safety Task Execution stamps source_execution; a Safety Inspection Report
    stamps source_inspection. Any other source DocType is left unstamped (the
    ticket is still created)."""
    if source_doc.doctype == _STE_DOCTYPE:
        mr.source_execution = source_doc.name
    elif source_doc.doctype == _SIR_DOCTYPE:
        mr.source_inspection = source_doc.name


def _reported_by(source_doc) -> str:
    """Best-effort reporter: the source's inspector/executor, else the session user."""
    return (
        source_doc.get("inspector")
        or source_doc.get("executed_by")
        or frappe.session.user
    )


def is_actionable(finding) -> bool:
    """A finding warrants a ticket when it names an issue_type and a room and is
    not already resolved. issue_type is the explicit 'this needs maintenance'
    signal; a resolved finding needs no new ticket.

    Public because the same rule decides safety-notification escalation; this
    module owns it, callers import it rather than re-stating the three tests."""
    if not finding.get("issue_type"):
        return False
    if not finding.get("room"):
        return False
    if (finding.get("status") or "") == "Resolved":
        return False
    return True


def _already_linked(finding) -> bool:
    """True only when the recorded back-link points at a Maintenance Request that
    still exists — a dangling link (target deleted) is treated as not linked so a
    fresh ticket is created."""
    mr_name = finding.get("generated_maintenance_request")
    if not mr_name:
        return False
    return bool(frappe.db.exists("Maintenance Request", mr_name))
