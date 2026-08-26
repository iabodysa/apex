# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.tests.factories import make_employee


def _manifest(**overrides):
    fields = {"doctype": "Passenger Manifest", "dispatch_date": frappe.utils.today()}
    fields.update(overrides)
    return frappe.get_doc(fields)


class TestPassengerManifestDuplicatePassenger(FrappeTestCase):
    def test_one_employee_listed_twice_is_refused(self):
        employee = make_employee("_T-Manifest Twice").name
        doc = _manifest(passengers=[{"employee": employee}, {"employee": employee}])
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True)

    def test_two_rows_with_no_employee_are_accepted(self):
        doc = _manifest(
            passengers=[{"passenger_name": "_T-Guest A"}, {"passenger_name": "_T-Guest B"}]
        ).insert(ignore_permissions=True)
        self.assertEqual(doc.passenger_count, 2)


class TestPassengerManifestCount(FrappeTestCase):
    def test_the_count_follows_the_rows_rather_than_what_was_typed(self):
        employee = make_employee("_T-Manifest Counted").name
        doc = _manifest(passenger_count=99, passengers=[{"employee": employee}]).insert(
            ignore_permissions=True
        )
        self.assertEqual(doc.passenger_count, 1)

    def test_a_manifest_with_no_passenger_counts_zero(self):
        doc = _manifest(passenger_count=7, passengers=[]).insert(ignore_permissions=True)
        self.assertEqual(doc.passenger_count, 0)
