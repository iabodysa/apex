# Copyright (c) 2026, afmcoltd
"""Room Bed Transfer's own contract: it needs an assignment and a date, it refuses a target room
that carries no building, and cancelling it puts the resident back where he started.

The building, its rooms, its beds and the employee all come from ``test_records.json`` rather than
a Company, a Site, a Building, a Room, a Bed, an Employee, a Project and an Assignment rebuilt for
every one of its five methods. The one record still built per case is the roomless room the
integrity guard exists to reject — that is the subject, not scaffolding.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from unittest import TestCase
from unittest.mock import MagicMock, patch
from apex.habitat.doctype.room_bed_transfer import room_bed_transfer
from unittest.mock import patch
from apex.habitat import permissions as P
from apex.habitat.api.transfer_board import transfer_occupant

# Project is deliberately NOT a dependency. ERPNext's Project fixture is not idempotent — its
# autoname mints a new name while project_name carries a unique index, so a second build attempt
# collides instead of being skipped.

BUILDING = "_Test Building"
ROOM = "_T-101"
ORIGIN_BED = "_T-101-A"
TARGET_BED = "_T-101-B"


class TestRoomBedTransfer(FrappeTestCase):
    def setUp(self):
        # FrappeTestCase rolls the database back once per CLASS, not once per method —
        # frappe/tests/utils.py:46 registers _rollback_db with addClassCleanup — so the bed one
        # case houses a resident in would still be occupied when the next case tries. A savepoint
        # is the framework's own way to hand the fixture beds back.
        frappe.db.savepoint("apex_room_bed_transfer_case")
        self.addCleanup(frappe.db.rollback, save_point="apex_room_bed_transfer_case")

        self.assignment = frappe.get_doc({
            "doctype": "Housing Assignment",
            "naming_series": "ACC-ASGN-.YYYY.-.####",
            "employee": frappe.db.get_value("Employee", {"first_name": "_Test Employee"}),
            "project": frappe.db.get_value("Project", {"project_name": "_Test Project"}),
            "building": BUILDING,
            "room": ROOM,
            "bed": ORIGIN_BED,
            "cost_center": frappe.db.get_value("Building", BUILDING, "default_cost_center"),
            "check_in_date": "2026-06-01",
            "assignment_type": "New Assignment",
        })
        self.assignment.insert(ignore_permissions=True)

    def _transfer(self, **overrides):
        payload = {
            "doctype": "Room Bed Transfer",
            "naming_series": "RBT-.YYYY.-.####",
            "assignment": self.assignment.name,
            "to_room": ROOM,
            "to_bed": TARGET_BED,
            "transfer_date": "2026-06-02",
        }
        payload.update(overrides)
        return frappe.get_doc(payload)

    def test_a_transfer_takes_the_assignment_and_target_it_is_given(self):
        transfer = self._transfer()
        transfer.insert(ignore_permissions=True)

        self.assertEqual(transfer.assignment, self.assignment.name)
        self.assertEqual(transfer.to_bed, TARGET_BED)

    def test_a_transfer_without_an_assignment_is_refused(self):
        transfer = self._transfer(assignment=None)

        with self.assertRaises(frappe.exceptions.MandatoryError):
            transfer.insert(ignore_permissions=True)

    def test_a_transfer_without_a_date_is_refused(self):
        transfer = self._transfer(transfer_date=None)

        with self.assertRaises(frappe.exceptions.MandatoryError):
            transfer.insert(ignore_permissions=True)

    def test_a_target_room_that_carries_no_building_is_refused(self):
        """The building-integrity guard: a transfer whose target room carries no building must be
        rejected in validate(). The room is minted with ignore_mandatory and the field cleared to
        be certain, and its bed is Available and belongs to the room, so every earlier gate passes
        and execution reaches the building guard."""
        tag = frappe.generate_hash(length=12).upper()
        roomless = frappe.get_doc({
            "doctype": "Room", "naming_series": "ROOM-.####",
            "room_number": "NB" + tag, "bed_capacity": 1, "readiness_status": "Ready",
        }).insert(ignore_permissions=True, ignore_mandatory=True).name
        frappe.db.set_value("Room", roomless, "building", None, update_modified=False)
        stray_bed = frappe.get_doc({
            "doctype": "Bed", "naming_series": "BED-.####", "room": roomless,
            "bed_code": "NB" + tag, "status": "Available",
        }).insert(ignore_permissions=True, ignore_mandatory=True).name

        with self.assertRaises(frappe.ValidationError):
            self._transfer(to_room=roomless, to_bed=stray_bed).insert(ignore_permissions=True)

    def test_cancelling_a_transfer_puts_the_resident_back_on_the_origin_bed(self):
        self.assignment.submit()
        transfer = self._transfer()
        transfer.insert(ignore_permissions=True)
        transfer.submit()

        self.assignment.reload()
        self.assertEqual(self.assignment.bed, TARGET_BED, "submit moves the assignment onto the target bed")
        self.assertEqual(frappe.db.get_value("Bed", TARGET_BED, "status"), "Occupied")
        self.assertEqual(frappe.db.get_value("Bed", ORIGIN_BED, "status"), "Available")

        transfer.cancel()

        self.assignment.reload()
        self.assertEqual(self.assignment.bed, ORIGIN_BED, "cancel restores the origin bed")
        self.assertEqual(self.assignment.room, ROOM, "cancel restores the origin room")
        self.assertEqual(self.assignment.building, BUILDING, "cancel restores the origin building")
        self.assertEqual(frappe.db.get_value("Bed", ORIGIN_BED, "status"), "Occupied")
        self.assertEqual(frappe.db.get_value("Bed", TARGET_BED, "status"), "Available")

test_dependencies = ['Bed', 'Employee']
test_ignore = ['Additional Salary', 'Asset', 'Asset Movement', 'Company', 'Cost Center', 'Currency', 'Employee', 'Item', 'Payment Entry', 'Project', 'Purchase Invoice', 'Role', 'Salary Component', 'Supplier', 'User']


# --- merged from test_room_bed_transfer_bed_swap.py ---
class TestRoomBedTransferBedSwap(FrappeTestCase):
    def setUp(self):
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
                    "readiness_status": "Ready",
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

        transfer = self._transfer(fx)
        transfer.insert(ignore_permissions=True)
        self.assertEqual(
            transfer.from_bed, fx.from_bed, "from_bed must fetch from assignment.bed"
        )

        transfer.submit()

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


# --- merged from test_room_bed_transfer_cancel_origin.py ---
def _raising_frappe() -> MagicMock:
    fake = MagicMock()

    def throw(message, exc=None, **_kwargs):
        raise (exc or frappe.ValidationError)(message)

    fake.throw.side_effect = throw
    return fake
def _transfer():
    doc = MagicMock(assignment="HA-1", from_bed="BED-FROM", to_bed="BED-TO")
    return doc
def _live_assignment():
    return frappe._dict(docstatus=1, check_out_date=None, bed="BED-TO")
class TestRoomBedTransferCancelChecksOrigin(TestCase):
    def _run(self, origin_status):
        fake = _raising_frappe()
        fake.db.get_value.side_effect = [_live_assignment(), origin_status]
        with (
            patch.object(room_bed_transfer, "frappe", fake),
            patch.object(room_bed_transfer, "_", side_effect=lambda message: message),
        ):
            room_bed_transfer.before_cancel(_transfer())
        return fake

    def test_cancel_is_allowed_while_the_origin_bed_is_still_free(self):
        fake = self._run("Available")
        self.assertEqual(
            fake.db.get_value.call_args.args[:3],
            ("Bed", "BED-FROM", "status"),
            "the origin bed status must be the second read",
        )
        self.assertTrue(
            fake.db.get_value.call_args.kwargs.get("for_update"),
            "the origin read must lock, or the check and the reversal see different rows",
        )

    def test_cancel_is_refused_once_the_origin_bed_is_taken(self):
        for origin_status in ("Occupied", "Out of Service"):
            with self.subTest(origin_status=origin_status):
                with self.assertRaises(frappe.ValidationError):
                    self._run(origin_status)


# --- merged from test_room_bed_transfer_cross_building.py ---
class TestRoomBedTransferCrossBuilding(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")

    def _h(self):
        return frappe.generate_hash(length=12).upper()

    def _building(self, site, company, cc):
        return frappe.get_doc(
            {
                "doctype": "Building",
                "building_name": "B " + self._h(),
                "site": site,
                "total_capacity": 4,
                "company": company,
                "default_cost_center": cc,
            }
        ).insert(ignore_permissions=True).name

    def _room(self, building):
        return frappe.get_doc(
            {
                "doctype": "Room",
                "naming_series": "ROOM-.####",
                "building": building,
                "room_number": "R" + self._h(),
                "bed_capacity": 4,
                "readiness_status": "Ready",
            }
        ).insert(ignore_permissions=True).name

    def _bed(self, building, room):
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

    def _world(self):
        """Two complete buildings on one site, each with a room and one bed, plus
        an employee and project. Minted per METHOD: FrappeTestCase rolls rows back
        once per CLASS, so siblings sharing a bed would see each other's flips."""
        company = frappe.db.get_value("Company", {}) or frappe.get_doc(
            {
                "doctype": "Company",
                "company_name": "Test Co " + self._h(),
                "default_currency": "SAR",
                "country": "Saudi Arabia",
            }
        ).insert(ignore_permissions=True).name
        cc = frappe.db.get_value(
            "Cost Center", {"is_group": 0, "company": company}
        ) or frappe.db.get_value("Cost Center", {"is_group": 0})
        site = frappe.get_doc(
            {"doctype": "Site", "site_name": self._h() + self._h()}
        ).insert(ignore_permissions=True).name

        a_building = self._building(site, company, cc)
        a_room = self._room(a_building)
        a_bed = self._bed(a_building, a_room)

        b_building = self._building(site, company, cc)
        b_room = self._room(b_building)
        b_bed = self._bed(b_building, b_room)

        return frappe._dict(
            company=company,
            cc=cc,
            a_building=a_building,
            a_room=a_room,
            a_bed=a_bed,
            b_building=b_building,
            b_room=b_room,
            b_bed=b_bed,
            project=frappe.get_doc(
                {"doctype": "Project", "project_name": "P " + self._h()}
            ).insert(ignore_permissions=True).name,
            emp=frappe.get_doc(
                {
                    "doctype": "Employee",
                    "first_name": "E " + self._h(),
                    "company": company,
                    "gender": "Male",
                    "date_of_birth": "1990-01-01",
                    "date_of_joining": "2020-01-01",
                }
            ).insert(ignore_permissions=True).name,
        )

    def _active_assignment(self, fx):
        """A submitted, not-checked-out assignment occupying ``a_bed``."""
        asg = frappe.get_doc(
            {
                "doctype": "Housing Assignment",
                "naming_series": "ACC-ASGN-.YYYY.-.####",
                "employee": fx.emp,
                "project": fx.project,
                "building": fx.a_building,
                "room": fx.a_room,
                "bed": fx.a_bed,
                "cost_center": fx.cc,
                "check_in_date": "2026-06-01",
                "assignment_type": "New Assignment",
            }
        )
        asg.submit()
        return asg

    def _building_occupancy(self, building):
        """``(stored current_occupants, live active-assignment count)``.

        Both halves matter: the stored counter is what every dashboard, report and
        capacity guard reads, and the live count is the truth it is supposed to
        equal. Asserting only the stored number would pass on a counter that is
        consistently wrong."""
        stored = frappe.db.get_value("Building", building, "current_occupants") or 0
        live = frappe.db.count(
            "Housing Assignment",
            {"building": building, "docstatus": 1, "check_out_date": ["is", "not set"]},
        )
        return int(stored), int(live)

    def _occupied_beds(self, room):
        return frappe.db.count("Bed", {"room": room, "status": "Occupied"})

    def _draft_transfer(self, assignment, to_room, to_bed, transfer_date="2026-06-02"):
        return frappe.get_doc(
            {
                "doctype": "Room Bed Transfer",
                "naming_series": "RBT-.YYYY.-.####",
                "assignment": assignment,
                "to_room": to_room,
                "to_bed": to_bed,
                "transfer_date": transfer_date,
            }
        )

    def test_cross_building_transfer_is_rejected_on_a_direct_document_call(self):
        """RED->GREEN. The document path — no Transfer Board involved — must reject a
        move into another building rather than accept it and re-point the assignment
        there."""
        fx = self._world()
        asg = self._active_assignment(fx)
        before_a = self._building_occupancy(fx.a_building)
        before_b = self._building_occupancy(fx.b_building)
        self.assertEqual(before_a, (1, 1), "seed precondition: the resident is counted in A")
        self.assertEqual(before_b, (0, 0), "seed precondition: B starts empty")

        doc = self._draft_transfer(asg.name, fx.b_room, fx.b_bed)
        with self.assertRaises(frappe.ValidationError) as caught:
            doc.insert(ignore_permissions=True)
        # Assert the MESSAGE, not just the type: a link check raises the very same
        # exception class before validate() ever runs.
        self.assertIn("Cross-building", str(caught.exception))

        self.assertEqual(
            frappe.db.get_value("Bed", fx.a_bed, "status"),
            "Occupied",
            "the source bed must not be freed by a rejected transfer",
        )
        self.assertEqual(
            frappe.db.get_value("Bed", fx.b_bed, "status"),
            "Available",
            "the target bed must not be occupied by a rejected transfer",
        )
        self.assertEqual(
            frappe.db.get_value("Housing Assignment", asg.name, "building"),
            fx.a_building,
            "the assignment must stay in its own building",
        )
        self.assertEqual(self._building_occupancy(fx.a_building), before_a)
        self.assertEqual(self._building_occupancy(fx.b_building), before_b)

    def test_cross_building_transfer_is_rejected_through_the_transfer_board(self):
        """NON-REGRESSION, not RED->GREEN: the board rejects this too, even though the
        rule lives in the controller now, not the page. What is guarded here is that
        the rule living in the controller does not change what the operator sees, and
        that no Room Bed Transfer row survives the refusal."""
        fx = self._world()
        asg = self._active_assignment(fx)

        with self.assertRaises(frappe.ValidationError) as caught:
            transfer_occupant(
                source_bed=fx.a_bed, target_bed=fx.b_bed, transfer_date="2026-06-02"
            )
        self.assertIn("Cross-building", str(caught.exception))
        self.assertEqual(
            frappe.db.count("Room Bed Transfer", {"assignment": asg.name}),
            0,
            "a refused board move must leave no transfer document behind",
        )
        self.assertEqual(frappe.db.get_value("Bed", fx.a_bed, "status"), "Occupied")
        self.assertEqual(frappe.db.get_value("Bed", fx.b_bed, "status"), "Available")

    def test_submit_refuses_a_transfer_whose_resident_has_since_moved(self):
        """RED->GREEN for the stale ``from_bed``.

        ``from_bed`` is a ``fetch_from`` snapshot frozen at the draft save and NOT
        refreshed on the submitting save (base_document.py:850 skips the fetch once
        docstatus is submitted). Submitting a draft raised from bed 1 after the
        resident has since moved to bed 3 must be refused: otherwise it would free bed
        1 (already free) and occupy bed 2, leaving bed 3 Occupied by nobody — one
        resident, two occupied beds."""
        fx = self._world()
        bed2 = self._bed(fx.a_building, fx.a_room)
        bed3 = self._bed(fx.a_building, fx.a_room)
        asg = self._active_assignment(fx)

        stale = self._draft_transfer(asg.name, fx.a_room, bed2)
        stale.insert(ignore_permissions=True)
        self.assertEqual(stale.from_bed, fx.a_bed, "the draft froze bed 1 as its source")

        moved = self._draft_transfer(asg.name, fx.a_room, bed3, transfer_date="2026-06-03")
        moved.insert(ignore_permissions=True)
        moved.submit()
        self.assertEqual(
            frappe.db.get_value("Housing Assignment", asg.name, "bed"),
            bed3,
            "precondition: the resident is now in bed 3",
        )

        with self.assertRaises(frappe.ValidationError) as caught:
            stale.submit()
        self.assertIn("raised from Bed", str(caught.exception))
        self.assertEqual(
            frappe.db.get_value("Room Bed Transfer", stale.name, "docstatus"),
            0,
            "the refusal fires in before_submit, so docstatus is never written "
            "(document.py writes it at :428, on_submit only runs at :431)",
        )

        self.assertEqual(
            self._occupied_beds(fx.a_room),
            1,
            "one resident may occupy exactly one bed — count, do not merely check existence",
        )
        self.assertEqual(frappe.db.get_value("Bed", bed3, "status"), "Occupied")
        self.assertEqual(frappe.db.get_value("Bed", bed2, "status"), "Available")
        self.assertEqual(frappe.db.get_value("Housing Assignment", asg.name, "bed"), bed3)

    def test_cancel_is_refused_once_the_resident_has_moved_on(self):
        """RED->GREEN. The old ``on_cancel`` flipped both bed statuses
        UNCONDITIONALLY while guarding only the assignment re-point, so cancelling
        a superseded transfer re-occupied its source bed for a resident who was no
        longer in it — a phantom occupancy no report can explain."""
        fx = self._world()
        bed2 = self._bed(fx.a_building, fx.a_room)
        bed3 = self._bed(fx.a_building, fx.a_room)
        asg = self._active_assignment(fx)

        first = self._draft_transfer(asg.name, fx.a_room, bed2)
        first.insert(ignore_permissions=True)
        first.submit()

        second = self._draft_transfer(asg.name, fx.a_room, bed3, transfer_date="2026-06-03")
        second.insert(ignore_permissions=True)
        second.submit()

        with self.assertRaises(frappe.ValidationError) as caught:
            first.cancel()
        self.assertIn("no longer be reversed", str(caught.exception))

        self.assertEqual(
            self._occupied_beds(fx.a_room),
            1,
            "a refused reversal must not leave a second bed occupied",
        )
        self.assertEqual(frappe.db.get_value("Bed", fx.a_bed, "status"), "Available")
        self.assertEqual(frappe.db.get_value("Bed", bed3, "status"), "Occupied")
        self.assertEqual(
            frappe.db.get_value("Room Bed Transfer", first.name, "docstatus"),
            1,
            "the refusal fires in before_cancel, so the transfer is left submitted "
            "rather than cancelled-in-the-row with its reversal never run",
        )

    def test_scoped_supervisor_is_bounded_by_the_assignment_building(self):
        """RED->GREEN. Room Bed Transfer carried NO scope hook at all: its only
        defence was the DocPerm list, which happens to name two oversight roles.
        The moment a building-scoped role is granted the DocType, the guard has to
        be structural. ``_doc_building`` had no anchor for this DocType, so it
        resolved None and denied the supervisor his OWN building too."""
        fx = self._world()
        asg = self._active_assignment(fx)
        doc = frappe._dict(doctype="Room Bed Transfer", assignment=asg.name)

        with patch.object(P, "_building_is_unscoped", return_value=False), patch.object(
            P, "_allowed_buildings", return_value=[fx.a_building]
        ):
            self.assertIsNone(
                P.building_scoped_has_permission(doc, "submit", user="sup"),
                "a supervisor scoped to the resident's own building is deferred to his DocPerms",
            )

        with patch.object(P, "_building_is_unscoped", return_value=False), patch.object(
            P, "_allowed_buildings", return_value=[fx.b_building]
        ):
            self.assertFalse(
                P.building_scoped_has_permission(doc, "submit", user="sup"),
                "a supervisor holding only the OTHER building may not move this resident out",
            )

        with patch.object(P, "_building_is_unscoped", return_value=True):
            self.assertIsNone(
                P.building_scoped_has_permission(doc, "submit", user="mgr"),
                "an oversight role stays unscoped — the hook denies only, never grants",
            )

    def test_scope_fragment_hops_through_the_assignment(self):
        """RED->GREEN: the fragment did not exist. Room Bed Transfer has no
        ``building`` column, so the estate has to be reached one hop away."""
        with patch.object(P, "_building_is_unscoped", return_value=False), patch.object(
            P, "_allowed_buildings", return_value=["BLDG-1"]
        ):
            cond = P.building_scope_query(doctype="Room Bed Transfer", user="sup")
            self.assertIn("`assignment`", cond)
            self.assertIn("tabHousing Assignment", cond)
            self.assertIn("BLDG-1", cond)

        with patch.object(P, "_building_is_unscoped", return_value=False), patch.object(
            P, "_allowed_buildings", return_value=[]
        ):
            self.assertEqual(
                P.building_scope_query(doctype="Room Bed Transfer", user="sup"),
                "1=0",
                "a scoped user with no building sees nothing, never everything",
            )

        with patch.object(P, "_building_is_unscoped", return_value=True):
            self.assertEqual(P.building_scope_query(doctype="Room Bed Transfer", user="mgr"), "")
