# Copyright (c) 2026, afmcoltd
"""What a QR Location guarantees, asserted against the DocType itself.

Patterned on frappe's own document lifecycle tests (``frappe/tests/test_document.py``,
``test_insert``). ``before_save`` is a module-level function wired through ``hooks.py``'s
``doc_events`` (not a method on the ``Document`` subclass), so it only runs through the
real lifecycle call — ``insert()`` — exercised below.

The guarantee: every QR Location resolves to a public request URL keyed by a token, and
that token is generated once — a location already carrying one keeps it, so reprinting or
resaving a poster never invalidates the QR code already stuck on a wall.
"""

import frappe
from frappe.tests.utils import FrappeTestCase


class TestQRLocation(FrappeTestCase):
    def test_a_location_without_a_token_is_given_one_and_a_matching_public_url(self):
        """A poster cannot be printed until it has a token to encode; before_save must
        generate one rather than leaving the QR unresolvable."""
        location = frappe.copy_doc(frappe.get_test_records("QR Location")[0])
        self.assertFalse(location.location_token)

        location.insert()

        self.assertTrue(location.location_token)
        self.assertIn(f"token={location.location_token}", location.public_url)

    def test_a_location_with_an_existing_token_keeps_it(self):
        """Regenerating the token on every save would invalidate every QR poster already
        printed and stuck on a wall."""
        location = frappe.copy_doc(frappe.get_test_records("QR Location")[0])
        location.location_token = "_T-fixed-poster-token"

        location.insert()

        self.assertEqual(location.location_token, "_T-fixed-poster-token")
        self.assertIn("token=_T-fixed-poster-token", location.public_url)
