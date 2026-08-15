# Copyright (c) 2026, AFMCO Support Services Co. Ltd and Contributors

import frappe
from frappe.tests.utils import FrappeTestCase


class TestWashPlatform(FrappeTestCase):
    def test_platform_name_is_trimmed(self):
        """validate() trims the platform name so the stored value matches the name
        Frappe derives from it via ``autoname: field:platform_name``. The blank/absent
        rejection is stock Frappe ``reqd: 1`` on the field, not app logic to re-test."""
        doc = frappe.get_doc({"doctype": "Wash Platform", "platform_name": " Shell "})
        doc.insert(ignore_permissions=True)
        self.addCleanup(
            frappe.delete_doc, "Wash Platform", doc.name, force=True, ignore_permissions=True
        )
        self.assertEqual(doc.platform_name, "Shell")
        self.assertEqual(doc.name, "Shell")
