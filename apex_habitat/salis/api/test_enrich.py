"""Tests for the shared Salis title-enrichment helper + the output-key drift fix.

``vehicle_driver_titles`` is the single bulk path that attaches the human-readable
plate + driver name to dispatch-board / fuel-console / operations-alert rows. The
historical bug these tests lock down: the three readers had drifted on the plate
output key (``vehicle_plate`` vs ``plate_number``). The canonical key is
``vehicle_plate``; every consumer must expose it and none may expose the old
``plate_number`` on its enriched rows.

The helper is exercised with ``frappe.get_all`` patched at its import site, so the
bulk lookup count and the docname fallback are asserted deterministically without
depending on seeded data. The consumer readers are asserted at source level so the
canonical key is verified for all three even where wiring the full board response
is heavy.
"""

from __future__ import annotations

import inspect
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex_habitat.salis.api import dispatch_board, fuel_console, operations_alerts
from apex_habitat.salis.api.enrich import (
    DRIVER_NAME_KEY,
    VEHICLE_PLATE_KEY,
    vehicle_driver_titles,
)

_GET_ALL = "apex_habitat.salis.api.enrich.frappe.get_all"


def _fake_get_all(plates: dict, names: dict):
    """Return a get_all stand-in resolving Salis Vehicle/Driver titles from maps."""

    def _impl(doctype, filters=None, fields=None, **kwargs):
        wanted = (filters or {}).get("name", [None, []])[1]
        if doctype == "Salis Vehicle":
            return [frappe._dict(name=k, plate_number=plates[k]) for k in wanted if k in plates]
        if doctype == "Salis Driver":
            return [frappe._dict(name=k, full_name=names[k]) for k in wanted if k in names]
        return []

    return _impl


class TestVehicleDriverTitles(FrappeTestCase):
    def test_canonical_keys_and_bulk_resolution(self):
        rows = [
            frappe._dict(vehicle="V1", driver="D1"),
            frappe._dict(vehicle="V2", driver="D1"),  # repeats -> deduped in the lookup
            frappe._dict(vehicle="V3", driver=None),  # missing driver
        ]
        plates = {"V1": "AAA 111", "V2": "BBB 222"}  # V3 absent -> docname fallback
        names = {"D1": "Sara Driver"}

        fake = _fake_get_all(plates, names)
        with patch(_GET_ALL, side_effect=fake) as mocked:
            vehicle_driver_titles(rows)

        # Two bounded queries total (one per referenced DocType), never N+1.
        self.assertEqual(mocked.call_count, 2)

        # Canonical key is populated; the drifted key is never written.
        self.assertEqual(rows[0][VEHICLE_PLATE_KEY], "AAA 111")
        self.assertEqual(rows[0][DRIVER_NAME_KEY], "Sara Driver")
        self.assertNotIn("plate_number", rows[0])

        # Missing-title fallback returns the docname (plate) / docname (driver).
        self.assertEqual(rows[2][VEHICLE_PLATE_KEY], "V3")
        self.assertIsNone(rows[2][DRIVER_NAME_KEY])  # no driver ref -> None passthrough

    def test_empty_rows_make_no_queries(self):
        with patch(_GET_ALL, side_effect=AssertionError("must not query")) as mocked:
            self.assertEqual(vehicle_driver_titles([]), [])
        mocked.assert_not_called()

    def test_custom_field_names(self):
        rows = [frappe._dict(veh="V1", drv="D1")]
        fake = _fake_get_all({"V1": "AAA 111"}, {"D1": "Sara Driver"})
        with patch(_GET_ALL, side_effect=fake):
            vehicle_driver_titles(rows, vehicle_field="veh", driver_field="drv")
        self.assertEqual(rows[0][VEHICLE_PLATE_KEY], "AAA 111")
        self.assertEqual(rows[0][DRIVER_NAME_KEY], "Sara Driver")


class TestConsumersReadCanonicalKey(FrappeTestCase):
    """Lock the drift fix: every consumer reads ``vehicle_plate``, none reads the
    old ``plate_number`` on an enriched row, and all delegate to the one helper."""

    def test_all_consumers_call_the_shared_helper(self):
        for mod in (dispatch_board, fuel_console, operations_alerts):
            self.assertIs(
                mod.vehicle_driver_titles,
                vehicle_driver_titles,
                f"{mod.__name__} must import the shared enrich.vehicle_driver_titles",
            )

    def test_no_consumer_emits_the_drifted_plate_key(self):
        # The old alert reader wrote a["plate_number"]; the fuel reader emitted a
        # "plate_number" map key. Neither pattern may survive in the sources.
        for mod in (dispatch_board, fuel_console, operations_alerts):
            src = inspect.getsource(mod)
            self.assertNotIn('"plate_number"]', src, f"{mod.__name__} still assigns plate_number")
            self.assertNotIn('["plate_number"]', src, f"{mod.__name__} still assigns plate_number")

    def test_fuel_console_output_uses_canonical_key(self):
        src = inspect.getsource(fuel_console.get_pending_fuel_requests)
        self.assertIn('"vehicle_plate"', src)
        self.assertNotIn('"plate_number"', src)
