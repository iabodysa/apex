"""Room Bed Transfer submit/cancel side-effects: the bed occupancy swap.

The shipped ``test_room_bed_transfer`` only ``insert(... ignore_links=True)``s and
checks mandatory fields; it never submits or cancels, so the controller's actual
job is unguarded. ``on_submit`` (room_bed_transfer.py) frees ``from_bed``, occupies
``to_bed``, and re-points the live Accommodation Assignment's bed/room/building to
the target; ``on_cancel`` reverses the two bed statuses. A regression that leaves
``from_bed`` Occupied or fails to flip ``to_bed`` (or skips the cancel reversal)
would double-book or strand beds in the occupancy grid with no failing test. This
guards both the submit swap (incl. assignment re-pointing) and the cancel reversal.

Fixtures are built fresh per test (keyed off ``self._testMethodName``) so the suite
passes on a migrated site with NO production data; assertions on the seeded state
keep it non-vacuous.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

# [#8evoal] Real linked masters are created in-test; tell the framework not to
# auto-provision stubs for these (mirrors the sibling controller tests).
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
        # Author all fixtures + transitions as Administrator; restore in tearDown.
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")

    def _h(self):
        return frappe.generate_hash(length=4).upper()

    def _fixtures(self):
        """A fully consistent two-building / two-room / two-bed world so the
        Accommodation Assignment controller's full validate() runs (not link-ignored
        stubs) and a cross-building transfer genuinely changes room AND building.

        Returns the from-side (building/room/bed) and to-side (building/room/bed)
        plus the employee, so the swap re-point is observable across all three
        spatial fields.
        """
        company = frappe.db.get_value("Company", {}) or frappe.get_doc(
            {
                "doctype": "Company",
                "company_name": "Test Co " + self._h(),
                "default_currency": "SAR",
                "country": "Saudi Arabia",
            }
        ).insert(ignore_permissions=True).name
        # A non-group cost center for billing (Building.default_cost_center).
        cc = frappe.db.get_value("Cost Center", {"is_group": 0, "company": company}) or frappe.db.get_value(
            "Cost Center", {"is_group": 0}
        )
        site = frappe.get_doc(
            {"doctype": "Accommodation Site", "site_name": self._h() + self._h()}
        ).insert(ignore_permissions=True).name

        def _building():
            return frappe.get_doc(
                {
                    "doctype": "Accommodation Building",
                    "building_name": "B " + self._h(),
                    "site": site,
                    "total_capacity": 4,
                    "company": company,
                    "default_cost_center": cc,
                }
            ).insert(ignore_permissions=True).name

        def _room(building):
            return frappe.get_doc(
                {
                    "doctype": "Accommodation Room",
                    "naming_series": "ROOM-.####",
                    "building": building,
                    "room_number": "R" + self._h(),
                    "bed_capacity": 4,
                    "readiness_status": "Ready",  # [#agde2c] avoids the not-assignable throw
                }
            ).insert(ignore_permissions=True).name

        def _bed(building, room):
            return frappe.get_doc(
                {
                    "doctype": "Accommodation Bed",
                    "naming_series": "BED-.####",
                    "room": room,
                    "building": building,
                    "bed_code": "B" + self._h(),
                    "status": "Available",
                }
            ).insert(ignore_permissions=True).name

        from_building = _building()
        from_room = _room(from_building)
        from_bed = _bed(from_building, from_room)

        to_building = _building()
        to_room = _room(to_building)
        to_bed = _bed(to_building, to_room)

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
            from_building=from_building,
            from_room=from_room,
            from_bed=from_bed,
            to_building=to_building,
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
                "doctype": "Accommodation Assignment",
                "naming_series": "ACC-ASGN-.YYYY.-.####",
                "employee": fx.emp,
                "project": fx.project,
                "building": fx.from_building,
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

    def test_submit_swaps_beds_and_repoints_assignment(self):
        fx = self._fixtures()
        asg = self._active_assignment(fx)
        self._asg_name = asg.name

        # Non-vacuous: the seed produced exactly the occupancy we rely on — the
        # assignment's on_submit already occupied from_bed and to_bed is free.
        self.assertEqual(
            frappe.db.get_value("Accommodation Bed", fx.from_bed, "status"),
            "Occupied",
            "seed precondition: from_bed must be Occupied by the active assignment",
        )
        self.assertEqual(
            frappe.db.get_value("Accommodation Bed", fx.to_bed, "status"),
            "Available",
            "seed precondition: to_bed must start Available",
        )
        # from_bed is fetched from assignment.bed; confirm it resolved before submit.
        transfer = self._transfer(fx)
        transfer.insert(ignore_permissions=True)
        self.assertEqual(
            transfer.from_bed, fx.from_bed, "from_bed must fetch from assignment.bed"
        )

        transfer.submit()

        # The occupancy swap: source freed, target taken.
        self.assertEqual(
            frappe.db.get_value("Accommodation Bed", fx.from_bed, "status"),
            "Available",
            "on_submit must free the source bed",
        )
        self.assertEqual(
            frappe.db.get_value("Accommodation Bed", fx.to_bed, "status"),
            "Occupied",
            "on_submit must occupy the target bed",
        )

        # The live assignment is re-pointed in place to the target bed/room/building.
        row = frappe.db.get_value(
            "Accommodation Assignment",
            asg.name,
            ["bed", "room", "building", "check_out_date", "docstatus"],
            as_dict=True,
        )
        self.assertEqual(row.bed, fx.to_bed, "assignment must now reference the target bed")
        self.assertEqual(row.room, fx.to_room, "assignment must now reference the target room")
        self.assertEqual(
            row.building, fx.to_building, "assignment must now reference the target building"
        )
        # The stay was never closed/re-opened: still an active (submitted) check-in.
        self.assertEqual(row.docstatus, 1, "the transfer must not cancel the assignment")
        self.assertFalse(
            row.check_out_date, "the transfer must keep the assignment checked in"
        )

    def test_cancel_reverses_the_swap(self):
        fx = self._fixtures()
        asg = self._active_assignment(fx)
        self._asg_name = asg.name

        transfer = self._transfer(fx)
        transfer.insert(ignore_permissions=True)
        transfer.submit()

        # Post-submit precondition (non-vacuous): swap is in effect before we cancel.
        self.assertEqual(
            frappe.db.get_value("Accommodation Bed", fx.from_bed, "status"),
            "Available",
            "precondition: submit freed from_bed",
        )
        self.assertEqual(
            frappe.db.get_value("Accommodation Bed", fx.to_bed, "status"),
            "Occupied",
            "precondition: submit occupied to_bed",
        )

        transfer.cancel()

        # on_cancel reverses ONLY the two bed statuses.
        self.assertEqual(
            frappe.db.get_value("Accommodation Bed", fx.to_bed, "status"),
            "Available",
            "on_cancel must free the target bed again",
        )
        self.assertEqual(
            frappe.db.get_value("Accommodation Bed", fx.from_bed, "status"),
            "Occupied",
            "on_cancel must re-occupy the source bed",
        )
