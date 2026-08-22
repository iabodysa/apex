# Copyright (c) 2026, afmcoltd
"""What a Safety Inspection Report guarantees, asserted against the DocType itself.

Patterned on frappe's own document lifecycle tests (``frappe/tests/test_document.py``,
``test_update_after_submit``). ``on_submit`` / ``on_cancel`` are native class methods —
Frappe calls them directly on ``submit()`` / ``cancel()``, no ``hooks.py`` wiring.

Three guarantees: (1) ``safety_section_clear`` short-circuits the fan-out entirely, even
with a finding row present; (2) submitting an actionable finding (issue_type + room, not
resolved) spawns exactly one Maintenance Request, surfaced in the read-only
``linked_maintenance_requests`` table; (3) cancelling deletes a generated ticket nobody
has picked up yet (still Draft), reversing the fan-out rather than leaving it orphaned.

NOTE (finding, not asserted here): ``Maintenance Request.source_inspection``'s own field
description calls this DocType "deprecated" — new safety-driven requests are meant to
carry ``source_execution`` from Safety Task Execution instead. The lifecycle guarantees
below are still live code and are tested as such.

NOT covered here: cancelling a report that generated a still-draft Maintenance Request
currently raises ``frappe.exceptions.LinkExistsError`` instead of deleting it —
``_reverse_generated_request`` (``safety_inspection_report.py:58``) calls
``frappe.delete_doc(..., ignore_permissions=True)`` without ``force`` or
``ignore_doctypes=["Safety Inspection Report"]``, and the report's own
``linked_maintenance_requests`` child row (written by ``_surface``) still points at the
ticket at the moment of cancel, so Frappe's own referential-integrity check
(``check_if_doc_is_linked``) blocks the delete. This contradicts the method's own
docstring ("a still-draft generated ticket is a pure side-effect and is deleted") and is
reachable through the plain submit-then-cancel lifecycle, not a contrived state — reported
as a finding rather than pinned as a passing test, since asserting the crash as expected
would misrepresent a bug as a guarantee.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Building", "Room"]


def _make_report(*, safety_section_clear, findings=None):
    report = frappe.new_doc("Safety Inspection Report")
    report.building = "_Test Building"
    report.inspection_date = "2026-01-14"
    report.inspector = "Administrator"
    report.safety_section_clear = safety_section_clear
    for row in findings or []:
        report.append("safety_findings", row)
    return report


class TestSafetyInspectionReport(FrappeTestCase):
    def test_submitting_with_safety_section_clear_raises_no_maintenance_request(self):
        """safety_section_clear is the inspector declaring no issues; the fan-out must
        short-circuit entirely even with a finding row present."""
        report = _make_report(
            safety_section_clear=1,
            findings=[
                {"issue_type": "Electrical", "room": "_T-101", "description": "_Test stray finding"}
            ],
        )
        report.insert()
        report.submit()

        self.assertEqual(len(report.linked_maintenance_requests), 0)
        self.assertEqual(
            frappe.db.count("Maintenance Request", {"source_inspection": report.name}), 0
        )

    def test_submitting_an_actionable_finding_raises_and_surfaces_one_maintenance_request(self):
        """An actionable finding must spawn exactly one ticket, surfaced in the read-only
        linked table."""
        report = _make_report(
            safety_section_clear=0,
            findings=[
                {"issue_type": "Electrical", "room": "_T-101", "description": "_Test broken socket"}
            ],
        )
        report.insert()
        report.submit()

        self.assertEqual(
            frappe.db.count("Maintenance Request", {"source_inspection": report.name}), 1
        )
        self.assertEqual(len(report.linked_maintenance_requests), 1)
        self.assertEqual(report.linked_maintenance_requests[0].status, "Open")
