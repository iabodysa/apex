# Copyright (c) 2026, afmcoltd
"""What a Safety Task Catalog guarantees, asserted against the DocType itself.

Patterned on frappe's own document-validation tests (``frappe/tests/test_document.py``,
``test_validate``). The one guarantee: ``validate_source_provenance`` refuses a
worker-facing field (``task_title`` or ``instructions``) that still carries the name of
the spreadsheet it was bulk-imported from — the inspector walking the round reads that
field verbatim, so an import trail left in it would read as an instruction.
"""

import frappe
from frappe.tests.utils import FrappeTestCase


class TestSafetyTaskCatalog(FrappeTestCase):
    def test_a_task_title_carrying_an_import_file_name_is_refused(self):
        """An import trail left in the operator-facing title reads as an instruction to
        the inspector standing in front of the fire extinguisher."""
        catalog = frappe.copy_doc(frappe.get_test_records("Safety Task Catalog")[0])
        catalog.task_code = "_T-SAFE-002"
        catalog.task_title = "Fire Extinguisher Check import_batch_2026.xlsx"

        with self.assertRaisesRegex(frappe.ValidationError, "carries the file it was imported from"):
            catalog.insert()

    def test_a_task_title_without_a_file_name_is_accepted(self):
        """The acceptance counterpart — an ordinary title with no import trail must still
        save."""
        catalog = frappe.copy_doc(frappe.get_test_records("Safety Task Catalog")[0])
        catalog.task_code = "_T-SAFE-003"

        catalog.insert()

        self.assertEqual(catalog.task_title, "_Test Fire Extinguisher Check")
