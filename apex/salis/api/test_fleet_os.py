# Copyright (c) 2026, AFMCO and contributors
"""The Fleet OS board: what it reports, and what the workshop actions leave behind.

Nothing here mints a vehicle. ``test_dependencies`` names the two roots and Frappe stands them up
once per run, so the two fixture plates are the whole cast. Every case that moves a fixture hands
it back in ``addCleanup`` — a shared record is only reusable while each test leaves it as it found
it.

Three classes that stood in the previous form of this file are gone rather than converted: they
covered ``bulk_stop_vehicles``, ``bulk_workshop_in``, ``create_handover`` and ``get_status_meta``,
a console surface that was retired on purpose and that
``apex/www/test_portal_shell_contract.py`` now forbids from ever returning.
"""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.api import fleet_os

test_dependencies = ["Salis Vehicle", "Salis Driver"]

_RESOLVER = "apex.salis.api.fleet_reader._permitted_projects"

OWNED_PLATE = "_T ABC 1001"
RENTED_PLATE = "_T ABC 1002"
DRIVER_NAME = "_Test Driver"


def _vehicle(plate):
    return frappe.db.get_value("Salis Vehicle", {"plate_number": plate}, "name")


def _driver(full_name):
    return frappe.db.get_value("Salis Driver", {"full_name": full_name}, "name")


def _restore_vehicle(plate):
    """Put a borrowed fixture vehicle back: every stop it collected is cancelled through the
    native lifecycle (whose on_cancel restores the previous status) and the status is pinned
    back to Active in case the test moved it without a stop."""
    name = _vehicle(plate)
    for stop in frappe.get_all(
        "Vehicle Suspension", filters={"vehicle": name, "docstatus": 1}, pluck="name"
    ):
        frappe.get_doc("Vehicle Suspension", stop).cancel()
    frappe.db.set_value("Salis Vehicle", name, {"status": "Active", "current_driver": None})


class TestWorkshopEvents(FrappeTestCase):
    """workshop_in/out are audited submittable events, not bare status flips."""

    def setUp(self):
        frappe.set_user("Administrator")
        self.addCleanup(_restore_vehicle, OWNED_PLATE)
        self.plate = OWNED_PLATE
        self.vehicle = _vehicle(OWNED_PLATE)

    def _open_maintenance_stop(self):
        return frappe.db.get_value(
            "Vehicle Suspension",
            {"vehicle": self.vehicle, "stop_reason": "Maintenance", "docstatus": 1,
             "return_date": ["is", "not set"]},
            ["name", "stop_reason", "docstatus"],
            as_dict=True,
        )

    def test_workshop_in_creates_submitted_maintenance_stop(self):
        res = fleet_os.workshop_in(self.plate, expected_return="2026-07-01", notes="brakes")
        stop = self._open_maintenance_stop()
        self.assertIsNotNone(stop)
        self.assertEqual(stop.name, res["stop"])
        self.assertEqual(stop.stop_reason, "Maintenance")
        self.assertEqual(stop.docstatus, 1)
        self.assertEqual(
            frappe.db.get_value("Salis Vehicle", self.vehicle, "status"), "Under Maintenance"
        )
        notes = frappe.db.get_value("Vehicle Suspension", stop.name, "notes") or ""
        self.assertIn("2026-07-01", notes)
        self.assertIn("brakes", notes)
        self.assertFalse(frappe.db.get_value("Vehicle Suspension", stop.name, "return_date"))

    def test_workshop_out_closes_stop_and_restores_status(self):
        fleet_os.workshop_in(self.plate)
        stop_name = self._open_maintenance_stop().name
        fleet_os.workshop_out(self.plate)
        self.assertEqual(frappe.db.get_value("Vehicle Suspension", stop_name, "docstatus"), 2)
        self.assertTrue(frappe.db.get_value("Vehicle Suspension", stop_name, "return_date"))
        self.assertEqual(
            frappe.db.get_value("Salis Vehicle", self.vehicle, "status"), "Active"
        )
        self.assertIsNone(self._open_maintenance_stop())

    def test_workshop_out_without_open_stop_throws(self):
        with self.assertRaises(frappe.ValidationError):
            fleet_os.workshop_out(self.plate)


class TestReaderErrors(FrappeTestCase):
    """A failing secondary reader degrades to a dismissible notice, not a blank
    board: the vehicles still return and the failure is named in reader_errors."""

    def setUp(self):
        frappe.set_user("Administrator")

    def test_partial_reader_failure_is_signalled_not_thrown(self):
        real_get_all = frappe.get_all

        def boom(doctype, *a, **kw):
            if doctype == "Vehicle Incident":
                raise RuntimeError("incident store offline")
            return real_get_all(doctype, *a, **kw)

        with patch(_RESOLVER, return_value=(True, None)), patch.object(frappe, "get_all", side_effect=boom):
            r = fleet_os.get_fleet_os()

        self.assertTrue(r["vehicles"], "the board must still return vehicles")
        self.assertIn(OWNED_PLATE, [v["plate"] for v in r["vehicles"]])
        self.assertTrue(r["reader_errors"], "the failed reader must be signalled")
        self.assertTrue(any("error" in e and "reader" in e for e in r["reader_errors"]))

    def test_clean_read_has_empty_reader_errors(self):
        with patch(_RESOLVER, return_value=(True, None)):
            r = fleet_os.get_fleet_os()
        self.assertEqual(r["reader_errors"], [])

    def test_empty_branches_carry_reader_errors_key(self):
        with patch(_RESOLVER, return_value=(False, [])):
            scope_empty = fleet_os.get_fleet_os()
        self.assertEqual(scope_empty["reason"], "scope_empty")
        self.assertEqual(scope_empty["reader_errors"], [])


