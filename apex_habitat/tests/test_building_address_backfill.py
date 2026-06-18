"""T-269: backfill Accommodation Building.building_address from the building's legacy
default native Address (Dynamic Link) when the field is empty, without clobbering a
building that already has one.

Covers both branches of the patch's execute():
- empty building_address + a Dynamic-Link Address  -> field becomes that address
- already-populated building_address               -> left untouched
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex_habitat.patches.v1_x.backfill_building_address_from_default_address import execute
from apex_habitat.tests.factories import make_building, make_company


def _make_address(title, link_building=None):
    """Insert a native Address (optionally Dynamic-Linked to a building) as Administrator."""
    links = (
        [{"link_doctype": "Accommodation Building", "link_name": link_building}]
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
        # make_building defaults company="Test AFMCO"; ensure it exists (link validation).
        make_company()
        # Per-test unique key so fixtures never collide across methods / reruns.
        self.key = self._testMethodName

    def test_empty_building_address_is_backfilled_from_default_address(self):
        bldg = make_building(name=f"T269 {self.key} B").name
        addr = _make_address(f"T269 {self.key} Addr", link_building=bldg).name
        # Precondition: the field is empty, the Dynamic Link exists.
        self.assertFalse(frappe.db.get_value("Accommodation Building", bldg, "building_address"))

        execute()

        self.assertEqual(
            frappe.db.get_value("Accommodation Building", bldg, "building_address"),
            addr,
            "empty building_address should be backfilled to the default linked Address",
        )

    def test_existing_building_address_is_left_untouched(self):
        # A standalone Address already chosen on the building...
        own = _make_address(f"T269 {self.key} Own").name
        bldg = make_building(name=f"T269 {self.key} B", building_address=own).name
        # ...and a DIFFERENT Address linked via Dynamic Link that the patch must NOT prefer.
        other = _make_address(f"T269 {self.key} Other", link_building=bldg).name
        self.assertNotEqual(own, other)

        execute()

        self.assertEqual(
            frappe.db.get_value("Accommodation Building", bldg, "building_address"),
            own,
            "a building that already has building_address must not be overwritten",
        )
