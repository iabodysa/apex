"""Guard: the Masar enum endpoint must cover the live Select options in Arabic.

The Masar worker portal localizes server enum values (DocType Select options) for
Arabic mode from a SINGLE source: the backend ``get_enum_labels`` endpoint reads
each field's live options and maps them to their ``ar.csv`` translation
(``salis/api/masar.py``). The SPA renders the raw English value when no label is
returned — so any live option missing an Arabic translation silently renders
ENGLISH inside the Arabic UI (the recurring "language changes in places" class).

This test calls the endpoint and asserts that every live option of each enum
field has a non-identity Arabic label, failing the build the moment an option is
added/renamed (or its ar.csv row is dropped) without a translation. This replaces
the older guard that locked a hand-maintained JS map; the durable native-first
fix (server-driving the label from ar.csv) is now in place, and this locks its
coverage.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex_habitat.salis.api.masar import _ENUM_SOURCES, get_enum_labels


class TestWorkerPortalEnumCoverage(FrappeTestCase):
    def test_endpoint_covers_live_options_in_arabic(self):
        labels = get_enum_labels(lang="ar")
        missing = []
        for ns, (dt, field) in _ENUM_SOURCES.items():
            meta_field = frappe.get_meta(dt).get_field(field)
            self.assertIsNotNone(
                meta_field, f"{dt}.{field} missing (declared enum source for '{ns}')"
            )
            ns_labels = labels.get(ns, {})
            options = [o.strip() for o in (meta_field.options or "").split("\n") if o.strip()]
            for opt in options:
                if not ns_labels.get(opt):
                    missing.append(f"{ns} ({dt}.{field}): '{opt}'")
        self.assertEqual(
            sorted(missing),
            [],
            "Masar Select options with no Arabic label from get_enum_labels "
            f"(would render English in Arabic mode): {sorted(missing)}",
        )
