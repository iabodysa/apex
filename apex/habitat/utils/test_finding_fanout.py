# Copyright (c) 2026, AFMCO and contributors
"""Unit tests for habitat.utils.finding_fanout.fan_out_findings.

The Maintenance Request creation is mocked (a fake ``new_doc``), so the
actionable / not-actionable / already-linked decision branches, the field
mapping, and the source-specific back-link stamp are all exercised without a
live site.
"""

from __future__ import annotations

import unittest
from unittest import mock

from apex.habitat.utils import finding_fanout


class _FakeRow:
    """Stand-in for an Inspection Finding Item child row."""

    def __init__(self, **fields):
        self._fields = fields
        self.db_set_calls = []

    def get(self, key, default=None):
        return self._fields.get(key, default)

    def db_set(self, field, value):
        self.db_set_calls.append((field, value))
        self._fields[field] = value


class _FakeMR:
    """Stand-in for a Maintenance Request returned by frappe.new_doc."""

    def __init__(self):
        self.name = "MR-FAKE-1"

    def insert(self, *args, **kwargs):
        return self


class _FakeSource:
    def __init__(self, **fields):
        self._fields = fields
        self.doctype = fields.get("doctype")
        self.name = fields.get("name")

    def get(self, key, default=None):
        return self._fields.get(key, default)


class TestFanOutFindings(unittest.TestCase):
    def _source(self, **overrides):
        base = {
            "doctype": "Safety Task Execution",
            "name": "STE-1",
            "building": "B-1",
            "executed_by": "exec@x",
        }
        base.update(overrides)
        return _FakeSource(**base)

    def test_actionable_finding_spawns_ticket_and_back_links(self):
        finding = _FakeRow(
            issue_type="Plumbing", room="R-1", status="Open",
            priority="High", description="Leak under sink",
        )
        mr = _FakeMR()
        with mock.patch.object(finding_fanout, "frappe") as mf:
            mf.new_doc.return_value = mr
            created = finding_fanout.fan_out_findings([finding], self._source())
        self.assertEqual(created, ["MR-FAKE-1"])
        self.assertEqual(mr.building, "B-1")
        self.assertEqual(mr.room, "R-1")
        self.assertEqual(mr.issue_type, "Plumbing")
        self.assertEqual(mr.priority, "High")
        self.assertEqual(mr.issue_description, "Leak under sink")
        self.assertEqual(mr.reported_by, "exec@x")
        self.assertEqual(mr.status, "Open")
        self.assertEqual(mr.source_execution, "STE-1")
        self.assertIn(("generated_maintenance_request", "MR-FAKE-1"), finding.db_set_calls)

    def test_priority_defaults_to_medium(self):
        finding = _FakeRow(issue_type="Electrical", room="R-2", description="Sparks")
        mr = _FakeMR()
        with mock.patch.object(finding_fanout, "frappe") as mf:
            mf.new_doc.return_value = mr
            finding_fanout.fan_out_findings([finding], self._source())
        self.assertEqual(mr.priority, "Medium")

    def test_not_actionable_findings_are_skipped(self):
        no_issue = _FakeRow(room="R-1", description="x")
        no_room = _FakeRow(issue_type="Plumbing", description="x")
        resolved = _FakeRow(issue_type="Plumbing", room="R-1", status="Resolved", description="x")
        with mock.patch.object(finding_fanout, "frappe") as mf:
            created = finding_fanout.fan_out_findings(
                [no_issue, no_room, resolved], self._source()
            )
            mf.new_doc.assert_not_called()
        self.assertEqual(created, [])

    def test_already_linked_finding_is_skipped(self):
        finding = _FakeRow(
            issue_type="Plumbing", room="R-1", status="Open", description="x",
            generated_maintenance_request="MR-EXIST",
        )
        with mock.patch.object(finding_fanout, "frappe") as mf:
            mf.db.exists.return_value = True
            created = finding_fanout.fan_out_findings([finding], self._source())
            mf.new_doc.assert_not_called()
        self.assertEqual(created, [])

    def test_empty_and_none_rows_return_empty(self):
        with mock.patch.object(finding_fanout, "frappe"):
            self.assertEqual(finding_fanout.fan_out_findings([], self._source()), [])
            self.assertEqual(finding_fanout.fan_out_findings(None, self._source()), [])

    def test_inspection_source_stamps_source_inspection(self):
        finding = _FakeRow(issue_type="Plumbing", room="R-1", status="Open", description="x")
        mr = _FakeMR()
        src = self._source(
            doctype="Safety Inspection Report", name="SIR-9", inspector="insp@x"
        )
        with mock.patch.object(finding_fanout, "frappe") as mf:
            mf.new_doc.return_value = mr
            finding_fanout.fan_out_findings([finding], src)
        self.assertEqual(mr.source_inspection, "SIR-9")
        self.assertEqual(mr.reported_by, "insp@x")


if __name__ == "__main__":
    unittest.main()
