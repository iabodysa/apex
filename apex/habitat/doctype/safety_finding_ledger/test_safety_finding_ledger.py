# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Safety Finding Ledger posting engine.

Proves that submitting a Safety Round posts one immutable ledger row per finding
on its executions, that posting is idempotent (a re-run adds no rows), that the
rows are immutable (cannot be edited or deleted), and that cancelling the round
reverses — not deletes — the ledgered findings.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today
from apex.tests.factories import make_safety_round


class TestSafetyFindingLedger(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        tag = self._testMethodName

        self.building = (
            frappe.get_doc(
                {
                    "doctype": "Building",
                    "building_name": f"SFL Bldg {tag}",
                    "status": "Active",
                }
            )
            .insert(ignore_permissions=True)
            .name
        )

        self.task = (
            frappe.get_doc(
                {
                    "doctype": "Safety Task Catalog",
                    "task_code": f"SFL-{tag}",
                    "task_title": f"SFL Task {tag}",
                    "department": "Fire Safety",
                    "frequency": "Weekly",
                    "priority": "High",
                    "applicable_to_all_buildings": 1,
                    "is_active": 1,
                }
            )
            .insert(ignore_permissions=True)
            .name
        )

    def _execution(self, safety_round, status, findings):
        doc = frappe.get_doc(
            {
                "doctype": "Safety Task Execution",
                "building": self.building,
                "task": self.task,
                "execution_date": today(),
                "execution_status": status,
                "safety_round": safety_round,
                "findings": findings,
            }
        ).insert(ignore_permissions=True)
        doc.submit()
        return doc

    def _ledger_rows(self, safety_round, originals_only=True):
        filters = {"safety_round": safety_round}
        if originals_only:
            filters["reversal_of"] = ["is", "not set"]
        return frappe.get_all(
            "Safety Finding Ledger",
            filters=filters,
            fields=[
                "name",
                "finding",
                "severity",
                "status",
                "resolved",
                "source_name",
                "source_detail_no",
                "is_cancelled",
                "reversal_of",
            ],
        )

    def test_submit_posts_one_row_per_finding(self):
        rnd = make_safety_round(self.building)
        self._execution(
            rnd.name,
            "Poor",
            [
                {"description": "Blocked fire exit", "severity": "High", "status": "Open"},
                {
                    "description": "Expired extinguisher",
                    "severity": "Critical",
                    "status": "Resolved",
                },
            ],
        )
        rnd.submit()

        rows = self._ledger_rows(rnd.name)
        self.assertEqual(len(rows), 2, "one immutable row per finding")
        by_desc = {r.finding: r for r in rows}
        self.assertEqual(by_desc["Blocked fire exit"].severity, "High")
        self.assertEqual(by_desc["Blocked fire exit"].status, "Open")
        self.assertEqual(by_desc["Blocked fire exit"].resolved, 0)
        self.assertEqual(by_desc["Expired extinguisher"].resolved, 1)
        self.assertEqual({r.source_detail_no for r in rows}, {1, 2})

    def test_posting_is_idempotent(self):
        rnd = make_safety_round(self.building)
        ex = self._execution(
            rnd.name,
            "Poor",
            [{"description": "Loose wiring", "severity": "Medium", "status": "Open"}],
        )
        rnd.submit()
        self.assertEqual(len(self._ledger_rows(rnd.name)), 1)

        from apex.habitat.safety_engine import post_safety_findings

        rnd.reload()
        posted = post_safety_findings(rnd)
        self.assertEqual(posted, 0, "a re-run posts no further rows")
        self.assertEqual(len(self._ledger_rows(rnd.name)), 1)
        self.assertTrue(ex.name)

    def test_rows_are_immutable(self):
        rnd = make_safety_round(self.building)
        self._execution(
            rnd.name,
            "Poor",
            [{"description": "Wet floor", "severity": "Low", "status": "Open"}],
        )
        rnd.submit()
        row = self._ledger_rows(rnd.name)[0]

        doc = frappe.get_doc("Safety Finding Ledger", row.name)
        doc.status = "Resolved"
        with self.assertRaises(frappe.ValidationError):
            doc.save(ignore_permissions=True)

        with self.assertRaises(frappe.ValidationError):
            frappe.delete_doc(
                "Safety Finding Ledger", row.name, ignore_permissions=True, force=True
            )

    def test_cancel_reverses_not_deletes(self):
        rnd = make_safety_round(self.building)
        ex = self._execution(
            rnd.name,
            "Poor",
            [
                {"description": "Faulty alarm", "severity": "High", "status": "Open"},
                {"description": "Missing sign", "severity": "Low", "status": "Open"},
            ],
        )
        rnd.submit()
        self.assertEqual(len(self._ledger_rows(rnd.name)), 2)

        ex.cancel()
        rnd.cancel()

        originals = self._ledger_rows(rnd.name)
        self.assertEqual(len(originals), 2, "originals are preserved on cancel")
        reversals = [
            r for r in self._ledger_rows(rnd.name, originals_only=False) if r.reversal_of
        ]
        self.assertEqual(len(reversals), 2, "one reversal per original")
        self.assertTrue(all(r.is_cancelled for r in reversals))
        self.assertEqual(
            {r.reversal_of for r in reversals}, {r.name for r in originals}
        )

    def test_cancel_reversal_is_idempotent(self):
        rnd = make_safety_round(self.building)
        ex = self._execution(
            rnd.name,
            "Poor",
            [{"description": "Cracked window", "severity": "Medium", "status": "Open"}],
        )
        rnd.submit()
        ex.cancel()
        rnd.cancel()

        from apex.habitat.safety_engine import reverse_safety_findings

        again = reverse_safety_findings(rnd.name)
        self.assertEqual(again, 0, "a second reversal posts nothing")
        reversals = [
            r for r in self._ledger_rows(rnd.name, originals_only=False) if r.reversal_of
        ]
        self.assertEqual(len(reversals), 1, "exactly one reversal per original")
