# Copyright (c) 2026, AFMCO and contributors
"""the worker transport read must not query a trip's status per row.

``get_worker_transport`` batch-fetches every Dispatch Trip the caller's requests
point at, and must fold that same trip's ``status`` into the same batch rather than
issuing a separate ``frappe.db.get_value`` per row three lines below it — a per-row
read there silently reintroduces the N+1 this file guards against.

The measurement, not the assertion, is the point: this counts the Dispatch Trip
reads the endpoint makes and requires the count to stay flat as the request count
grows. A per-row read makes it climb with the rows.

One row shape is deliberately excluded from the batch and must stay a read: a
request with no stored ``dispatch_trip`` has its trip resolved live, so it is
outside the batch by construction. Every request seeded here carries a stored trip,
which is the shape the batch is supposed to cover.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.api import masar
from apex.tests.factories import (
    WorkerTripMixin as _WorkerTripMixin,
    ensure_worker_token,
    make_masar_building as _building,
    make_project as _project,
    make_test_driver as _ensure_test_driver,
    make_worker_employee as _employee,
)


class _TripReads:
    """Tally ``frappe.db.get_value`` calls per DocType across a block."""

    def __init__(self):
        self.by_doctype: dict = {}
        self._orig = None

    def __enter__(self):
        self._orig = frappe.db.get_value

        def counted(doctype, *a, **k):
            self.by_doctype[doctype] = self.by_doctype.get(doctype, 0) + 1
            return self._orig(doctype, *a, **k)

        frappe.db.get_value = counted
        return self

    def __exit__(self, *exc):
        frappe.db.get_value = self._orig
        return False

    @property
    def dispatch_trip(self):
        return self.by_doctype.get("Dispatch Trip", 0)


class TestTransportStatusComesFromTheBatch(_WorkerTripMixin, FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.project = _project("Masar SB Project")
        cls.building = _building("Masar SB Building")
        cls.driver = _ensure_test_driver()

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        if frappe.db.exists("Project", cls.project):
            frappe.delete_doc("Project", cls.project, ignore_permissions=True, force=True)
        frappe.db.commit()
        super().tearDownClass()

    def setUp(self):
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")

    def _reads_for(self, worker, trip_count):
        """Seed ``trip_count`` trips carrying ``worker`` and count the endpoint's
        Dispatch Trip reads."""
        for i in range(trip_count):
            self._worker_trip(
                self.driver, self.project, self.building, [worker], f"SB Route {i}"
            )
        token = ensure_worker_token(worker)
        with _TripReads() as reads:
            masar.get_worker_transport(token=token)
        return reads.dispatch_trip

    def test_dispatch_trip_reads_do_not_grow_with_the_request_count(self):
        """The invariant a per-row read breaks: one trip and three trips must cost
        the same number of Dispatch Trip reads."""
        one = self._reads_for(_employee("Masar SB One"), 1)
        three = self._reads_for(_employee("Masar SB Three"), 3)
        self.assertEqual(
            one,
            three,
            "Dispatch Trip reads grew with the request count: {0} for one request, "
            "{1} for three — a per-row read is back".format(one, three),
        )

    def test_a_stored_trip_costs_no_status_read_at_all(self):
        """Stronger than flatness: a request whose trip is already in the batch must
        cost zero Dispatch Trip reads, because the batch carries its status."""
        reads = self._reads_for(_employee("Masar SB Zero"), 2)
        self.assertEqual(
            reads,
            0,
            "the endpoint read Dispatch Trip {0} time(s) for requests whose trips "
            "were already batch-fetched".format(reads),
        )
