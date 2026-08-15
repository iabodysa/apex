# Copyright (c) 2026, AFMCO and contributors
"""A-404 — the five-minute boarding tick must load only the trips that have work.

`auto_confirm_claimed_boardings` asked Trip Boarding State for every row at status
`Worker Claimed`, then `frappe.get_doc`'d the whole Dispatch Trip behind each one — child
tables and all — to discover that most claims had not yet reached
`boarding_auto_confirm_minutes`. On a fleet where claims are normal and timeouts are rare,
almost every load was wasted, once every five minutes, forever.

The cutoff now travels in the query. `_apply_auto_confirm` keeps its own check: the query
narrows the candidate set, the function still decides — so a row that slips through a
coarser filter is still tested before it is flipped.

The card asks for a count rather than an assertion, so these tests wrap `frappe.get_doc`
and count Dispatch Trip loads across a tick.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime, today

from apex.apex_core.doctype.salis_settings.salis_settings import get_boarding_setting
from apex.salis.api import boarding_flow

EMPLOYEE = "_T-Employee-00001"
DUE_TRIPS = 2
NOT_DUE_TRIPS = 5


def _h(n=8):
    return frappe.generate_hash(length=n).upper()


class TestTheBoardingTickLoadsOnlyDueTrips(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.cutoff_minutes = get_boarding_setting("boarding_auto_confirm_minutes")

    def setUp(self):
        frappe.set_user("Administrator")
        self.mine = []

    def _trip(self, claimed_minutes_ago):
        """A draft trip carrying one Worker Claimed row of the given age.

        ``trip_date`` is set even though the insert passes ``ignore_mandatory``:
        the tick re-saves every trip it flips, and that save runs the ordinary
        mandatory check, so a trip missing a required field is loaded, flipped in
        memory, then rolled back by the tick's per-trip savepoint — the flip would
        never reach the database. The trip carries no Transport Request, so
        ``sync_passengers`` returns early and leaves this hand-built boarding row
        exactly as written."""
        doc = frappe.get_doc(
            {
                "doctype": "Dispatch Trip",
                "trip_date": today(),
                "boarding_state": [
                    {
                        "employee": EMPLOYEE,
                        "status": "Worker Claimed",
                        "worker_claim_at": add_to_date(
                            now_datetime(), minutes=-claimed_minutes_ago
                        ),
                    }
                ],
            }
        )
        doc.insert(ignore_permissions=True, ignore_mandatory=True)
        self.mine.append(doc.name)
        self.addCleanup(self._drop, doc.name)
        return doc.name

    def _drop(self, name):
        frappe.db.set_value(
            "Dispatch Trip", name, "docstatus", 0, update_modified=False
        )
        frappe.delete_doc("Dispatch Trip", name, force=True, ignore_permissions=True)

    def _count_trip_loads(self):
        """Wrap frappe.get_doc and count the Dispatch Trip loads THIS test caused.

        Returns the DISTINCT trips opened. A trip the tick actually changes is read a
        second time by `save()` for its before-save snapshot; that read is the cost of
        doing the work, not the waste this card is about, which is opening a trip only to
        find it has nothing due.

        Scoped to the fixture's own trip names so a bench carrying unrelated claimed
        trips cannot inflate the number — the count has to mean the same thing on an
        empty bench and a busy one."""
        loads = []
        original = frappe.get_doc

        def counting(*args, **kwargs):
            if args and args[0] == "Dispatch Trip" and len(args) > 1 and args[1] in self.mine:
                loads.append(args[1])
            return original(*args, **kwargs)

        frappe.get_doc = counting
        try:
            boarding_flow.auto_confirm_claimed_boardings()
        finally:
            frappe.get_doc = original
        return sorted(set(loads))

    def test_a_tick_loads_the_due_trips_and_not_the_rest(self):
        for _ in range(DUE_TRIPS):
            self._trip(self.cutoff_minutes + 5)
        for _ in range(NOT_DUE_TRIPS):
            self._trip(0)
        frappe.db.commit()

        loads = self._count_trip_loads()

        self.assertEqual(
            len(loads),
            DUE_TRIPS,
            f"the tick loaded {len(loads)} trips; only {DUE_TRIPS} of "
            f"{DUE_TRIPS + NOT_DUE_TRIPS} claimed trips are past the cutoff",
        )

    def test_a_tick_with_nothing_due_loads_no_documents_at_all(self):
        """The case the card names: a quiet tick must touch nothing."""
        for _ in range(NOT_DUE_TRIPS):
            self._trip(0)
        frappe.db.commit()

        self.assertEqual(self._count_trip_loads(), [])

    def test_a_trip_crossing_its_cutoff_between_ticks_is_picked_up_next_time(self):
        """The boundary. The cutoff is recomputed per tick, so a claim that was too
        young a moment ago is due once enough time has passed — proved by moving the
        claim rather than the clock."""
        name = self._trip(0)
        frappe.db.commit()
        self.assertEqual(self._count_trip_loads(), [], "not due on the first tick")

        frappe.db.set_value(
            "Trip Boarding State",
            {"parent": name, "parenttype": "Dispatch Trip"},
            "worker_claim_at",
            add_to_date(now_datetime(), minutes=-(self.cutoff_minutes + 5)),
        )
        frappe.db.commit()

        self.assertEqual(
            self._count_trip_loads(), [name], "the next tick must pick it up"
        )

    def test_the_row_is_actually_confirmed_so_the_narrowing_did_not_skip_the_work(self):
        """A narrower query that also stopped doing the job would pass the counts above."""
        name = self._trip(self.cutoff_minutes + 5)
        frappe.db.commit()

        boarding_flow.auto_confirm_claimed_boardings()

        row = frappe.get_all(
            "Trip Boarding State",
            filters={"parent": name, "parenttype": "Dispatch Trip"},
            fields=["status", "confirm_source"],
        )[0]
        self.assertEqual(row.status, "Boarded")
        self.assertEqual(row.confirm_source, "Auto")
