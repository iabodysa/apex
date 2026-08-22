# Copyright (c) 2026, afmcoltd
"""What a Vehicle Category guarantees, asserted against the DocType itself.

The only server-side rule this master carries is that ``category_name`` is
trimmed on save so its stored value matches what Frappe derives the document
name from — ``autoname`` is ``field:category_name`` (the same shape already
pinned for Fuel Platform and Rental Office).
"""

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = []


class TestVehicleCategory(FrappeTestCase):
    def test_category_name_is_trimmed_on_save_and_matches_the_document_name(self):
        """A name with stray leading/trailing whitespace must not be stored verbatim."""
        category = frappe.copy_doc(frappe.get_test_records("Vehicle Category")[0])
        category.category_name = "  _T-Padded Category  "
        category.insert()
        self.assertEqual(category.category_name, "_T-Padded Category")
        self.assertEqual(category.name, category.category_name)
