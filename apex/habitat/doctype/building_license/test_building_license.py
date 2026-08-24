# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from apex.habitat.doctype.building_license.building_license import derive_license_status


class TestDeriveLicenseStatus(FrappeTestCase):
    def test_an_expiry_today_or_earlier_is_expired(self):
        self.assertEqual(derive_license_status(today(), 30, on_date=today()), "Expired")

    def test_an_expiry_inside_the_lead_window_is_expiring_soon(self):
        on_date = today()
        expiry = add_days(on_date, 10)
        self.assertEqual(derive_license_status(expiry, 30, on_date=on_date), "Expiring Soon")

    def test_an_expiry_beyond_the_lead_window_is_active(self):
        on_date = today()
        expiry = add_days(on_date, 60)
        self.assertEqual(derive_license_status(expiry, 30, on_date=on_date), "Active")

    def test_a_negative_lead_time_is_floored_to_zero(self):
        on_date = today()
        expiry = add_days(on_date, 1)
        self.assertEqual(derive_license_status(expiry, -30, on_date=on_date), "Active")

    def test_the_boundary_day_itself_is_expiring_soon_not_active(self):
        on_date = today()
        expiry = add_days(on_date, 30)
        self.assertEqual(derive_license_status(expiry, 30, on_date=on_date), "Expiring Soon")


class TestBuildingLicenseOwnDecisions(FrappeTestCase):
    def _doc(self, **fields):
        doc = frappe.new_doc("Building License")
        doc.update(fields)
        return doc

    def test_an_expiry_on_or_before_the_issue_date_is_refused(self):
        doc = self._doc(issue_date="2026-06-01", expiry_date="2026-06-01")
        with self.assertRaises(frappe.ValidationError):
            doc._validate_dates()

    def test_an_expiry_after_the_issue_date_passes(self):
        doc = self._doc(issue_date="2026-06-01", expiry_date="2026-07-01")
        doc._validate_dates()

    def test_a_new_documents_status_is_derived_from_its_expiry(self):
        doc = self._doc(expiry_date=today(), renewal_lead_days=30)
        doc._sync_status()
        self.assertEqual(doc.status, "Expired")
