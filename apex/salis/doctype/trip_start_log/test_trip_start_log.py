# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.test_runner import make_test_records
from frappe.tests.utils import FrappeTestCase


class TestTripStartLogStartDatetimeIsFrozenAfterSubmit(FrappeTestCase):
    def _submitted_log(self):
        make_test_records("Salis Vehicle")
        make_test_records("Salis Driver")
        make_test_records("Project")
        vehicle = frappe.get_all("Salis Vehicle", limit=1, pluck="name")[0]
        driver = frappe.get_all("Salis Driver", limit=1, pluck="name")[0]
        project = frappe.get_all("Project", limit=1, pluck="name")[0]

        trip_doc = frappe.new_doc("Dispatch Trip")
        trip_doc.trip_type = "Ad Hoc"
        trip_doc.vehicle = vehicle
        trip_doc.driver = driver
        trip_doc.project = project
        trip_doc.trip_date = "2026-08-20"
        trip_doc.append("stops", {"stop_name": "Camp Gate"})
        trip_doc.insert()
        trip = trip_doc.name

        doc = frappe.new_doc("Trip Start Log")
        doc.dispatch_trip = trip
        doc.status = "Started"
        doc.start_datetime = "2026-08-20 06:00:00"
        doc.insert()
        doc.submit()
        return doc

    def test_editing_start_datetime_after_submit_is_refused(self):
        doc = self._submitted_log()
        doc.start_datetime = "2026-08-20 07:00:00"
        self.assertRaises(frappe.exceptions.UpdateAfterSubmitError, doc.save)
