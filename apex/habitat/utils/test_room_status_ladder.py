# Copyright (c) 2026, AFMCO and contributors
"""one function computes Room status, and it answers the zero-capacity case.

Two writers held their own ladder and disagreed on exactly one input. The live handler in
`housing_assignment.py` used `active >= (capacity or 0)`, so a room with no declared
capacity read as Full the moment anyone moved in; the weekly job in `tasks/occupancy.py`
used `capacity and active >= capacity`, so the same room read as Partially Occupied. The
displayed status therefore flipped every time the Sunday sync ran.

`occupancy.room_status` is now the only ladder. The product call it carries — an
undeclared capacity is never Full — is pinned by the first test here, because it is the
one answer that was never decided and would otherwise be inherited again from whichever
expression survived the next edit.

Plain values in, a value out, so none of this needs a database.
"""

from frappe.tests.utils import FrappeTestCase

from apex.habitat.utils.occupancy import room_status


class TestTheRoomStatusLadder(FrappeTestCase):
    def test_a_room_with_no_declared_capacity_is_never_full(self):
        """The product decision. Zero or null capacity means the ceiling is unknown, not
        that the room holds nobody — so an occupant must not read as no room left."""
        for capacity in (0, None):
            with self.subTest(capacity=capacity):
                self.assertEqual(room_status(1, capacity), "Partially Occupied")
                self.assertEqual(room_status(9, capacity), "Partially Occupied")

    def test_an_empty_room_is_available_whatever_its_capacity(self):
        for capacity in (0, None, 1, 4):
            with self.subTest(capacity=capacity):
                self.assertEqual(room_status(0, capacity), "Available")

    def test_a_room_at_or_over_its_declared_capacity_is_full(self):
        self.assertEqual(room_status(4, 4), "Full")
        self.assertEqual(room_status(5, 4), "Full")

    def test_a_room_under_its_declared_capacity_is_partially_occupied(self):
        self.assertEqual(room_status(1, 4), "Partially Occupied")
        self.assertEqual(room_status(3, 4), "Partially Occupied")

    def test_the_two_former_writers_now_agree_on_every_input(self):
        """The defect itself: the old pair returned different answers, and this is the
        input set where they parted. Both call sites now route here, so one answer is
        all there is — but the old expressions are kept side by side so the divergence
        is visible rather than described."""
        for active, capacity in ((1, 0), (1, None), (3, 0), (0, 0), (2, 4), (4, 4)):
            live_handler = (
                "Available" if active <= 0
                else "Full" if active >= (capacity or 0)
                else "Partially Occupied"
            )
            weekly_job = (
                "Available" if active <= 0
                else "Full" if (capacity and active >= capacity)
                else "Partially Occupied"
            )
            with self.subTest(active=active, capacity=capacity):
                self.assertEqual(
                    room_status(active, capacity),
                    weekly_job,
                    "the shared ladder must keep the weekly job's answer",
                )
                if live_handler != weekly_job:
                    self.assertNotEqual(
                        room_status(active, capacity),
                        live_handler,
                        "this is an input the two writers disagreed on",
                    )
