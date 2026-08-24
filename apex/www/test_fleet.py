# Copyright (c) 2026, Apex contributors


from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.www import fleet


class TestFleetPortalLanguage(FrappeTestCase):
    def test_the_portal_keeps_the_language_the_framework_resolved_for_the_user(self):
        self.addCleanup(setattr, frappe.local, "lang", frappe.local.lang)
        frappe.local.lang = "en"
        with patch.object(fleet, "guest_redirect"), patch.object(
            fleet, "get_fleet_context", return_value={"capabilities": {}}
        ), patch.object(
            fleet, "publish_portal_context", side_effect=lambda context, **k: context
        ):
            fleet.get_context({})

        self.assertEqual(frappe.local.lang, "en")
