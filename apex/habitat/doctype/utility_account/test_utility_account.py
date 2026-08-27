# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.tests.factories import make_building


def _account(**overrides):
    fields = {
        "doctype": "Utility Account",
        "building": None,
        "utility_type": "Electricity",
        "account_number": "_T-UTIL-" + frappe.generate_hash(length=6),
    }
    fields.update(overrides)
    if fields.get("building") is None:
        fields["building"] = make_building("Utility Account Test Building", company="_Test Company").name
    return frappe.get_doc(fields)


class TestUtilityAccountNumberIsUnique(FrappeTestCase):
    def test_a_second_account_carrying_the_same_number_is_refused(self):
        first = _account().insert(ignore_permissions=True)
        with self.assertRaises((frappe.UniqueValidationError, frappe.DuplicateEntryError)):
            _account(account_number=first.account_number).insert(ignore_permissions=True)

    def test_the_same_number_is_refused_even_in_another_building(self):
        first = _account().insert(ignore_permissions=True)
        other = make_building("Utility Account Test Building 2", company="_Test Company").name
        with self.assertRaises((frappe.UniqueValidationError, frappe.DuplicateEntryError)):
            _account(account_number=first.account_number, building=other).insert(ignore_permissions=True)

    def test_framework_refuses_an_account_with_no_number(self):
        with self.assertRaises(frappe.MandatoryError):
            _account(account_number=None).insert(ignore_permissions=True)


class TestUtilityAccountBuildingAndType(FrappeTestCase):
    def test_framework_refuses_an_account_with_no_building(self):
        with self.assertRaises(frappe.MandatoryError):
            _account(building="").insert(ignore_permissions=True)

    def test_framework_refuses_a_building_that_does_not_exist(self):
        with self.assertRaisesRegex(frappe.LinkValidationError, "Could not find"):
            _account(building="No Such Building " + frappe.generate_hash(length=6)).insert(
                ignore_permissions=True
            )

    def test_an_omitted_utility_type_falls_to_the_first_declared_option_rather_than_being_refused(self):
        doc = _account(utility_type=None).insert(ignore_permissions=True)
        self.assertEqual(doc.utility_type, "Electricity")

    def test_framework_refuses_a_utility_type_outside_the_select_options(self):
        with self.assertRaisesRegex(frappe.ValidationError, 'cannot be "Sewage"'):
            _account(utility_type="Sewage").insert(ignore_permissions=True)


class TestUtilityAccountDefaults(FrappeTestCase):
    def test_a_new_account_is_active_and_carries_the_declared_variance_threshold(self):
        doc = _account().insert(ignore_permissions=True)
        self.assertEqual(doc.status, "Active")
        self.assertEqual(doc.variance_threshold_pct, 25)

    def test_an_unshared_meter_still_carries_the_full_cost_bearing_share(self):
        doc = _account().insert(ignore_permissions=True)
        self.assertEqual(doc.cost_bearing_pct, 100)

    def test_the_account_is_named_from_the_declared_series(self):
        doc = _account().insert(ignore_permissions=True)
        self.assertTrue(doc.name.startswith("UTIL-ACC-"))
