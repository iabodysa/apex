# Copyright (c) 2026, afmcoltd

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.doctype.housing_assignment.housing_assignment import (
    _derive_place_from_bed,
    _flag_temporary_worker_past_expiry,
    _snapshot_agreed_rate,
)


def _bed_with_a_building():
    for bed in frappe.get_all("Bed", pluck="name"):
        room = frappe.db.get_value("Bed", bed, "room")
        if room and frappe.db.get_value("Room", room, "building"):
            return bed, room, frappe.db.get_value("Room", room, "building")
    return None, None, None


class TestSnapshotAgreedRate(FrappeTestCase):
    def test_a_blank_rate_is_filled_from_the_buildings_cost_per_bed(self):
        doc = frappe._dict(agreed_monthly_rate=None)
        building = frappe._dict(monthly_cost_per_capacity=850)
        _snapshot_agreed_rate(doc, building)
        self.assertEqual(doc.agreed_monthly_rate, 850)

    def test_an_operator_entered_rate_is_never_overwritten(self):
        doc = frappe._dict(agreed_monthly_rate=1200)
        building = frappe._dict(monthly_cost_per_capacity=850)
        _snapshot_agreed_rate(doc, building)
        self.assertEqual(doc.agreed_monthly_rate, 1200)

    def test_a_building_with_no_configured_rate_leaves_the_field_at_zero(self):
        doc = frappe._dict(agreed_monthly_rate=None)
        building = frappe._dict(monthly_cost_per_capacity=None)
        _snapshot_agreed_rate(doc, building)
        self.assertEqual(doc.agreed_monthly_rate, 0)


class TestFlagTemporaryWorkerPastExpiry(FrappeTestCase):
    def _doc(self, **fields):
        base = {"party_type": "Temporary Worker", "party": "_T-TW-0001", "check_in_date": None}
        base.update(fields)
        return frappe._dict(base)

    def test_a_non_temporary_worker_party_is_never_looked_up(self):
        doc = frappe._dict(party_type="Employee", party="HR-EMP-0001", check_in_date=None)
        with patch.object(frappe.db, "get_value") as mock_get_value:
            _flag_temporary_worker_past_expiry(doc)
            mock_get_value.assert_not_called()

    def test_no_party_named_is_never_looked_up(self):
        doc = frappe._dict(party_type="Temporary Worker", party=None, check_in_date=None)
        with patch.object(frappe.db, "get_value") as mock_get_value:
            _flag_temporary_worker_past_expiry(doc)
            mock_get_value.assert_not_called()

    def test_an_expiry_before_check_in_raises_the_warning(self):
        doc = self._doc(check_in_date="2026-06-01")
        with patch.object(frappe.db, "get_value", return_value="2026-05-01"), patch.object(
            frappe, "msgprint"
        ) as mock_msgprint:
            _flag_temporary_worker_past_expiry(doc)
            mock_msgprint.assert_called_once()
            self.assertEqual(mock_msgprint.call_args.kwargs.get("indicator"), "orange")

    def test_an_expiry_on_or_after_check_in_raises_nothing(self):
        doc = self._doc(check_in_date="2026-06-01")
        with patch.object(frappe.db, "get_value", return_value="2026-07-01"), patch.object(
            frappe, "msgprint"
        ) as mock_msgprint:
            _flag_temporary_worker_past_expiry(doc)
            mock_msgprint.assert_not_called()


class TestPlaceIsDerivedFromTheBed(FrappeTestCase):
    def test_both_hops_fill_from_the_bed_alone(self):
        bed, room, building = _bed_with_a_building()
        self.assertIsNotNone(bed, "no bed on this site names a room that names a building")

        doc = frappe._dict(bed=bed, room=None, building=None)
        _derive_place_from_bed(doc)
        self.assertEqual(doc.room, room)
        self.assertEqual(doc.building, building)

    def test_a_caller_supplied_value_is_never_overwritten(self):
        bed, room, _building = _bed_with_a_building()
        self.assertIsNotNone(bed)

        doc = frappe._dict(bed=bed, room=room, building="Chosen By Caller")
        _derive_place_from_bed(doc)
        self.assertEqual(doc.building, "Chosen By Caller")

    def test_no_bed_derives_nothing_rather_than_guessing(self):
        doc = frappe._dict(bed=None, room=None, building=None)
        _derive_place_from_bed(doc)
        self.assertIsNone(doc.room)
        self.assertIsNone(doc.building)

    def test_the_chain_still_does_not_resolve_on_its_own(self):
        doc = frappe.get_doc({"doctype": "Housing Assignment"})
        bed, _room, _building = _bed_with_a_building()
        doc.bed = bed
        if hasattr(doc, "set_fetch_from_values"):
            doc.set_fetch_from_values()
        self.assertIsNone(
            doc.get("building"),
            "fetch_from now cascades server-side — _derive_place_from_bed is redundant",
        )


class TestTermsConsentIsSubmitLocked(FrappeTestCase):
    def _submitted_assignment(self):
        name = frappe.db.get_value(
            "Housing Assignment",
            {
                "docstatus": 1,
                "room": ("is", "set"),
                "bed": ("is", "set"),
                "project": ("is", "set"),
            },
            "name",
            order_by="creation asc",
        )
        if not name:
            doc = frappe.get_doc(frappe.get_test_records("Housing Assignment")[0])
            doc.insert()
            doc.submit()
            name = doc.name
        return frappe.get_doc("Housing Assignment", name)

    def test_the_signature_cannot_be_replaced_after_submit(self):
        doc = self._submitted_assignment()
        doc.terms_signature = "data:image/png;base64,AAAA"
        with self.assertRaises(frappe.UpdateAfterSubmitError):
            doc.save()

    def test_the_acceptance_stamp_cannot_be_moved_after_submit(self):
        doc = self._submitted_assignment()
        doc.terms_accepted_on = "2026-01-01 00:00:00"
        with self.assertRaises(frappe.UpdateAfterSubmitError):
            doc.save()