class TestWorkshopLane(FrappeTestCase):
    """get_fleet_os carries the workshop lane: entry date, days-in-workshop and
    the overstay flag for a vehicle with an open Maintenance stop."""

    def setUp(self):
        frappe.set_user("Administrator")

    def _row_for(self, plate):
        with patch(_RESOLVER, return_value=(True, None)):
            for v in fleet_os.get_fleet_os().get("vehicles", []):
                if v.get("plate") == plate:
                    return v
        return None

    def test_workshop_fields_populate_for_a_vehicle_in_the_shop(self):
        self.addCleanup(_restore_vehicle, OWNED_PLATE)
        fleet_os.workshop_in(OWNED_PLATE, notes="gearbox")

        row = self._row_for(OWNED_PLATE)
        self.assertIsNotNone(row)
        self.assertEqual(row["vehicle_status"], "workshop")
        self.assertTrue(row["workshop_date"], "the workshop entry date must be set")
        self.assertIn("gearbox", row["workshop_notes"])
        self.assertGreaterEqual(row["days_in_workshop"], 0)
        self.assertIn("workshop_overstay", row)
        self.assertFalse(row["workshop_overstay"])

    def test_non_workshop_vehicle_has_blank_lane(self):
        row = self._row_for(RENTED_PLATE)
        self.assertIsNotNone(row)
        self.assertEqual(row["workshop_date"], "")
        self.assertEqual(row["days_in_workshop"], 0)
        self.assertFalse(row["workshop_overstay"])


class TestVehicleTimeline(FrappeTestCase):
    """get_vehicle_timeline merges assignments + stops + incidents + alerts into
    one descending feed, read-scoped and PII-gated."""

    def setUp(self):
        frappe.set_user("Administrator")
        # Registered LIFO: the session is handed back to Administrator FIRST, so the
        # restore that follows it runs with the rights to cancel what the case submitted.
        self.addCleanup(_restore_vehicle, OWNED_PLATE)
        self.addCleanup(frappe.set_user, "Administrator")
        self.vehicle = _vehicle(OWNED_PLATE)

    def test_timeline_merges_every_source_descending(self):
        inc = frappe.get_doc(
            {
                "doctype": "Vehicle Incident",
                "incident_type": "Accident",
                "vehicle": self.vehicle,
                "incident_date": "2026-06-02",
                "description": "Side scrape.",
                "status": "Open",
            }
        ).insert(ignore_permissions=True)
        inc.submit()
        fleet_os.workshop_in(OWNED_PLATE)

        res = fleet_os.get_vehicle_timeline(OWNED_PLATE)
        kinds = {e["kind"] for e in res["events"]}
        self.assertIn("incident", kinds)
        self.assertIn("stop", kinds)
        dates = [e["date"] for e in res["events"] if e["date"]]
        self.assertEqual(dates, sorted(dates, reverse=True))

    def test_timeline_blanks_driver_for_non_pii_role(self):
        driver = _driver(DRIVER_NAME)
        asg = frappe.get_doc(
            {
                "doctype": "Vehicle Assignment",
                "vehicle": self.vehicle,
                "driver": driver,
                "start_date": "2026-06-01",
                "status": "Active",
            }
        ).insert(ignore_permissions=True)
        asg.submit()
        self.addCleanup(frappe.db.set_value, "Salis Driver", driver, "current_vehicle", None)

        rows = [e for e in fleet_os.get_vehicle_timeline(OWNED_PLATE)["events"] if e["kind"] == "assignment"]
        self.assertTrue(rows)
        self.assertEqual(rows[0]["driver"], driver)

        email = "tl-timeline-auditor@test.local"
        if not frappe.db.exists("User", email):
            frappe.get_doc(
                {
                    "doctype": "User",
                    "email": email,
                    "first_name": "TL Timeline Auditor",
                    "roles": [{"role": "Internal Auditor"}],
                }
            ).insert(ignore_permissions=True)
        frappe.set_user(email)
        blanked = [
            e for e in fleet_os.get_vehicle_timeline(OWNED_PLATE)["events"] if e["kind"] == "assignment"
        ]
        self.assertTrue(blanked, "the timeline must STILL be visible (non-vacuous check)")
        self.assertEqual(blanked[0]["driver"], "")
