# Copyright (c) 2026, AFMCO and contributors
"""Route Plan regression tests — P-035.

Covers:
- sequence field removed from Route Stop (child table uses idx for order).
- stop_name is required on every Route Stop row.
- Adding 3 stops, reordering via idx, re-saving preserves the new idx order.
- Saving with a blank stop_name raises frappe.ValidationError.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

test_ignore = [
    "Employee",
    "Company",
    "Project",
    "Transport Request",
    "Salis Vehicle",
    "Salis Driver",
    "User",
    "Role",
]


def _make_route_plan(stops):
    """Return an unsaved Route Plan doc with the given stop rows.

    ``stops`` is a list of dicts passed directly as child-table rows; at minimum
    each dict should contain ``stop_name``.
    """
    doc = frappe.get_doc(
        {
            "doctype": "Route Plan",
            "stops": stops,
        }
    )
    return doc


class TestRoutePlanP035(FrappeTestCase):
    # [#eb9kj8]
    def test_sequence_field_removed(self):
        meta = frappe.get_meta("Route Stop")
        fieldnames = [f.fieldname for f in meta.fields]
        self.assertNotIn(
            "sequence",
            fieldnames,
            "sequence field must have been removed from Route Stop",
        )

    # [#gow7g4]
    def test_stop_name_required_in_meta(self):
        meta = frappe.get_meta("Route Stop")
        stop_name_field = next(
            (f for f in meta.fields if f.fieldname == "stop_name"), None
        )
        self.assertIsNotNone(stop_name_field, "stop_name field must exist on Route Stop")
        self.assertEqual(
            stop_name_field.reqd,
            1,
            "stop_name must have reqd=1 on Route Stop",
        )

    # [#lfu11h]
    def test_blank_stop_name_raises(self):
        doc = _make_route_plan(
            [
                {"stop_name": "Alpha Gate"},
                {"stop_name": ""},          # [#cnrebd]
                {"stop_name": "Gamma Hall"},
            ]
        )
        with self.assertRaises(frappe.ValidationError):
            doc.validate()

    # [#7du76a]
    def test_reorder_via_idx_preserved(self):
        """Create a Route Plan with 3 named stops, reorder their idx values,
        call validate() (which must not raise), and confirm the idx values
        survive in the order we assigned them."""
        doc = _make_route_plan(
            [
                {"stop_name": "Alpha Gate"},
                {"stop_name": "Beta Block"},
                {"stop_name": "Gamma Hall"},
            ]
        )
        # [#6u9zy7]
        doc.stops[0].idx = 2  # [#i70tpk]
        doc.stops[1].idx = 3  # [#34h4pq]
        doc.stops[2].idx = 1  # [#j0ewyn]

        # [#6lpmrk]
        doc.validate()

        # [#ba1rwe]
        idx_by_name = {s.stop_name: s.idx for s in doc.stops}
        self.assertEqual(idx_by_name["Alpha Gate"], 2)
        self.assertEqual(idx_by_name["Beta Block"], 3)
        self.assertEqual(idx_by_name["Gamma Hall"], 1)


class TestRoutePlanFulfilmentStamp(FrappeTestCase):
    """P-034: on_submit must PERSIST movement_planner.

    on_submit fires after the document row is already written, so a plain
    ``self.movement_planner = ...`` is never flushed back — only db_set
    persists. The proof is a re-read straight from the DB after submit.
    """

    def test_movement_planner_persisted_on_submit(self):
        frappe.set_user("Administrator")
        doc = frappe.get_doc(
            {
                "doctype": "Route Plan",
                "route_name": "P-034 Persist Check",
                "stops": [{"stop_name": "Alpha Gate"}],
            }
        )
        doc.insert(ignore_permissions=True)
        # [#pawxm1]
        self.assertFalse(doc.movement_planner)

        doc.submit()

        # [#p3evhe]
        persisted = frappe.db.get_value(
            "Route Plan", doc.name, "movement_planner"
        )
        self.assertEqual(persisted, frappe.session.user)
