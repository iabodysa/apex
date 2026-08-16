# Copyright (c) 2026, AFMCO and contributors
"""get_site_address resolves the building's address from the SAVED record.

Regression for: the building-address-over-site fallback is live in the
controller (building.get_site_address) but the existing suite only
drives it through the unsaved-form path, passing `site` /
`building_address` explicitly as keyword args. The persistence path — where BOTH
args are omitted (None) and the endpoint reads the STORED `building_address` and
`site` off the record — was never asserted.

These tests omit the args so the controller falls back to `frappe.db.get_value`
(controller lines reading the saved building_address, then the saved site), and
assert the precedence ORDER end-to-end from the database:
    stored building_address  >  stored site  >  empty.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.doctype.building.building import (
    get_site_address,
)
from apex.tests.factories import make_building, make_company


def _ensure_site(name):
    """Per-name idempotent Accommodation Site (re-runnable across test sessions)."""
    if not frappe.db.exists("Site", name):
        frappe.get_doc(
            {"doctype": "Site", "site_name": name}
        ).insert(ignore_permissions=True)
    return name


def _ensure_address(title, line1, city, link_doctype=None, link_name=None):
    """Per-title idempotent Address; optionally Dynamic-Linked to a parent so it is
    that parent's DEFAULT address (get_address_text resolves via get_default_address)."""
    existing = frappe.db.get_value("Address", {"address_title": title})
    if existing:
        return existing
    payload = {
        "doctype": "Address",
        "address_title": title,
        "address_type": "Other",
        "address_line1": line1,
        "city": city,
        "country": "Saudi Arabia",
    }
    if link_doctype and link_name:
        payload["links"] = [{"link_doctype": link_doctype, "link_name": link_name}]
    return frappe.get_doc(payload).insert(ignore_permissions=True).name


class TestBuildingAddressFallback(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        make_company()

    def test_saved_site_address_when_no_own_address(self):
        """No stored building_address but a stored site -> the SITE's address.

        Drives the saved-record fallback with NO args (the controller reads the
        stored `site` because both building_address and site are omitted).
        """
        site = _ensure_site("T143 Fallback Site A")
        _ensure_address(
            "T143 Fallback Site A Addr", "Site Street 5", "Riyadh",
            link_doctype="Site", link_name=site,
        )
        bldg = make_building(name="T143 Fallback Bldg A", site=site).name

        self.assertIn("Site Street 5", get_site_address(bldg))

    def test_saved_own_address_precedes_saved_site(self):
        """Both stored: the building's OWN address wins over the site's, resolved
        purely from the saved record (no args passed)."""
        site = _ensure_site("T143 Fallback Site B")
        _ensure_address(
            "T143 Fallback Site B Addr", "Site Street 7", "Riyadh",
            link_doctype="Site", link_name=site,
        )
        own = _ensure_address("T143 Fallback Own B Addr", "Own Street 9", "Jeddah")
        bldg = make_building(
            name="T143 Fallback Bldg B", site=site, building_address=own
        ).name

        text = get_site_address(bldg)
        self.assertIn("Own Street 9", text)
        self.assertNotIn("Site Street 7", text)

    def test_legacy_dynamic_link_own_address_precedes_site(self):
        """A legacy own Address linked via Dynamic Link (the pre-Link-field native
        widget) and NO stored building_address must still surface on the form,
        winning over the site's address instead of being silently shadowed."""
        site = _ensure_site("T139 Reconcile Site")
        _ensure_address(
            "T139 Reconcile Site Addr", "Site Street 21", "Riyadh",
            link_doctype="Site", link_name=site,
        )
        bldg = make_building(name="T139 Reconcile Bldg", site=site).name
        _ensure_address(
            "T139 Reconcile Own Addr", "Legacy Own Street 23", "Jeddah",
            link_doctype="Building", link_name=bldg,
        )

        text = get_site_address(bldg)
        self.assertIn("Legacy Own Street 23", text)
        self.assertNotIn("Site Street 21", text)

    def test_clearing_saved_own_address_falls_back_to_site(self):
        """Clearing the stored building_address on the record makes the next no-arg
        resolution fall back to the stored site again (the live fallback path)."""
        site = _ensure_site("T143 Fallback Site C")
        _ensure_address(
            "T143 Fallback Site C Addr", "Site Street 11", "Riyadh",
            link_doctype="Site", link_name=site,
        )
        own = _ensure_address("T143 Fallback Own C Addr", "Own Street 13", "Jeddah")
        bldg = make_building(
            name="T143 Fallback Bldg C", site=site, building_address=own
        ).name

        self.assertIn("Own Street 13", get_site_address(bldg))

        frappe.db.set_value("Building", bldg, "building_address", None)
        cleared = get_site_address(bldg)
        self.assertIn("Site Street 11", cleared)
        self.assertNotIn("Own Street 13", cleared)
