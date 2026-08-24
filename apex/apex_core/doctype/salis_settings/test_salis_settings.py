# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


class TestSalisSettingsRecoveryPercent(FrappeTestCase):
    def test_a_recovery_percent_above_fifty_is_refused(self):
        doc = frappe.get_single("Salis Settings")
        doc.enable_employee_advance_recovery = 0
        doc.employee_advance_recovery_max_percent = 75
        with self.assertRaises(frappe.ValidationError):
            doc.save(ignore_permissions=True)


class TestSalisSettingsAccentColor(FrappeTestCase):
    def test_an_accent_color_that_is_not_a_hex_colour_is_refused(self):
        doc = frappe.get_single("Salis Settings")
        doc.enable_employee_advance_recovery = 0
        doc.employee_advance_recovery_max_percent = None
        doc.accent_color = "not-a-colour"
        with self.assertRaises(frappe.ValidationError):
            doc.save(ignore_permissions=True)


class TestSalisSettingsFrontendBaseUrl(FrappeTestCase):
    def test_a_frontend_base_url_without_a_scheme_is_refused(self):
        doc = frappe.get_single("Salis Settings")
        doc.enable_employee_advance_recovery = 0
        doc.employee_advance_recovery_max_percent = None
        doc.accent_color = None
        doc.frontend_base_url = "ftp://salis-fleet.com"
        with self.assertRaisesRegex(frappe.ValidationError, "must start with http"):
            doc.save(ignore_permissions=True)


class TestSalisSettingsApprovalSwitch(FrappeTestCase):
    def _restore(self, switch, workflows):
        frappe.db.set_single_value("Salis Settings", "enable_approvals", switch)
        for name, is_active, document_type in workflows:
            frappe.db.set_value("Workflow", name, "is_active", is_active)
            frappe.clear_cache(doctype=document_type)

    def test_disabling_approvals_deactivates_every_salis_workflow(self):
        salis_doctypes = frappe.get_all("DocType", filters={"module": "Salis"}, pluck="name")
        workflows = frappe.get_all(
            "Workflow",
            filters={"document_type": ["in", salis_doctypes]},
            fields=["name", "is_active", "document_type"],
            as_list=True,
        )
        if not workflows:
            self.skipTest("No Salis workflow is installed on this site.")
        switch = frappe.db.get_single_value("Salis Settings", "enable_approvals")
        self.addCleanup(self._restore, switch, workflows)

        doc = frappe.get_single("Salis Settings")
        doc.enable_employee_advance_recovery = 0
        doc.employee_advance_recovery_max_percent = None
        doc.accent_color = None
        doc.frontend_base_url = None
        doc.enable_approvals = 0
        doc.save(ignore_permissions=True)

        for name, _is_active, _document_type in workflows:
            self.assertEqual(frappe.db.get_value("Workflow", name, "is_active"), 0)
