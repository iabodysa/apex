# Copyright (c) 2026, afmcoltd
"""What a Wash Platform guarantees, asserted against the DocType itself.

The only server-side rule this master carries is that ``platform_name`` is
trimmed on save so its stored value matches what Frappe derives the document
name from — ``autoname`` is ``field:platform_name`` (the same shape already
pinned for Fuel Platform, Rental Office and Vehicle Category).
"""

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = []


class TestWashPlatform(FrappeTestCase):
    def test_platform_name_is_trimmed_on_save_and_matches_the_document_name(self):
        """A name with stray leading/trailing whitespace must not be stored verbatim."""
        platform = frappe.copy_doc(frappe.get_test_records("Wash Platform")[0])
        platform.platform_name = "  _T-Padded Wash Bay  "
        platform.insert()
        self.assertEqual(platform.platform_name, "_T-Padded Wash Bay")
        self.assertEqual(platform.name, platform.platform_name)
