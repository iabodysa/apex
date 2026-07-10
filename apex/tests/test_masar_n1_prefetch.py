# Copyright (c) 2026, AFMCO and contributors
"""Masar perf guard: the worker-route read path bulk-prefetches.

The driver "my worker route today" endpoint folds three helpers that each used to
issue one ``frappe.db.get_value`` per row inside a loop (N+1):

  * ``_today_worker_trips``  — Route Plan.transport_request + Transport Request.service_line per trip
  * ``_registered_workers``  — Employee.employee_name per manifest row
  * ``_ordered_stops``       — Accommodation Building per stop

Each now issues ONE bulk read keyed on the collected ids before the loop. These
tests are a regression fence on that property:

  1. **Query count is independent of row count** — the number of ``frappe.get_all``
     / ``frappe.db.get_value`` calls ``get_my_worker_route_today`` makes for a
     2-worker trip equals the count for a 6-worker trip. A reintroduced per-row
     lookup would make the larger trip issue more calls and fail this.
  2. **Output is behaviour-preserving** — the prefetched employee names + the
     pickup building surfaced by the endpoint equal the values a direct per-row
     read returns, so the refactor changed performance only, not the payload.

The trip fixture + driver/employee chain are reused from
``test_masar_worker_movement`` so the suites stay convention-aligned and re-runs
on a non-fresh DB never duplicate.
"""


import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.api import masar
from apex.tests.factories import (
    WorkerTripMixin as _WorkerTripMixin,
    make_driver_chain as _ensure_driver_chain,
    make_masar_building as _building,
    make_worker_employee as _employee,
    make_project as _project,
)


class _CallCounter:
    """Wrap ``frappe.get_all`` and ``frappe.db.get_value`` to tally per-DocType
    read calls within a block. A bulk-prefetch issues a fixed number regardless of
    row count; an N+1 loop issues one per row."""

    def __init__(self):
        self.get_all_by_doctype: dict = {}
        self.get_value_by_doctype: dict = {}
        self._orig_get_all = None
        self._orig_get_value = None

    def __enter__(self):
        self._orig_get_all = frappe.get_all
        self._orig_get_value = frappe.db.get_value

        def counted_get_all(doctype, *a, **k):
            self.get_all_by_doctype[doctype] = self.get_all_by_doctype.get(doctype, 0) + 1
            return self._orig_get_all(doctype, *a, **k)

        def counted_get_value(doctype, *a, **k):
            self.get_value_by_doctype[doctype] = self.get_value_by_doctype.get(doctype, 0) + 1
            return self._orig_get_value(doctype, *a, **k)

        frappe.get_all = counted_get_all
        frappe.db.get_value = counted_get_value
        return self

    def __exit__(self, *exc):
        frappe.get_all = self._orig_get_all
        frappe.db.get_value = self._orig_get_value
        return False

    @property
    def total(self) -> int:
        return sum(self.get_all_by_doctype.values()) + sum(self.get_value_by_doctype.values())


class TestMasarWorkerRoutePrefetch(_WorkerTripMixin, FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        frappe.db.set_single_value("Salis Settings", "enable_driver_portal", 1)
        cls.project = _project("Masar N1 Project")
        cls.building = _building("Masar N1 Building")
        # [#llw7jc]
        cls.small_driver, cls.small_user = _ensure_driver_chain(
            "masar_n1_small_drv@example.com", "Masar N1 Small"
        )
        cls.large_driver, cls.large_user = _ensure_driver_chain(
            "masar_n1_large_drv@example.com", "Masar N1 Large"
        )
        cls.small_workers = [_employee(f"Masar N1 Small W{i}") for i in range(2)]
        cls.large_workers = [_employee(f"Masar N1 Large W{i}") for i in range(6)]

    @classmethod
    def tearDownClass(cls):
        # [#4w47gh]
        frappe.set_user("Administrator")
        if frappe.db.exists("Project", cls.project):
            frappe.delete_doc("Project", cls.project, ignore_permissions=True, force=True)
        frappe.db.commit()
        super().tearDownClass()

    def setUp(self):
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")

    def _route_today_as(self, driver, user, workers, route_name):
        """Seed a Workers-line trip for ``driver`` and call the endpoint as their
        own user, returning ``(payload, call_counter)``."""
        self._worker_trip(driver, self.project, self.building, workers, route_name)
        frappe.set_user(user)
        try:
            with _CallCounter() as counter:
                payload = masar.get_my_worker_route_today()
        finally:
            frappe.set_user("Administrator")
        return payload, counter

    def test_query_count_independent_of_worker_count(self):
        """The read path issues the SAME number of DB read calls for a 6-worker
        trip as for a 2-worker trip — proof the N+1 loops are gone."""
        small_payload, small_counter = self._route_today_as(
            self.small_driver, self.small_user, self.small_workers, "N1 Small Route"
        )
        large_payload, large_counter = self._route_today_as(
            self.large_driver, self.large_user, self.large_workers, "N1 Large Route"
        )

        # [#nvqmbz]
        self.assertEqual(len(small_payload["trips"]), 1)
        self.assertEqual(len(large_payload["trips"]), 1)
        self.assertEqual(len(small_payload["trips"][0]["workers"]), 2)
        self.assertEqual(len(large_payload["trips"][0]["workers"]), 6)

        self.assertEqual(
            large_counter.total,
            small_counter.total,
            "Read-call count grew with worker count — an N+1 per-row lookup is back. "
            f"small={small_counter.get_all_by_doctype}/{small_counter.get_value_by_doctype} "
            f"large={large_counter.get_all_by_doctype}/{large_counter.get_value_by_doctype}",
        )

        # [#tmrfkp]
        self.assertLessEqual(large_counter.get_all_by_doctype.get("Employee", 0), 1)
        self.assertLessEqual(large_counter.get_all_by_doctype.get("Building", 0), 1)
        # [#rszb76]
        self.assertLessEqual(large_counter.get_value_by_doctype.get("Employee", 0), 1)
        self.assertEqual(large_counter.get_value_by_doctype.get("Building", 0), 0)

    def test_prefetched_output_matches_per_row_reads(self):
        """The endpoint's prefetched values equal a direct per-row read — the
        refactor is behaviour-preserving, not just faster."""
        payload, _ = self._route_today_as(
            self.large_driver, self.large_user, self.large_workers, "N1 Parity Route"
        )
        trip = payload["trips"][0]

        # [#q69g5q]
        for w in trip["workers"]:
            expected = frappe.db.get_value("Employee", w["employee"], "employee_name")
            self.assertEqual(w["employee_name"], expected)

        # [#6i4gtw]
        housing_stop = next(s for s in trip["stops"] if s.get("accommodation_building"))
        b = frappe.db.get_value(
            "Building",
            housing_stop["accommodation_building"],
            ["name", "building_name", "city", "district", "google_maps_url"],
            as_dict=True,
        )
        self.assertEqual(housing_stop["pickup"]["name"], b["name"])
        self.assertEqual(housing_stop["pickup"]["building_name"], b["building_name"])
        self.assertEqual(housing_stop["pickup"]["google_maps_url"], b["google_maps_url"])
