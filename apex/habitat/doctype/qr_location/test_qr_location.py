# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


class TestQRLocationTokenGeneration(FrappeTestCase):
    def test_a_missing_location_token_is_generated_and_embedded_in_the_public_url(self):
        doc = frappe.get_doc(
            {
                "doctype": "QR Location",
                "naming_series": "QR-LOC-.####",
                "poster_title": "_T-QR Guard",
            }
        )
        doc.insert(ignore_permissions=True)
        self.addCleanup(
            lambda name=doc.name: frappe.delete_doc(
                "QR Location", name, ignore_permissions=True, force=True
            )
        )
        self.assertEqual(len(doc.location_token), 10)
        self.assertIn(doc.location_token, doc.public_url)
