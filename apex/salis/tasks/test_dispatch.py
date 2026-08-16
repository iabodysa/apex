from __future__ import annotations

from datetime import date, datetime, time
from unittest.mock import MagicMock, call, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.tasks.dispatch import (
    generation_key,
    generate_for_assignment,
    planned_window,
    scheduled_dates,
)


class TestRecurringDispatch(FrappeTestCase):
    def test_scheduled_dates_respect_weekdays_and_assignment_bounds(self):
        self.assertEqual(
            scheduled_dates(
                date(2026, 8, 13),
                date(2026, 8, 16),
                {"Thursday", "Saturday"},
            ),
            [date(2026, 8, 13), date(2026, 8, 15)],
        )

    def test_planned_window_rolls_overnight_end_into_next_day(self):
        start, end = planned_window(date(2026, 8, 13), time(22, 0), time(5, 0))

        self.assertEqual(start, datetime(2026, 8, 13, 22, 0))
        self.assertEqual(end, datetime(2026, 8, 14, 5, 0))

    def test_generation_key_is_stable_per_assignment_and_date(self):
        self.assertEqual(
            generation_key("RA-0001", date(2026, 8, 13)),
            "RA-0001:2026-08-13",
        )

    @patch("apex.salis.tasks.dispatch.frappe.new_doc")
    @patch("apex.salis.tasks.dispatch.frappe.db.exists")
    @patch("apex.salis.tasks.dispatch.frappe.get_doc")
    def test_generator_creates_only_missing_applicable_trips(
        self, get_doc, exists, new_doc
    ):
        assignment = frappe._dict(
            name="RA-0001",
            docstatus=1,
            status="Approved",
            enabled=1,
            starts_on=date(2026, 8, 13),
            ends_on=None,
            generated_through=None,
            work_shift="WS-0001",
            route_template="RT-0001",
            project="PROJ-1",
            driver="DRV-1",
            vehicle="VEH-1",
            shift_name="Night",
            assignment_name="Housing · Night · Project",
            db_set=MagicMock(),
        )
        shift = frappe._dict(
            is_active=1,
            start_time=time(22, 0),
            end_time=time(5, 0),
            applicable_days=[
                frappe._dict(day_of_week="Thursday"),
                frappe._dict(day_of_week="Saturday"),
            ],
        )
        get_doc.side_effect = [assignment, shift]
        exists.side_effect = [False, True]
        trip = MagicMock()
        new_doc.return_value = trip

        count = generate_for_assignment(
            "RA-0001", start_date="2026-08-13", end_date="2026-08-15"
        )

        self.assertEqual(count, 1)
        trip.update.assert_called_once()
        payload = trip.update.call_args.args[0]
        self.assertEqual(payload["route_assignment"], "RA-0001")
        self.assertEqual(payload["generation_key"], "RA-0001:2026-08-13")
        self.assertEqual(payload["planned_end"], datetime(2026, 8, 14, 5, 0))
        trip.insert.assert_called_once()
        assignment.db_set.assert_called_once_with(
            "generated_through", date(2026, 8, 15), update_modified=False
        )
        self.assertEqual(
            exists.call_args_list,
            [
                call("Dispatch Trip", {"generation_key": "RA-0001:2026-08-13"}),
                call("Dispatch Trip", {"generation_key": "RA-0001:2026-08-15"}),
            ],
        )

    @patch("apex.salis.tasks.dispatch.frappe.db.get_value")
    @patch("apex.salis.tasks.dispatch.frappe.new_doc")
    @patch("apex.salis.tasks.dispatch.frappe.db.exists")
    @patch("apex.salis.tasks.dispatch.frappe.get_doc")
    def test_a_stopped_driver_is_left_off_the_trip_the_shift_generates(
        self, get_doc, exists, new_doc, get_value
    ):
        """The route still runs, with no driver, so the assignment queue picks it up.

        The assignment names its driver once and regenerates from it every shift. Without
        this the generator writes a stopped driver's name back onto tomorrow's trip the
        morning after he was stopped, and the refusal that made him hand today's trips over
        buys nothing.
        """
        assignment = frappe._dict(
            name="RA-0002",
            docstatus=1,
            status="Approved",
            enabled=1,
            starts_on=date(2026, 8, 13),
            ends_on=None,
            generated_through=None,
            work_shift="WS-0001",
            route_template="RT-0001",
            project="PROJ-1",
            driver="DRV-STOPPED",
            vehicle="VEH-1",
            shift_name="Night",
            db_set=MagicMock(),
        )
        shift = frappe._dict(
            is_active=1,
            start_time=time(22, 0),
            end_time=time(5, 0),
            applicable_days=[frappe._dict(day_of_week="Thursday")],
        )
        get_doc.side_effect = [assignment, shift]
        exists.return_value = False
        get_value.return_value = "Stopped"
        trip = MagicMock()
        new_doc.return_value = trip

        generate_for_assignment("RA-0002", start_date="2026-08-13", end_date="2026-08-13")

        payload = trip.update.call_args.args[0]
        self.assertIsNone(
            payload["driver"], "a stopped driver must not be written onto a new trip"
        )
        self.assertEqual(
            payload["vehicle"], "VEH-1", "the route and its vehicle still run"
        )
