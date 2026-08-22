# Copyright (c) 2026, afmcoltd
"""What a Fuel Platform guarantees, asserted against the DocType itself.

The only server-side rule this master carries is that ``platform_name`` is
trimmed on save so its stored value matches what Frappe derives the document
name from — ``autoname`` is ``field:platform_name``, and Frappe's own naming
already normalizes the identifier it derives, so the trimmed field and the
document's name agree rather than diverging.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = []


class TestFuelPlatform(FrappeTestCase):
    def test_platform_name_is_trimmed_on_save_and_matches_the_document_name(self):
        """A name with stray leading/trailing whitespace must not be stored verbatim."""
        platform = frappe.copy_doc(frappe.get_test_records("Fuel Platform")[0])
        platform.platform_name = "  _T-Padded Fuel Card  "
        platform.insert()
        self.assertEqual(platform.platform_name, "_T-Padded Fuel Card")
        self.assertEqual(platform.name, platform.platform_name)
