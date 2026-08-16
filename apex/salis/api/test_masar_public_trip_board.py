# Copyright (c) 2026, AFMCO and contributors
"""Masar public trip board — get_public_trip_board (salis/api/masar.py).

An arrivals-board surface: which vehicle, which route, when it leaves, where it
stands, published with no token because there is nothing personal in it. Two
things are proven, and they are opposite halves of the same fixture:

  * a tokenless request returns the board — route name, departure time, the
    stop shape, the plate and the status;
  * the SAME tokenless request carries no worker identity anywhere in the
    payload — no employee name, no phone, no national id, none of the
    Manifest Passenger rows the personal endpoints expose.

The personal half (get_worker_transport, get_worker_boarding_pass) still
requires a resolved token; that refusal is proven directly here too, so the
"board is public, the ride is not" split is not asserted in only one direction.
"""

import json

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.api import masar
from apex.tests.factories import (
    WorkerTripMixin as _WorkerTripMixin,
    make_masar_building as _building,
    make_project as _project,
    make_test_driver as _ensure_test_driver,
    make_worker_employee as _employee,
)


class TestMasarPublicTripBoard(_WorkerTripMixin, FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.project = _project("Masar Public Board Project")
        cls.building = _building("Masar Public Board Building")
        cls.driver = _ensure_test_driver()
        cls.worker = _employee("Masar Public Board Worker")

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        if frappe.db.exists("Building", cls.building):
            frappe.delete_doc("Building", cls.building, ignore_permissions=True, force=True)
        if frappe.db.exists("Project", cls.project):
            frappe.delete_doc("Project", cls.project, ignore_permissions=True, force=True)
        frappe.db.commit()
        super().tearDownClass()

    def setUp(self):
        frappe.set_user("Guest")

    def tearDown(self):
        frappe.set_user("Administrator")

    def _forbidden_strings(self):
        """Every string a leak would have to contain -- the worker's own name and
        his Employee docname, which no board row has a reason to carry."""
        return [self.worker, frappe.db.get_value("Employee", self.worker, "employee_name")]

    def test_a_tokenless_request_returns_the_board(self):
        tr, rp, dt = self._worker_trip(
            self.driver, self.project, self.building, [self.worker], "Public Board Route"
        )
        result = masar.get_public_trip_board()

        row = next((r for r in result["trips"] if r["dispatch_trip"] == dt.name), None)
        self.assertIsNotNone(row, "the published trip must appear on the board")
        self.assertIn("route_name", row)
        self.assertIn("depart_time", row)
        self.assertIn("vehicle_plate", row)
        self.assertIn("status", row)
        self.assertTrue(row["stops"], "the board must carry the trip's stop shape")
        self.assertIn("stop_name", row["stops"][0])
        self.assertIn("planned_time", row["stops"][0])

    def test_the_same_request_carries_no_worker_identity(self):
        tr, rp, dt = self._worker_trip(
            self.driver, self.project, self.building, [self.worker], "Public Board Route Two"
        )
        result = masar.get_public_trip_board()

        payload = json.dumps(result, default=str)
        for forbidden in self._forbidden_strings():
            self.assertNotIn(
                forbidden, payload, f"the public board leaked {forbidden!r}"
            )
        row = next(r for r in result["trips"] if r["dispatch_trip"] == dt.name)
        for personal_key in ("passengers", "employee", "manifest", "phone", "national_id"):
            self.assertNotIn(personal_key, row)
            for stop in row["stops"]:
                self.assertNotIn(personal_key, stop)

    def test_the_personal_half_still_requires_a_token(self):
        with self.assertRaises(frappe.PermissionError):
            masar.get_worker_transport()
