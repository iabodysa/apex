# Copyright (c) 2026, AFMCO and contributors
"""A-384 — the columns the board filters and sorts on must be reachable by an index.

Two framework facts make this necessary rather than obvious, and both were measured in
installed source rather than remembered:

* ``frappe/database/schema.py:66-76`` emits an index ONLY for a column whose field
  carries ``search_index``. A Link field gets no index for being a Link, so
  ``Dispatch Trip.status`` and ``.transport_request`` were full scans.
* ``creation`` is indexed only when the DocType sets ``sort_field`` to it, and every
  hot DocType here sorts by ``modified``, so that fallback does not apply either.

The assertion is on EXPLAIN, not on wall time. A full scan of a few hundred rows is
fast today and stops being fast later, so timing alone would pass while the defect
stays. Timings are printed for the record the card asks for, and asserted on nothing.
"""

import timeit

import frappe
from frappe.tests.utils import FrappeTestCase

# (label, sql, the column the plan must reach)
CASES = [
    (
        "Salis Driver filtered by status",
        "select name from `tabSalis Driver` where status='Active' limit 200",
    ),
    (
        "Transport Request filtered by status",
        "select name from `tabTransport Request` where status='New' limit 200",
    ),
    (
        "Dispatch Trip filtered by status",
        "select name from `tabDispatch Trip` where status='Dispatched' limit 200",
    ),
    (
        "Dispatch Trip filtered by transport_request",
        "select name from `tabDispatch Trip` where transport_request='X' limit 200",
    ),
    (
        "Dispatch Trip filtered by route_plan",
        "select name from `tabDispatch Trip` where route_plan='X' limit 200",
    ),
]


def _plan(sql):
    return frappe.db.sql(f"explain {sql}", as_dict=True)


class TestTheHotColumnsAreIndexed(FrappeTestCase):
    def test_every_filtered_column_is_reachable_by_an_index(self):
        unindexed = []
        for label, sql in CASES:
            rows = _plan(sql)
            used = any((r.get("key") or "").strip() for r in rows)
            scan = [r for r in rows if (r.get("type") or "") == "ALL"]
            seconds = timeit.timeit(lambda: frappe.db.sql(sql), number=10) / 10
            print(
                f"{label:44} {seconds * 1000:7.3f} ms  "
                f"key={rows[0].get('key') or '-'} type={rows[0].get('type')} "
                f"rows={rows[0].get('rows')}"
            )
            if not used and scan:
                unindexed.append(label)
        self.assertEqual(
            unindexed,
            [],
            "these queries reach no index and scan the whole table; add search_index "
            "to the column and ctl stamp before migrate",
        )

    def test_the_doctypes_declare_the_index_rather_than_relying_on_link_type(self):
        """schema.py:66-76 keys on search_index alone, so a Link field is not enough."""
        expected = {
            "Salis Driver": ["status"],
            "Transport Request": ["status"],
            "Dispatch Trip": ["status", "transport_request", "route_plan"],
        }
        missing = []
        for doctype, fieldnames in expected.items():
            meta = frappe.get_meta(doctype)
            for fieldname in fieldnames:
                field = meta.get_field(fieldname)
                self.assertIsNotNone(field, f"{doctype}.{fieldname} is gone")
                if not field.search_index:
                    missing.append(f"{doctype}.{fieldname}")
        self.assertEqual(missing, [], "search_index missing on a hot filter column")
