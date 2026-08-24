# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from apex.tests.factories import make_building, make_safety_round


def _task_catalog(code):
    if frappe.db.exists("Safety Task Catalog", {"task_code": code}):
        return frappe.db.get_value("Safety Task Catalog", {"task_code": code}, "name")
    return frappe.get_doc(
        {
            "doctype": "Safety Task Catalog",
            "task_title": f"_T-Safety Task {code}",
            "department": "Fire Safety",
            "task_code": code,
            "frequency": "Weekly",
        }
    ).insert(ignore_permissions=True).name


def _execution(round_doc, task, status="Good"):
    return frappe.get_doc(
        {
            "doctype": "Safety Task Execution",
            "execution_date": today(),
            "building": round_doc.building,
            "task": task,
            "execution_status": status,
            "safety_round": round_doc.name,
        }
    ).insert(ignore_permissions=True)


class TestSafetyRoundDuplicateGuard(FrappeTestCase):
    def test_a_duplicate_round_for_the_same_building_date_and_cadence_is_refused(self):
        building = make_building("_T-SRound Duplicate")
        make_safety_round(building.name, round_date=today(), cadence="Weekly")
        clash = frappe.get_doc(
            {
                "doctype": "Safety Round",
                "building": building.name,
                "round_date": today(),
                "cadence": "Weekly",
            }
        )
        with self.assertRaises(frappe.ValidationError):
            clash.insert(ignore_permissions=True)

    def test_a_reinspection_is_exempt_from_the_duplicate_guard(self):
        building = make_building("_T-SRound Reinspection")
        make_safety_round(building.name, round_date=today(), cadence="Weekly")
        follow_up = frappe.get_doc(
            {
                "doctype": "Safety Round",
                "building": building.name,
                "round_date": today(),
                "cadence": "Weekly",
                "is_reinspection": 1,
            }
        ).insert(ignore_permissions=True)
        self.assertEqual(follow_up.doctype, "Safety Round")


class TestSafetyRoundSubmitGuard(FrappeTestCase):
    def test_submitting_a_round_with_no_rated_task_is_refused(self):
        building = make_building("_T-SRound No Task")
        round_doc = make_safety_round(building.name, round_date=today(), cadence="Weekly")
        with self.assertRaises(frappe.ValidationError):
            round_doc.submit()


class TestSafetyRoundSubmit(FrappeTestCase):
    def test_submitting_ratifies_draft_executions_and_derives_a_pass_result(self):
        building = make_building("_T-SRound Ratify")
        round_doc = make_safety_round(building.name, round_date=today(), cadence="Weekly")
        task = _task_catalog("_T-SRound-Task-Ratify")
        execution = _execution(round_doc, task, status="Good")
        round_doc.submit()
        execution.reload()
        self.assertEqual(execution.docstatus, 1)
        self.assertEqual(round_doc.overall_result, "Pass")
