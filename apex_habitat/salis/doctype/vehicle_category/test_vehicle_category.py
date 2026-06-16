# Copyright (c) 2026, AFMCO Support Services Co. Ltd and Contributors
# [#hbxspc]

import frappe
from frappe.tests.utils import FrappeTestCase


class TestVehicleCategory(FrappeTestCase):
    def test_missing_category_name_rejected(self):
        """validate() guards the mandatory Category Name: a blank/absent name must
        be rejected rather than producing an unnamed master row."""
        doc = frappe.get_doc({"doctype": "Vehicle Category"})
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True)
