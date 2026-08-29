# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


def _service_platform(**overrides):
    fields = {
        "doctype": "Service Platform",
        "platform_name": "_T-ServicePlatform " + frappe.generate_hash(length=6),
        "service_type": "Fuel",
    }
    fields.update(overrides)
    return frappe.get_doc(fields)


class TestServicePlatformNaming(FrappeTestCase):
    def test_a_padded_name_is_stored_trimmed(self):
        bare = "_T-ServicePlatform " + frappe.generate_hash(length=6)
        doc = _service_platform(**{"platform_name": "  " + bare + "  "}).insert(ignore_permissions=True)
        self.assertEqual(doc.platform_name, bare)

    def test_the_trimmed_name_is_the_record_name(self):
        bare = "_T-ServicePlatform " + frappe.generate_hash(length=6)
        doc = _service_platform(**{"platform_name": bare + "   "}).insert(ignore_permissions=True)
        self.assertEqual(doc.name, bare)

    def test_a_missing_name_is_refused(self):
        doc = _service_platform(**{"platform_name": None})
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True)

    def test_a_missing_service_type_is_refused(self):
        doc = _service_platform(**{"service_type": None})
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True)
