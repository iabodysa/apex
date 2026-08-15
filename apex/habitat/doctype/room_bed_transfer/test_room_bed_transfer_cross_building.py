# Copyright (c) 2026, AFMCO and contributors
"""The one cross-building rule for a Room Bed Transfer, and the half-applied
states a move must never be able to leave behind.

Before this module the rule existed in ONE caller only — the Transfer Board API
raised it, the controller did not — so a Desk form save, a ``frappe.client`` REST
insert, a Data Import or a Server Script moved a resident between buildings
freely. That path re-points the live assignment with ``db_set``, which never runs
``Housing Assignment.validate()``, so the moved resident kept the OLD building's
cost centre and allowance state under the NEW building's Company. The tests here
drive the DOCUMENT directly, not the page, because the document is the path that
was open.

Occupancy is asserted as a DELTA against the counters read before the move, and
against the live active-assignment count, on BOTH buildings. "A row exists" is
equally true of a double post, and a counter that is merely non-zero is equally
true of a counter that never moved.

WHY THIS FILE IS 2.3x ITS SUBJECT (386 lines against the 168-line
``room_bed_transfer.py``). The previous note here read "288 test lines against 37 in the
subject (7.8x)"; both numbers were stale and the ratio was wrong by more than 3x, so it is
restated from a measurement rather than carried forward.

The ratio is earned by the SHAPE of the subject, not by repetition. A transfer is a
submit/cancel pair that mutates four records at once — two Beds, the live Housing
Assignment, and the occupancy counters on two Buildings — through a path (``db_set``) that
deliberately bypasses ``Housing Assignment.validate()``. Proving it therefore costs a full
two-building fixture chain (about a third of the file) and, for every one of the six
methods, assertions on BOTH sides of the move plus the counters, because a half-applied
state is the failure being guarded and only a both-sides assertion can see one. The six
methods are six distinct contracts — the document-level refusal, the API-level refusal, the
stale-resident submit guard, the moved-on cancel guard, the supervisor scope bound, and the
query fragment's hop through the assignment — not six shapes of one.
"""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat import permissions as P
from apex.habitat.api.transfer_board import transfer_occupant

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
        """RED->GREEN. The document path — no Transfer Board involved — used to
        accept a move into another building and re-point the assignment there."""
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
        """NON-REGRESSION, not RED->GREEN: the board rejected this before too — the
        rule simply used to live in the page. What is guarded here is that moving
        the rule into the controller did not change what the operator sees, and
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
        docstatus is submitted). A draft raised from bed 1 and submitted after the
        resident moved to bed 3 used to free bed 1 (already free) and occupy bed 2,
        leaving bed 3 Occupied by nobody — one resident, two occupied beds."""
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
