# Copyright (c) 2026, afmcoltd
"""What a Rental Office guarantees, asserted against the DocType itself.

The only server-side rule this master carries is that ``office_name`` is
trimmed on save so its stored value matches what Frappe derives the document
name from — ``autoname`` is ``field:office_name``, and Frappe's own naming
already normalizes the identifier it derives, so the trimmed field and the
document's name agree rather than diverging (see the Fuel Platform test, which
pins the same rule against the same autoname shape).
"""

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = []


class TestRentalOffice(FrappeTestCase):
    def test_office_name_is_trimmed_on_save_and_matches_the_document_name(self):
        """A name with stray leading/trailing whitespace must not be stored verbatim."""
        office = frappe.copy_doc(frappe.get_test_records("Rental Office")[0])
        office.office_name = "  _T-Padded Rental Office  "
        office.insert()
        self.assertEqual(office.office_name, "_T-Padded Rental Office")
        self.assertEqual(office.name, office.office_name)
