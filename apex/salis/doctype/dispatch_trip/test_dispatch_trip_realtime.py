# Copyright (c) 2026, AFMCO and contributors
"""Dispatch Trip realtime publish.

A trip change (assignment / status / board) must push a ``driver_trip_update``
to the Dispatch Trip doctype room so subscribed drivers' portals refetch ahead
of a manual refresh. The driver portal mirrors the fleet portal's socket pattern
and degrades to its existing fetch if the socket is unavailable.

This proves the SERVER half: ``on_update`` calls ``frappe.publish_realtime``
with the right event, room (``doctype="Dispatch Trip"``) and ``after_commit``.
The true socket round-trip needs the live bench (the integrator confirms in
the browser).

The rider is the shipped fixture. Naming it as a dependency is what replaced the
``test_ignore`` block that used to prune the walk behind its construction.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

test_dependencies = ["Salis Driver"]

DRIVER_NAME = "_Test Driver"


class TestDispatchTripRealtime(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.driver = frappe.db.get_value("Salis Driver", {"full_name": DRIVER_NAME}, "name")

    def tearDown(self):
        frappe.set_user("Administrator")

    def test_on_update_publishes_driver_trip_update(self):
        with patch("frappe.publish_realtime") as pub:
            trip = frappe.get_doc(
                {
                    "doctype": "Dispatch Trip",
                    "trip_date": today(),
                    "driver": self.driver,
                    "status": "Planned",
                }
            )
            trip.insert(ignore_permissions=True)
            self.addCleanup(
                lambda: frappe.delete_doc(
                    "Dispatch Trip", trip.name, force=True, ignore_permissions=True
                )
            )

        calls = [
            c
            for c in pub.call_args_list
            if c.args and c.args[0] == "driver_trip_update"
        ]
        self.assertTrue(
            calls,
            "on_update must publish a driver_trip_update so drivers' portals refetch.",
        )
        kwargs = calls[0].kwargs
        self.assertEqual(
            kwargs.get("doctype"),
            "Dispatch Trip",
            "driver_trip_update must be routed to the Dispatch Trip doctype room "
            "(the socket server gates delivery on read permission).",
        )
        self.assertTrue(
            kwargs.get("after_commit"),
            "driver_trip_update must be after_commit so subscribers read committed state.",
        )
        self.assertEqual(
            calls[0].args[1].get("name"),
            trip.name,
            "The advisory payload should carry the trip name.",
        )
