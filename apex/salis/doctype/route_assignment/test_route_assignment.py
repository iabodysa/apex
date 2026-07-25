# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Route Assignment controller.

Route Assignment carries no Python logic; its behaviour is the declarative
fetch_from chain that copies shift identity off the linked Work Shift. This
creates a Work Shift (via a Project) and asserts the fetched fields populate on
insert, and that the mandatory work_shift link is enforced. Requires a live
site."""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


class TestRouteAssignment(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.project = frappe.get_doc(
            {
                "doctype": "Project",
                "project_name": f"RA Fetch Project {frappe.generate_hash(length=12)}",
            }
        ).insert(ignore_permissions=True).name

        shift = frappe.new_doc("Work Shift")
        shift.shift_name = "RA Fetch Shift"
        shift.start_date = "2026-07-01"
        shift.start_time = "06:00:00"
        shift.end_time = "14:00:00"
        shift.project = self.project
        shift.is_active = 1
        self.work_shift = shift.insert(ignore_permissions=True).name

    def test_fetch_chain_populates_shift_identity(self):
        ra = frappe.new_doc("Route Assignment")
        ra.naming_series = "RA-.####"
        ra.work_shift = self.work_shift
        ra.insert(ignore_permissions=True)

        self.assertEqual(ra.shift_name, "RA Fetch Shift")
        self.assertEqual(ra.project, self.project)
        self.assertTrue(ra.shift_start_time)
        self.assertTrue(ra.shift_end_time)

    def test_work_shift_is_mandatory(self):
        ra = frappe.new_doc("Route Assignment")
        ra.naming_series = "RA-.####"
        with self.assertRaises(frappe.exceptions.MandatoryError):
            ra.insert(ignore_permissions=True)
