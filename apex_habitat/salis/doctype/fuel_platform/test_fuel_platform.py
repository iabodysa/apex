# Copyright (c) 2026, AFMCO Support Services Co. Ltd and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


class TestFuelPlatform(FrappeTestCase):
    def test_missing_platform_name_rejected(self):
        """validate() guards the mandatory Platform Name: a blank/absent name must
        be rejected rather than producing an unnamed master row."""
        doc = frappe.get_doc({"doctype": "Fuel Platform"})
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True)
