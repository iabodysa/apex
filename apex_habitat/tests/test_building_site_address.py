"""get_site_address honours the form's current Site over the building's stored one.

Regression for T-138: switching the Site dropdown before saving used to show the
OLD site's address, because the server read the building's saved `site` instead of
the form's value. The endpoint now accepts the current `site` and prefers it.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex_habitat.habitat.doctype.accommodation_building.accommodation_building import (
    get_site_address,
)
from apex_habitat.tests.factories import make_building


def _ensure_site(name):
    if not frappe.db.exists("Accommodation Site", name):
        frappe.get_doc(
            {"doctype": "Accommodation Site", "site_name": name}
        ).insert(ignore_permissions=True)
    return name


class TestBuildingSiteAddress(FrappeTestCase):
    def test_passed_site_overrides_stored_site(self):
        frappe.set_user("Administrator")
        site_a = _ensure_site("T138 Site A")
        site_b = _ensure_site("T138 Site B")
        # an Address linked only to site A
        if not frappe.db.exists("Address", {"address_title": "T138 A"}):
            frappe.get_doc(
                {
                    "doctype": "Address",
                    "address_title": "T138 A",
                    "address_type": "Other",
                    "address_line1": "A Street 1",
                    "city": "Riyadh",
                    "links": [{"link_doctype": "Accommodation Site", "link_name": site_a}],
                }
            ).insert(ignore_permissions=True)
        company = (
            frappe.defaults.get_global_default("company")
            or frappe.get_all("Company", limit=1)[0].name
        )
        bldg = make_building(name="T138 Building", site=site_a, company=company).name

        # stored-site fallback returns A's address (non-empty)
        self.assertTrue(get_site_address(bldg))
        # the form's current Site (B, which has no address) wins — empty, not A's stale address
        self.assertEqual(get_site_address(bldg, site=site_b), "")

    def test_building_address_overrides_site(self):
        """T-144: the building's own selected Address wins over the Site's; clearing it
        falls back to the Site."""
        frappe.set_user("Administrator")
        site_a = _ensure_site("T144 Site")
        if not frappe.db.exists("Address", {"address_title": "T144 Site Addr"}):
            frappe.get_doc(
                {
                    "doctype": "Address", "address_title": "T144 Site Addr",
                    "address_type": "Other", "address_line1": "Site Street", "city": "Riyadh",
                    "links": [{"link_doctype": "Accommodation Site", "link_name": site_a}],
                }
            ).insert(ignore_permissions=True)
        own = frappe.db.get_value("Address", {"address_title": "T144 Own Addr"})
        if not own:
            own = frappe.get_doc(
                {
                    "doctype": "Address", "address_title": "T144 Own Addr",
                    "address_type": "Other", "address_line1": "Own Street 9", "city": "Jeddah",
                }
            ).insert(ignore_permissions=True).name
        company = (
            frappe.defaults.get_global_default("company")
            or frappe.get_all("Company", limit=1)[0].name
        )
        bldg = make_building(name="T144 Building", site=site_a, company=company).name

        own_text = get_site_address(bldg, site=site_a, building_address=own)
        self.assertIn("Own Street 9", own_text)  # the building's own address wins
        self.assertNotIn("Site Street", own_text)  # not the site's
        self.assertIn("Site Street", get_site_address(bldg, site=site_a, building_address=""))
