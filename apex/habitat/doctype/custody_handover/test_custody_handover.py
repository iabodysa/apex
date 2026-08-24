# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.doctype.custody_handover.custody_handover import hash_otp


class TestHashOtp(FrappeTestCase):
    def test_the_hash_is_deterministic_for_the_same_code_and_name(self):
        self.assertEqual(hash_otp("123456", "ACH-0001"), hash_otp("123456", "ACH-0001"))

    def test_a_different_document_name_salts_to_a_different_hash(self):
        self.assertNotEqual(hash_otp("123456", "ACH-0001"), hash_otp("123456", "ACH-0002"))

    def test_a_different_code_produces_a_different_hash(self):
        self.assertNotEqual(hash_otp("123456", "ACH-0001"), hash_otp("654321", "ACH-0001"))

    def test_the_hash_is_never_the_plaintext_code(self):
        self.assertNotIn("123456", hash_otp("123456", "ACH-0001"))


class TestValidateRefusals(FrappeTestCase):
    def _doc(self, **fields):
        doc = frappe.new_doc("Custody Handover")
        doc.update(fields)
        return doc

    def test_the_same_building_on_both_sides_is_refused(self):
        doc = self._doc(from_building="_Test Building", to_building="_Test Building")
        with self.assertRaises(frappe.ValidationError):
            doc.validate()

    def test_the_same_person_on_both_sides_is_refused(self):
        doc = self._doc(
            from_building="_Test Building",
            to_building="_Test Building 2",
            procurement_supervisor="user@example.com",
            receiving_supervisor="user@example.com",
        )
        with self.assertRaises(frappe.ValidationError):
            doc.validate()

    def test_a_non_positive_quantity_is_refused(self):
        doc = self._doc(from_building="_Test Building", to_building="_Test Building 2")
        doc.append("items", {"qty": 0})
        with self.assertRaises(frappe.ValidationError):
            doc.validate()

    def test_different_buildings_different_people_and_a_positive_qty_pass(self):
        doc = self._doc(
            from_building="_Test Building",
            to_building="_Test Building 2",
            procurement_supervisor="a@example.com",
            receiving_supervisor="b@example.com",
        )
        doc.append("items", {"qty": 5})
        doc.validate()
