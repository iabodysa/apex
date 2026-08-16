# Copyright (c) 2026, AFMCO and contributors
"""The legacy /housing-count route redirects to the unified housing SPA's count view.

``get_context`` is the entire subject: it must set ``frappe.local.flags.redirect_location``
to the new route and raise ``frappe.Redirect`` rather than rendering ``housing-count.html``.
A caller that swallowed the redirect (or pointed it anywhere else) would silently keep
serving the retired page instead of forwarding to ``/housing#/count``.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.www.housing_count import get_context


class TestHousingCountRedirect(FrappeTestCase):
    def test_get_context_redirects_to_the_unified_housing_count_view(self):
        frappe.local.flags.redirect_location = None
        with self.assertRaises(frappe.Redirect):
            get_context({})
        self.assertEqual(frappe.local.flags.redirect_location, "/housing#/count")
