# Copyright (c) 2026, afmcoltd
"""What Arrival Batch guarantees, asserted against the DocType itself.

Patterned on ``frappe/tests/test_document.py`` — the subject is ``validate``. A manifest
is both a public intake surface and the desk's reconciliation record, so ``validate``
carries three separate jobs: reject a honeypot-filled submission (the web form copies
every one of its fields onto the document, honeypot included), cap the list at 500
expected workers, and derive ``expected_count``/``title`` so neither is ever hand-entered
out of step with the ``expected_workers`` table.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import formatdate

test_dependencies = ["Building"]


class TestArrivalBatch(FrappeTestCase):
    def test_a_clean_manifest_derives_its_count_and_title(self):
        """The acceptance case: a normal manifest inserts and its two derived fields line up."""
        record = frappe.copy_doc(frappe.get_test_records("Arrival Batch")[0])
        record.insert()

        self.assertEqual(record.expected_count, len(record.expected_workers))
        self.assertEqual(
            record.title,
            f"{record.building} - {formatdate(record.expected_date)}",
        )

    def test_a_honeypot_filled_submission_is_refused(self):
        """The web form copies every one of its fields onto the document, honeypot included."""
        record = frappe.copy_doc(frappe.get_test_records("Arrival Batch")[0])
        record.website_field = "filled-by-a-bot"

        with self.assertRaisesRegex(frappe.PermissionError, "Invalid submission"):
            record.insert()

    def test_a_manifest_over_five_hundred_workers_is_refused(self):
        """A manifest cannot list more workers than the cap the desk was sized for."""
        record = frappe.copy_doc(frappe.get_test_records("Arrival Batch")[0])
        record.set("expected_workers", [])
        for i in range(501):
            record.append("expected_workers", {"worker_name": f"_T-Overflow Worker {i}"})

        with self.assertRaisesRegex(frappe.ValidationError, "at most 500"):
            record.insert()
