# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


def _template(**overrides):
    fields = {
        "doctype": "Scheduled Task Template",
        "template_name": "_T-Task Template " + frappe.generate_hash(length=6),
        "task_type": "Maintenance",
        "frequency": "Monthly",
    }
    fields.update(overrides)
    return frappe.get_doc(fields)


class TestTemplateNameIsTheRecordName(FrappeTestCase):
    def test_the_template_name_becomes_the_record_name(self):
        doc = _template().insert(ignore_permissions=True)
        self.assertEqual(doc.name, doc.template_name)

    def test_framework_refuses_a_second_template_carrying_the_same_name(self):
        first = _template().insert(ignore_permissions=True)
        with self.assertRaises((frappe.DuplicateEntryError, frappe.UniqueValidationError)):
            _template(template_name=first.template_name).insert(ignore_permissions=True)

    def test_the_naming_field_refuses_to_be_empty(self):
        with self.assertRaisesRegex(frappe.ValidationError, "Template Name is required"):
            _template(template_name=None).insert(ignore_permissions=True)


class TestScheduledTaskTemplateVocabulary(FrappeTestCase):
    def test_an_omitted_frequency_falls_to_the_declared_default_rather_than_being_refused(self):
        doc = _template(frequency=None).insert(ignore_permissions=True)
        self.assertEqual(doc.frequency, "Monthly")

    def test_framework_refuses_a_frequency_outside_the_select_options(self):
        with self.assertRaisesRegex(frappe.ValidationError, 'cannot be "Hourly"'):
            _template(frequency="Hourly").insert(ignore_permissions=True)

    def test_framework_refuses_a_task_type_outside_the_select_options(self):
        with self.assertRaisesRegex(frappe.ValidationError, 'cannot be "Catering"'):
            _template(task_type="Catering").insert(ignore_permissions=True)

    def test_a_new_template_is_active_and_monthly_by_default(self):
        doc = frappe.get_doc({
            "doctype": "Scheduled Task Template",
            "template_name": "_T-Task Template " + frappe.generate_hash(length=6),
        }).insert(ignore_permissions=True)
        self.assertEqual(doc.is_active, 1)
        self.assertEqual(doc.frequency, "Monthly")


class TestScheduledTaskTemplateLinks(FrappeTestCase):
    def test_framework_refuses_an_employee_that_does_not_exist(self):
        with self.assertRaisesRegex(frappe.LinkValidationError, "Could not find"):
            _template(assigned_to="HR-EMP-99999").insert(ignore_permissions=True)

    def test_framework_refuses_a_safety_task_catalog_that_does_not_exist(self):
        with self.assertRaisesRegex(frappe.LinkValidationError, "Could not find"):
            _template(safety_task_catalog="No Such Task " + frappe.generate_hash(length=6)).insert(
                ignore_permissions=True
            )

    def test_framework_refuses_a_task_row_that_names_no_catalog_entry(self):
        with self.assertRaises(frappe.MandatoryError):
            _template(template_items=[{"title": "row with no catalog entry"}]).insert(
                ignore_permissions=True
            )
