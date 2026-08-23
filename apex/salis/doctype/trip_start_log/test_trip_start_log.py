# Copyright (c) 2026, afmcoltd
"""``start_datetime`` (and its siblings ``boarded_count``, ``boarding_events``,
``stop_progress``) carried ``allow_on_submit: 1`` though every app write path
(the worker/driver boarding endpoints) only ever touches them on a strictly
draft log (``docstatus: 0`` — see apex/salis/api/driver_portal/__init__.py:197-205
and apex/salis/api/boarding_flow.py:621/821: "a submitted/cancelled log is
closed"). Removing the flag lets the framework refuse a post-submit edit again.
Proven through ``insert()``/``submit()``/``save()``, never by calling a
controller method directly.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


class TestTripStartLogStartDatetimeIsFrozenAfterSubmit(FrappeTestCase):
    def _submitted_log(self):
        from frappe.test_runner import make_test_records

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
