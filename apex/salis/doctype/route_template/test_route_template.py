# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


def _route_template(**overrides):
    fields = {
        "doctype": "Route Template",
        "template_name": "_T-RouteTemplate " + frappe.generate_hash(length=6),
        "route_type": "Pickup",
        "stops": [{"stop_name": "_T-Gate"}, {"stop_name": "_T-Yard"}],
    }
    fields.update(overrides)
    return frappe.get_doc(fields)


class TestRouteTemplateStops(FrappeTestCase):
    def test_a_template_with_no_stop_is_refused_by_the_controller(self):
        doc = _route_template(stops=[])
        with self.assertRaisesRegex(frappe.ValidationError, "at least one route stop"):
            doc.insert(ignore_permissions=True)

    def test_a_stop_named_only_in_spaces_is_refused_by_its_row_number(self):
        doc = _route_template(stops=[{"stop_name": "_T-Gate"}, {"stop_name": "   "}])
        with self.assertRaisesRegex(frappe.ValidationError, "Row 2"):
            doc.insert(ignore_permissions=True)


class TestRouteTemplateStopKeys(FrappeTestCase):
    def test_two_stops_sharing_one_key_are_refused(self):
        doc = _route_template(stops=[
            {"stop_name": "_T-Gate", "stop_key": "gate"},
            {"stop_name": "_T-Yard", "stop_key": "gate"},
        ])
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True)

    def test_a_missing_key_is_filled_in_sequence(self):
        doc = _route_template().insert(ignore_permissions=True)
        self.assertEqual([stop.stop_key for stop in doc.stops], ["stop-1", "stop-2"])

    def test_a_filled_key_never_collides_with_one_already_typed(self):
        doc = _route_template(stops=[
            {"stop_name": "_T-Gate"},
            {"stop_name": "_T-Yard", "stop_key": "stop-1"},
        ]).insert(ignore_permissions=True)
        self.assertEqual([stop.stop_key for stop in doc.stops], ["stop-2", "stop-1"])

    def test_a_typed_key_is_stored_trimmed(self):
        doc = _route_template(stops=[{"stop_name": "_T-Gate", "stop_key": "  gate  "}]).insert(
            ignore_permissions=True
        )
        self.assertEqual(doc.stops[0].stop_key, "gate")
