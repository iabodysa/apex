"""Driver portal CSRF bootstrap test.

A signed-in user's page context must carry the real session CSRF token. If it is
empty, the SPA sends no X-Frappe-CSRF-Token header and every logged-in POST (the
get_driver_context bootstrap and all write endpoints) fails with CSRFTokenError.
"""

import unittest

import frappe

from apex_habitat.www import driver as driver_page


class TestDriverPortalCsrf(unittest.TestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def test_context_carries_the_session_csrf_token(self):
        ctx = frappe._dict()
        driver_page.get_context(ctx)
        # [#e7solg]
        # [#rf28z1]
        self.assertTrue(ctx.csrf_token, "driver portal context must carry a CSRF token")
        self.assertNotEqual(ctx.csrf_token, "{{ csrf_token }}")
        self.assertEqual(ctx.csrf_token, frappe.session.data.csrf_token)
