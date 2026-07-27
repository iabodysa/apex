# Copyright (c) 2026, AFMCO and contributors
"""Room Bed Transfer submit/cancel side-effects: the bed swap AND the occupancy
counters that have to move with it.

``on_submit`` frees ``from_bed``, occupies ``to_bed``, and re-points the live
Housing Assignment's bed/room/building; ``on_cancel`` reverses all of it. A
regression that leaves ``from_bed`` Occupied or fails to flip ``to_bed`` would
double-book or strand beds in the occupancy grid.

The move is BETWEEN TWO ROOMS OF ONE BUILDING. It used to be written across two
buildings, which encoded as correct the very behaviour the controller now
rejects: a cross-building move re-points the assignment with ``db_set`` and so
never re-derives the cost centre, Company or allowance state that the new
building implies. Two rooms in one building still exercise every spatial field
the swap touches, and they are what makes the ROOM counters observable — a
same-room move would hide the drift this module now guards.

Counters are asserted as DELTAS around the move, and against the live
active-assignment count. Housing Assignment and Housing Checkout have always
called ``recalculate_spatial`` on every move; the transfer alone did not, so both
rooms' ``current_occupancy`` silently drifted until the weekly sync job ran.

Fixtures are built fresh per test so the suite passes on a migrated site with NO
production data; assertions on the seeded state keep it non-vacuous.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

# [#ooevhv]
test_ignore = [
    "Additional Salary",
    "Asset",
    "Asset Movement",
    "Company",
    "Cost Center",
    "Currency",
    "Employee",
    "Item",
    "Payment Entry",
    "Project",
    "Purchase Invoice",
    "Role",
    "Salary Component",
    "Supplier",
    "User",
]


class TestRoomBedTransferBedSwap(FrappeTestCase):
    def setUp(self):
        # [#h0djea]
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")

    def _h(self):
        return frappe.generate_hash(length=12).upper()

    def _fixtures(self):
        """One building, two rooms, one bed each, so the Housing Assignment
        controller's full validate() runs (not link-ignored stubs) and the move
        changes bed AND room while staying inside the building the controller
        allows. Returns both sides plus the employee."""
        company = frappe.db.get_value("Company", {}) or frappe.get_doc(
            {
                "doctype": "Company",
                "company_name": "Test Co " + self._h(),
                "default_currency": "SAR",
                "country": "Saudi Arabia",
            }
        ).insert(ignore_permissions=True).name
        # [#3mukgp]
        cc = frappe.db.get_value("Cost Center", {"is_group": 0, "company": company}) or frappe.db.get_value(
            "Cost Center", {"is_group": 0}
        )
        site = frappe.get_doc(
            {"doctype": "Site", "site_name": self._h() + self._h()}
        ).insert(ignore_permissions=True).name

        building = frappe.get_doc(
            {
                "doctype": "Building",
                "building_name": "B " + self._h(),
                "site": site,
                "total_capacity": 4,
                "company": company,
                "default_cost_center": cc,
            }
        ).insert(ignore_permissions=True).name

        def _room():
            return frappe.get_doc(
                {
                    "doctype": "Room",
                    "naming_series": "ROOM-.####",
                    "building": building,
                    "room_number": "R" + self._h(),
                    "bed_capacity": 4,
                    "readiness_status": "Ready",  # [#id4o4x]
                }
            ).insert(ignore_permissions=True).name

        def _bed(room):
            return frappe.get_doc(
                {
                    "doctype": "Bed",
                    "naming_series": "BED-.####",
                    "room": room,
                    "building": building,
                    "bed_code": "B" + self._h(),
                    "status": "Available",
                }
            ).insert(ignore_permissions=True).name

        from_room = _room()
        from_bed = _bed(from_room)
        to_room = _room()
        to_bed = _bed(to_room)

        project = frappe.get_doc(
            {"doctype": "Project", "project_name": "P " + self._h()}
        ).insert(ignore_permissions=True).name
        emp = frappe.get_doc(
            {
                "doctype": "Employee",
                "first_name": "E " + self._h(),
                "company": company,
                "gender": "Male",
                "date_of_birth": "1990-01-01",
                "date_of_joining": "2020-01-01",
            }
        ).insert(ignore_permissions=True).name

        return frappe._dict(
            company=company,
            cc=cc,
            building=building,
            from_room=from_room,
            from_bed=from_bed,
            to_room=to_room,
            to_bed=to_bed,
            project=project,
            emp=emp,
        )

    def _active_assignment(self, fx):
        """A submitted, not-checked-out assignment occupying ``from_bed`` — the
        'active (checked-in)' state on_submit requires."""
        asg = frappe.get_doc(
            {
                "doctype": "Housing Assignment",
                "naming_series": "ACC-ASGN-.YYYY.-.####",
                "employee": fx.emp,
                "project": fx.project,
                "building": fx.building,
                "room": fx.from_room,
                "bed": fx.from_bed,
                "cost_center": fx.cc,
                "check_in_date": "2026-06-01",
                "assignment_type": "New Assignment",
            }
        )
        asg.submit()
        return asg

    def _transfer(self, fx):
        return frappe.get_doc(
            {
                "doctype": "Room Bed Transfer",
                "naming_series": "RBT-.YYYY.-.####",
                "assignment": self._asg_name,
                "to_room": fx.to_room,
                "to_bed": fx.to_bed,
                "transfer_date": "2026-06-02",
            }
        )

    def _counters(self, fx):
        """``(from_room stored, to_room stored, building stored, building live)``.

        The live count is carried alongside the stored one so a counter that is
        consistently wrong cannot pass as a counter that is right."""
        return (
            int(frappe.db.get_value("Room", fx.from_room, "current_occupancy") or 0),
            int(frappe.db.get_value("Room", fx.to_room, "current_occupancy") or 0),
            int(frappe.db.get_value("Building", fx.building, "current_occupants") or 0),
            frappe.db.count(
                "Housing Assignment",
                {"building": fx.building, "docstatus": 1, "check_out_date": ["is", "not set"]},
            ),
        )

    def test_submit_swaps_beds_and_repoints_assignment(self):
        fx = self._fixtures()
        asg = self._active_assignment(fx)
        self._asg_name = asg.name

        # [#s6cf35]
        self.assertEqual(
            frappe.db.get_value("Bed", fx.from_bed, "status"),
            "Occupied",
            "seed precondition: from_bed must be Occupied by the active assignment",
        )
        self.assertEqual(
            frappe.db.get_value("Bed", fx.to_bed, "status"),
            "Available",
            "seed precondition: to_bed must start Available",
        )
        self.assertEqual(
            self._counters(fx),
            (1, 0, 1, 1),
            "seed precondition: the resident is counted in the source room only",
        )

        # [#flajtg]
        transfer = self._transfer(fx)
        transfer.insert(ignore_permissions=True)
        self.assertEqual(
            transfer.from_bed, fx.from_bed, "from_bed must fetch from assignment.bed"
        )

        transfer.submit()

        # [#4ph7om]
        self.assertEqual(
            frappe.db.get_value("Bed", fx.from_bed, "status"),
            "Available",
            "on_submit must free the source bed",
        )
        self.assertEqual(
            frappe.db.get_value("Bed", fx.to_bed, "status"),
            "Occupied",
            "on_submit must occupy the target bed",
        )

        # [#3ftvei]
        row = frappe.db.get_value(
            "Housing Assignment",
            asg.name,
            ["bed", "room", "building", "check_out_date", "docstatus"],
            as_dict=True,
        )
        self.assertEqual(row.bed, fx.to_bed, "assignment must now reference the target bed")
        self.assertEqual(row.room, fx.to_room, "assignment must now reference the target room")
        self.assertEqual(
            row.building, fx.building, "an in-building move must not change the building"
        )
        # [#9xf9v0]
        self.assertEqual(row.docstatus, 1, "the transfer must not cancel the assignment")
        self.assertFalse(
            row.check_out_date, "the transfer must keep the assignment checked in"
        )

        self.assertEqual(
            self._counters(fx),
            (0, 1, 1, 1),
            "the occupancy must move room to room and the building total must not drift",
        )

    def test_cancel_reverses_the_swap(self):
        fx = self._fixtures()
        asg = self._active_assignment(fx)
        self._asg_name = asg.name
        before = self._counters(fx)

        transfer = self._transfer(fx)
        transfer.insert(ignore_permissions=True)
        transfer.submit()

        # [#ee6xdh]
        self.assertEqual(
            frappe.db.get_value("Bed", fx.from_bed, "status"),
            "Available",
            "precondition: submit freed from_bed",
        )
        self.assertEqual(
            frappe.db.get_value("Bed", fx.to_bed, "status"),
            "Occupied",
            "precondition: submit occupied to_bed",
        )
        self.assertNotEqual(
            self._counters(fx), before, "precondition: submit actually moved the counters"
        )

        transfer.cancel()

        # [#bfzbhi]
        self.assertEqual(
            frappe.db.get_value("Bed", fx.to_bed, "status"),
            "Available",
            "on_cancel must free the target bed again",
        )
        self.assertEqual(
            frappe.db.get_value("Bed", fx.from_bed, "status"),
            "Occupied",
            "on_cancel must re-occupy the source bed",
        )
        row = frappe.db.get_value(
            "Housing Assignment", asg.name, ["bed", "room", "building"], as_dict=True
        )
        self.assertEqual(row.bed, fx.from_bed, "cancel must put the resident back")
        self.assertEqual(row.room, fx.from_room)
        self.assertEqual(row.building, fx.building)
        self.assertEqual(
            self._counters(fx), before, "cancel must return the counters to their pre-move values"
        )
