# Copyright (c) 2026, afmcoltd
"""What a Safety Round guarantees, asserted against the DocType itself.

Patterned on frappe's own document lifecycle tests (``frappe/tests/test_document.py``,
``test_validate`` / ``test_update_after_submit``).

Four guarantees: (1) ``validate``'s ``_guard_duplicate`` refuses a second round for the
same building, date and cadence unless flagged ``is_reinspection``; (2) ``before_submit``'s
``_guard_rated`` refuses to close a round with no linked Safety Task Execution at all —
an unrated round would otherwise derive "Pass" from nothing; (3) ``on_submit`` ratifies
(submits) every still-draft execution linked to the round before deriving the result,
because the maker who records evidence cannot submit it themselves; (4) the derived
``overall_result`` follows the worst-status-wins rule — any "Not Done" fails the round,
otherwise any "Poor" needs attention, otherwise it passes.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Building"]


def _make_round(*, round_date, building="_Test Building", cadence="Weekly", is_reinspection=0):
    round_doc = frappe.new_doc("Safety Round")
    round_doc.building = building
    round_doc.round_date = round_date
    round_doc.cadence = cadence
    round_doc.is_reinspection = is_reinspection
    return round_doc


def _make_catalog_task():
    """A fresh, non-evidence-required Safety Task Catalog entry, so a Not Done / Poor
    result below is gated only by Safety Round's own rules, not the execution's evidence
    requirement."""
    catalog = frappe.new_doc("Safety Task Catalog")
    catalog.task_title = "_Test Round Task"
    catalog.task_code = frappe.generate_hash(length=8)
    catalog.department = "Fire Safety"
    catalog.frequency = "Weekly"
    catalog.insert()
    return catalog.name


def _make_draft_execution(*, round_name, building, execution_status):
    execution = frappe.new_doc("Safety Task Execution")
    execution.execution_date = "2026-03-02"
    execution.building = building
    execution.task = _make_catalog_task()
    execution.execution_status = execution_status
    execution.safety_round = round_name
    execution.insert()
    return execution


class TestSafetyRound(FrappeTestCase):
    def test_a_duplicate_round_for_the_same_building_date_and_cadence_is_refused(self):
        """Two rounds for the same building/date/cadence would double the record of one
        pass — a genuine follow-up must be flagged as a re-inspection instead."""
        first = _make_round(round_date="2026-03-03")
        first.insert()

        second = _make_round(round_date="2026-03-03")
        with self.assertRaisesRegex(frappe.ValidationError, "already exists"):
            second.insert()

    def test_a_reinspection_round_for_the_same_building_date_and_cadence_is_accepted(self):
        """is_reinspection is the documented escape hatch — a follow-up round on the same
        triple must still be recordable."""
        first = _make_round(round_date="2026-03-04")
        first.insert()

        reinspection = _make_round(round_date="2026-03-04", is_reinspection=1)
        reinspection.insert()

        self.assertTrue(reinspection.name)

    def test_submitting_a_round_with_no_rated_task_is_refused(self):
        """An unrated round would derive Pass from nothing — a signed-off claim that the
        building was checked when nothing was."""
        round_doc = _make_round(round_date="2026-03-05")
        round_doc.insert()

        with self.assertRaisesRegex(frappe.ValidationError, "no rated safety task"):
            round_doc.submit()

    def test_submitting_a_round_ratifies_its_draft_execution_and_fails_on_a_not_done_result(self):
        """The checker's submit must ratify the maker's still-draft execution — the result
        is derived only from docstatus 1 rows — and any Not Done execution fails the
        whole round (worst-status-wins)."""
        round_doc = _make_round(round_date="2026-03-06")
        round_doc.insert()
        execution = _make_draft_execution(
            round_name=round_doc.name, building=round_doc.building, execution_status="Not Done"
        )
        self.assertEqual(execution.docstatus, 0)

        round_doc.submit()

        self.assertEqual(
            frappe.db.get_value("Safety Task Execution", execution.name, "docstatus"), 1
        )
        self.assertEqual(round_doc.overall_result, "Fail")

    def test_a_round_with_only_passing_executions_derives_pass(self):
        """The worst-status-wins rule's other end: nothing but a passing result must
        derive Pass."""
        round_doc = _make_round(round_date="2026-03-07")
        round_doc.insert()
        _make_draft_execution(
            round_name=round_doc.name, building=round_doc.building, execution_status="Excellent"
        )

        round_doc.submit()

        self.assertEqual(round_doc.overall_result, "Pass")
