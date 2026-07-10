# Copyright (c) 2026, AFMCO and contributors
"""T-269: backfill Accommodation Building.building_address from the building's legacy
default native Address (Dynamic Link) when the field is empty, without clobbering a
building that already has one.

Covers both branches of the patch's execute():
- empty building_address + a Dynamic-Link Address  -> field becomes that address
- already-populated building_address               -> left untouched
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.patches.v1_x.backfill_building_address_from_default_address import execute
from apex.tests.factories import make_building, make_company


def _make_address(title, link_building=None):
    """Insert a native Address (optionally Dynamic-Linked to a building) as Administrator."""
    links = (
        [{"link_doctype": "Building", "link_name": link_building}]
        if link_building
        else []
    )
    return frappe.get_doc(
        {
            "doctype": "Address",
            "address_title": title,
            "address_type": "Other",
            "address_line1": f"{title} Street 1",
            "city": "Riyadh",
            "links": links,
        }
    ).insert(ignore_permissions=True)


class TestBuildingAddressBackfill(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        # [#nvhgvp]
        make_company()
        # [#1i98hj]
        self.key = self._testMethodName

    def test_empty_building_address_is_backfilled_from_default_address(self):
        bldg = make_building(name=f"T269 {self.key} B").name
        addr = _make_address(f"T269 {self.key} Addr", link_building=bldg).name
        # [#q1lo3u]
        self.assertFalse(frappe.db.get_value("Building", bldg, "building_address"))

        execute()

        self.assertEqual(
            frappe.db.get_value("Building", bldg, "building_address"),
            addr,
            "empty building_address should be backfilled to the default linked Address",
        )

    def test_existing_building_address_is_left_untouched(self):
        # [#isatfx]
        own = _make_address(f"T269 {self.key} Own").name
        bldg = make_building(name=f"T269 {self.key} B", building_address=own).name
        # [#q0hcwi]
        other = _make_address(f"T269 {self.key} Other", link_building=bldg).name
        self.assertNotEqual(own, other)

        execute()

        self.assertEqual(
            frappe.db.get_value("Building", bldg, "building_address"),
            own,
            "a building that already has building_address must not be overwritten",
        )
