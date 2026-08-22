# Copyright (c) 2026, afmcoltd
"""Facility Asset's own contract: it needs a name and a building, and it takes the name it is given.

The building comes from ``test_records.json``, so the link is really checked, rather than a
``QA-BLDG`` name that exists on no site with ``ignore_links=True`` passed to stop Frappe noticing,
or a sixteen-line ``test_ignore`` block for masters the asset does not link to.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.tests.factories import make_scoped_supervisor

test_dependencies = ["Building"]

# `linked_erpnext_asset` is the bridge to ERPNext Asset and no test record sets it, but
# `get_dependencies` (frappe/test_runner.py:358-380) walks every Link field regardless. Walking
# Asset drags in ERPNext's purchase chain, which ends at `Payment Gateway` — a DocType that ships
# with the separate `payments` app and is absent from a frappe/erpnext/hrms bench, so the walk
# raises DoesNotExistError before a single Facility Asset is created.
test_ignore = ["Asset"]

BUILDING = "_Test Building"
OTHER_BUILDING = "_Test Building 2"


class TestFacilityAsset(FrappeTestCase):
    def _asset(self, **overrides):
        payload = {
            "doctype": "Facility Asset",
            "naming_series": "FAC-AST-.YYYY.-.####",
            "asset_name": "_T CCTV Camera 1",
            "asset_category": "CCTV Camera",
            "building": BUILDING,
            "responsible_supervisor": "Administrator",
        }
        payload.update(overrides)
        return frappe.get_doc(payload)

    def test_an_asset_takes_the_name_it_is_given(self):
        asset = self._asset()
        asset.insert(ignore_permissions=True)
        self.addCleanup(
            frappe.delete_doc, "Facility Asset", asset.name, force=True, ignore_permissions=True
        )

        self.assertEqual(asset.asset_name, "_T CCTV Camera 1")
        self.assertEqual(asset.building, BUILDING)

    def test_an_asset_without_a_name_is_refused(self):
        asset = self._asset(asset_name=None)

        with self.assertRaises(frappe.exceptions.MandatoryError):
            asset.insert(ignore_permissions=True)

    def test_an_asset_without_a_building_is_refused(self):
        asset = self._asset(asset_name="_T Generator", asset_category="Generator", building=None)

        with self.assertRaises(frappe.exceptions.MandatoryError):
            asset.insert(ignore_permissions=True)


class TestFacilityAssetEstateScope(FrappeTestCase):
    """The supervisor's list read, performed the way the desk performs it.

    `Facility Asset` is scoped by a Building User Permission rather than a SQL
    fragment, and `db_query.add_user_permissions` (frappe/model/db_query.py:1067)
    walks EVERY Link field whose target is permitted. `previous_building` is such a
    field and `asset_movement_engine.set_previous_location` writes the counterparty
    estate into it, so without `ignore_user_permissions` on that field the receiving
    supervisor loses the asset they now hold.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.supervisor = make_scoped_supervisor(cls._user, BUILDING, cls.addClassCleanup)

    @classmethod
    def _user(cls, role):
        email = "fac-scope-{0}@example.com".format(frappe.generate_hash(length=8)).lower()
        frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": "Scope",
                "send_welcome_email": 0,
                "roles": [{"role": role}],
            }
        ).insert(ignore_permissions=True)
        cls.addClassCleanup(frappe.delete_doc, "User", email, force=True, ignore_permissions=True)
        return email

    def _insert(self, **overrides):
        payload = {
            "doctype": "Facility Asset",
            "naming_series": "FAC-AST-.YYYY.-.####",
            "asset_name": "_T Scope " + frappe.generate_hash(length=6),
            "asset_category": "CCTV Camera",
            "building": BUILDING,
            "responsible_supervisor": "Administrator",
        }
        payload.update(overrides)
        doc = frappe.get_doc(payload)
        doc.insert(ignore_permissions=True)
        self.addCleanup(
            frappe.delete_doc, "Facility Asset", doc.name, force=True, ignore_permissions=True
        )
        return doc.name

    def _visible_to_supervisor(self, name):
        frappe.set_user(self.supervisor)
        try:
            return bool(frappe.get_list("Facility Asset", filters={"name": name}, limit=1))
        finally:
            frappe.set_user("Administrator")

    def test_an_asset_moved_in_from_another_estate_stays_visible(self):
        name = self._insert(previous_building=OTHER_BUILDING)

        self.assertTrue(
            self._visible_to_supervisor(name),
            "the receiving supervisor lost an asset they hold, over where it used to be",
        )

    def test_another_estates_asset_is_still_hidden(self):
        """The control: without it, a scoping that had stopped working entirely
        would pass the test above."""
        name = self._insert(building=OTHER_BUILDING)

        self.assertFalse(self._visible_to_supervisor(name), "another estate's asset leaked")
