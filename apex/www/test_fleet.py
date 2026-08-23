# Copyright (c) 2026, Apex contributors

"""``/fleet`` must render Arabic like every sibling portal
(``www/driver.py``, ``www/masar.py``, ``www/housing.py``, ``www/fleet_os.py``),
regardless of the logged-in User's own ``language`` preference.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.www import fleet


class TestFleetPortalPinsArabic(FrappeTestCase):
    def test_get_context_sets_frappe_local_lang_to_arabic(self):
        frappe.local.lang = "en"
        with patch.object(fleet, "guest_redirect"), patch.object(
            fleet, "get_fleet_context", return_value={"capabilities": {}}
        ), patch.object(
            fleet, "publish_portal_context", side_effect=lambda context, **k: context
        ):
            fleet.get_context({})

        self.assertEqual(frappe.local.lang, "ar")
