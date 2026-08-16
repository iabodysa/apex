# Copyright (c) 2026, afmcoltd
"""What a stop refuses, and what it only reports.

A planned trip refuses the stop, because its driver can still be changed. A dispatched
trip is a vehicle already in motion, and a stop raised after an accident cannot wait for
it, so it reaches the supervisor as a comment instead.
"""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from apex.salis.doctype.driver_suspension import driver_suspension


class TestDriverSuspension(TestCase):
    @patch.object(driver_suspension, "refuse_to_stop_a_driver_who_still_holds_planned_trips")
    @patch.object(driver_suspension, "frappe")
    def test_the_trip_check_runs_while_the_form_is_being_filled(self, _frappe, refuse):
        """On validate, not on submit: the operator learns he must hand the trips over
        while he is still writing the stop, not after he has asked for it to take effect."""
        doc = SimpleNamespace(driver="DRV-1", release_vehicle=0, related_vehicle=None)

        driver_suspension.DriverSuspension.validate(doc)

        refuse.assert_called_once_with("DRV-1")

    @patch.object(driver_suspension, "dispatched_trips_for_driver")
    def test_a_trip_still_on_the_road_is_reported_and_never_refused(self, running):
        """The stop already succeeded by the time this runs. Refusing here would leave a
        suspended driver whose accident the supervisor never sees named against a trip."""
        running.return_value = ["DT-0044"]
        doc = SimpleNamespace(driver="DRV-1", add_comment=_Recorder())

        driver_suspension.DriverSuspension._report_any_trip_he_is_still_running(doc)

        self.assertIn("DT-0044", doc.add_comment.calls[0][1])

    @patch.object(driver_suspension, "dispatched_trips_for_driver")
    def test_no_running_trip_leaves_no_comment(self, running):
        """A stop on a driver who is not out today says nothing, so the comment carries
        a fact when it appears."""
        running.return_value = []
        doc = SimpleNamespace(driver="DRV-1", add_comment=_Recorder())

        driver_suspension.DriverSuspension._report_any_trip_he_is_still_running(doc)

        self.assertEqual(doc.add_comment.calls, [])


class _Recorder:
    """Captures ``add_comment`` arguments; ``SimpleNamespace`` has no Mock of its own."""

    def __init__(self):
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args)
