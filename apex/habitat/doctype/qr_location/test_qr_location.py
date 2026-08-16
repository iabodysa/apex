# Copyright (c) 2026, afmcoltd
"""Contract test for QR Location's ``before_save`` (A-564): generates a
``location_token`` when missing, and always rebuilds ``public_url`` from it."""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.doctype.qr_location.qr_location import before_save


class _StubQRLocation:
    def __init__(self, location_token=None):
        self.location_token = location_token
        self.public_url = None


class TestQRLocationBeforeSave(FrappeTestCase):
    def test_generates_a_token_when_missing(self):
        doc = _StubQRLocation(location_token=None)
        before_save(doc)
        self.assertTrue(doc.location_token)
        self.assertEqual(len(doc.location_token), 10)

    def test_keeps_an_existing_token(self):
        doc = _StubQRLocation(location_token="ABC1234567")
        before_save(doc)
        self.assertEqual(doc.location_token, "ABC1234567")

    def test_public_url_is_built_from_the_token(self):
        doc = _StubQRLocation(location_token="ABC1234567")
        before_save(doc)
        self.assertTrue(doc.public_url.endswith("/qr-request?token=ABC1234567"))

    def test_public_url_is_rebuilt_even_when_token_already_present(self):
        doc = _StubQRLocation(location_token="ABC1234567")
        doc.public_url = "stale"
        before_save(doc)
        self.assertNotEqual(doc.public_url, "stale")
        self.assertIn("token=ABC1234567", doc.public_url)

    def test_real_doctype_insert_round_trips_through_before_save(self):
        doc = frappe.get_doc(
            {
                "doctype": "QR Location",
                "poster_title": "A564 QR Test",
                "naming_series": "QR-LOC-.####",
            }
        )
        doc.insert(ignore_permissions=True)
        self.addCleanup(frappe.delete_doc, "QR Location", doc.name, force=True, ignore_permissions=True)
        self.assertTrue(doc.location_token)
        self.assertIn(doc.location_token, doc.public_url)
