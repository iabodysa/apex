# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.tests.factories import make_building


def _task_template():
    doc = frappe.get_doc({
        "doctype": "Scheduled Task Template",
        "template_name": "_T-Task Template " + frappe.generate_hash(length=6),
        "task_type": "Maintenance",
        "frequency": "Monthly",
    })
    return doc.insert(ignore_permissions=True).name


def _assignment(**overrides):
    fields = {
        "doctype": "Scheduled Task Assignment",
        "template": None,
        "building": None,
        "effective_from": "2026-04-01",
    }
    fields.update(overrides)
    if fields.get("template") is None:
        fields["template"] = _task_template()
    if fields.get("building") is None:
        fields["building"] = make_building("Scheduled Task Test Building", company="_Test Company").name
    return frappe.get_doc(fields)


class TestScheduledTaskAssignmentMandatoryPlace(FrappeTestCase):
    def test_framework_refuses_an_assignment_that_names_no_template(self):
        with self.assertRaises(frappe.MandatoryError):
            _assignment(template="").insert(ignore_permissions=True)

    def test_framework_refuses_an_assignment_that_names_no_building(self):
        with self.assertRaises(frappe.MandatoryError):
            _assignment(building="").insert(ignore_permissions=True)

    def test_framework_refuses_an_assignment_with_no_effective_date(self):
        with self.assertRaises(frappe.MandatoryError):
            _assignment(effective_from=None).insert(ignore_permissions=True)


class TestScheduledTaskAssignmentLinks(FrappeTestCase):
    def test_framework_refuses_a_template_that_does_not_exist(self):
        with self.assertRaisesRegex(frappe.LinkValidationError, "Could not find"):
            _assignment(template="No Such Template " + frappe.generate_hash(length=6)).insert(
                ignore_permissions=True
            )

    def test_framework_refuses_a_building_that_does_not_exist(self):
        with self.assertRaisesRegex(frappe.LinkValidationError, "Could not find"):
            _assignment(building="No Such Building " + frappe.generate_hash(length=6)).insert(
                ignore_permissions=True
            )


class TestScheduledTaskAssignmentNamingAndDefaults(FrappeTestCase):
    def test_the_assignment_is_named_from_the_declared_expression(self):
        doc = _assignment().insert(ignore_permissions=True)
        self.assertTrue(doc.name.startswith("STA-"))

    def test_a_new_assignment_is_active_without_the_operator_saying_so(self):
        doc = _assignment().insert(ignore_permissions=True)
        self.assertEqual(doc.is_active, 1)


TEST_ASSIGNMENTS = (
    ("_T-Scheduled Task Assignment-00001", "_Test Monthly AC Check", "2026-01-01"),
    ("_T-Scheduled Task Assignment-00002", "_Test Weekly Fire Drill", "2026-06-01"),
)


def _make_test_records(verbose=None):
    names = []
    for name, template, effective_from in TEST_ASSIGNMENTS:
        if not frappe.db.exists("Scheduled Task Assignment", name):
            frappe.get_doc(
                {
                    "doctype": "Scheduled Task Assignment",
                    "template": template,
                    "building": "_Test Building",
                    "effective_from": effective_from,
                }
            ).insert(set_name=name)
        names.append(name)
    frappe.db.commit()
    return names
