# Copyright (c) 2026, afmcoltd
"""``_worker_transport_requests`` must not return a worker's entire ride history.

The query had no date floor and no row limit, so a long-tenured worker's
10-second poll (``masar.get_worker_transport``) grew without bound: every
shuttle he had ever been on, forever. This pins the floor
(``WORKER_TRANSPORT_HISTORY_DAYS``): a ride dated far enough in the past to sit
outside it is dropped, one inside it is kept, and a request that has no
``pickup_datetime`` yet (nothing to floor against — it is usually the newest,
unscheduled request) is never dropped by the floor.

Builds the Transport Request directly rather than through the driver-side
Route Plan/Dispatch Trip fixture: ``_worker_transport_requests`` reads only
Transport Request and its worker child table, so the heavier trip fixture
would exercise nothing this test needs.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.api import masar_routes
from apex.tests.factories import (
    make_masar_building as _building,
    make_project as _project,
    make_worker_employee as _employee,
)


class TestWorkerTransportRequestsWindow(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.project = _project("Masar Transport Window Project")
        cls.building = _building("Masar Transport Window Residence")
        cls.employee = _employee("Masar Transport Window Worker")

    def setUp(self):
        frappe.set_user("Administrator")
        self._trs = []
        self.addCleanup(self._purge_trs)

    def _purge_trs(self):
        frappe.set_user("Administrator")
        for name in self._trs:
            if frappe.db.exists("Transport Request", name):
                frappe.delete_doc(
                    "Transport Request", name, ignore_permissions=True, force=True
                )

    def _make_request(self, title, pickup_datetime=None):
        fields = {
            "doctype": "Transport Request",
            "service_line": "Site Transport",
            "request_type": "Accommodation to Project Shuttle",
            "project": self.project,
            "accommodation_building": self.building,
            "from_location": "Building Gate",
            "to_location": "Project Site",
            "source_channel": "Desk",
            "status": "New",
            "workers": [{"employee": self.employee, "pickup_point": title}],
        }
        if pickup_datetime is not None:
            fields["pickup_datetime"] = pickup_datetime
        tr = frappe.get_doc(fields).insert(ignore_permissions=True)
        self._trs.append(tr.name)
        return tr

    def test_a_ride_older_than_the_floor_is_dropped(self):
        old_date = frappe.utils.add_days(
            frappe.utils.today(), -(masar_routes.WORKER_TRANSPORT_HISTORY_DAYS + 1)
        )
        tr = self._make_request("Old Ride", pickup_datetime=f"{old_date} 07:00:00")

        rows = masar_routes._worker_transport_requests(self.employee)

        self.assertNotIn(tr.name, [r["name"] for r in rows])

    def test_a_ride_inside_the_floor_is_kept(self):
        recent_date = frappe.utils.add_days(frappe.utils.today(), -1)
        tr = self._make_request("Recent Ride", pickup_datetime=f"{recent_date} 07:00:00")

        rows = masar_routes._worker_transport_requests(self.employee)

        self.assertIn(tr.name, [r["name"] for r in rows])

    def test_a_ride_with_no_pickup_datetime_yet_is_never_floored_out(self):
        tr = self._make_request("Unscheduled Ride")

        rows = masar_routes._worker_transport_requests(self.employee)

        self.assertIn(tr.name, [r["name"] for r in rows])
