# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.tests.factories import make_building

test_ignore = ["Asset"]


def _asset(**overrides):
    fields = {
        "doctype": "Facility Asset",
        "asset_name": "_T-Asset " + frappe.generate_hash(length=6),
        "asset_category": "CCTV Camera",
        "building": None,
        "responsible_supervisor": "Administrator",
    }
    fields.update(overrides)
    if fields.get("building") is None:
        fields["building"] = make_building("Facility Asset Test Building", company="_Test Company").name
    return frappe.get_doc(fields)


class TestFacilityAssetMandatoryIdentity(FrappeTestCase):
    def test_framework_refuses_an_asset_with_no_name(self):
        with self.assertRaises(frappe.MandatoryError):
            _asset(asset_name=None).insert(ignore_permissions=True)

    def test_an_omitted_category_falls_to_the_first_declared_option_rather_than_being_refused(self):
        doc = _asset(asset_category=None).insert(ignore_permissions=True)
        self.assertEqual(doc.asset_category, "CCTV Camera")

    def test_framework_refuses_an_asset_with_no_building(self):
        with self.assertRaises(frappe.MandatoryError):
            _asset(building="").insert(ignore_permissions=True)

    def test_framework_refuses_a_read_only_supervisor_left_empty(self):
        with self.assertRaises(frappe.MandatoryError):
            _asset(responsible_supervisor=None).insert(ignore_permissions=True)


class TestFacilityAssetLinks(FrappeTestCase):
    def test_framework_refuses_a_building_that_does_not_exist(self):
        with self.assertRaisesRegex(frappe.LinkValidationError, "Could not find"):
            _asset(building="No Such Building " + frappe.generate_hash(length=6)).insert(
                ignore_permissions=True
            )

    def test_framework_refuses_a_supervisor_who_is_not_a_user(self):
        with self.assertRaisesRegex(frappe.LinkValidationError, "Could not find"):
            _asset(responsible_supervisor="nobody" + frappe.generate_hash(length=6) + "@example.com").insert(
                ignore_permissions=True
            )

    def test_framework_refuses_an_erpnext_asset_that_does_not_exist(self):
        with self.assertRaisesRegex(frappe.LinkValidationError, "Could not find"):
            _asset(linked_erpnext_asset="ACC-ASS-9999-99999").insert(ignore_permissions=True)


class TestFacilityAssetVocabularyAndNaming(FrappeTestCase):
    def test_framework_refuses_a_category_outside_the_select_options(self):
        with self.assertRaisesRegex(frappe.ValidationError, 'cannot be "Submarine"'):
            _asset(asset_category="Submarine").insert(ignore_permissions=True)

    def test_framework_refuses_a_status_outside_the_select_options(self):
        with self.assertRaisesRegex(frappe.ValidationError, 'cannot be "Melted"'):
            _asset(status="Melted").insert(ignore_permissions=True)

    def test_the_asset_is_named_from_the_declared_series(self):
        doc = _asset().insert(ignore_permissions=True)
        self.assertTrue(doc.name.startswith("FAC-AST-"))

    def test_a_new_asset_is_operational_and_has_never_moved(self):
        doc = _asset().insert(ignore_permissions=True)
        self.assertEqual(doc.status, "Operational")
        self.assertEqual(doc.movement_count or 0, 0)
