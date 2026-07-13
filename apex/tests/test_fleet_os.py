# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Fleet OS dashboard reader's typed empty reason.

get_fleet_os tells an empty board apart from an access gap: ``scope_empty`` (the
user is scoped to no project), ``data_empty`` (the permitted fleet is empty), or
``reason: None`` when vehicles are returned. The project-scope resolver is
patched so each branch is exercised deterministically on a fresh site.
"""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.api import fleet_os

# [#awh5oi]
_RESOLVER = "apex.salis.api.fleet_reader._permitted_projects"


class TestFleetOSEmptyReason(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def test_scope_empty_when_no_permitted_project(self):
        # [#tmtqtu]
        with patch(_RESOLVER, return_value=(False, [])):
            r = fleet_os.get_fleet_os()
        self.assertEqual(r["vehicles"], [])
        self.assertEqual(r["reason"], "scope_empty")

    def test_data_empty_when_scope_has_no_vehicles(self):
        # [#29d5x3]
        ghost = f"NO-SUCH-PROJECT-{frappe.generate_hash(length=10)}"
        with patch(_RESOLVER, return_value=(False, [ghost])):
            r = fleet_os.get_fleet_os()
        self.assertEqual(r["vehicles"], [])
        self.assertEqual(r["reason"], "data_empty")

    def test_no_reason_when_vehicles_returned(self):
        plate = f"FOS {frappe.generate_hash(length=12)}"
        name = frappe.get_doc(
            {"doctype": "Salis Vehicle", "plate_number": plate, "status": "Active"}
        ).insert(ignore_permissions=True).name
        # [#gdata3]
        with patch(_RESOLVER, return_value=(True, None)):
            r = fleet_os.get_fleet_os()
        self.assertIsNone(r["reason"])
        self.assertTrue(r["vehicles"])
        self.assertIn(plate, [v["plate"] for v in r["vehicles"]], name)


class TestWorkshopEvents(FrappeTestCase):
    """workshop_in/out are audited submittable events, not bare status flips."""

    def setUp(self):
        frappe.set_user("Administrator")
        self.plate = f"WS {frappe.generate_hash(length=12)}"
        self.vehicle = (
            frappe.get_doc(
                {"doctype": "Salis Vehicle", "plate_number": self.plate, "status": "Active"}
            )
            .insert(ignore_permissions=True)
            .name
        )

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
        # [#lpxlre]
        self.assertIsNotNone(stop)
        self.assertEqual(stop.name, res["stop"])
        self.assertEqual(stop.stop_reason, "Maintenance")
        self.assertEqual(stop.docstatus, 1)
        # [#9f0wdi]
        self.assertEqual(
            frappe.db.get_value("Salis Vehicle", self.vehicle, "status"), "Under Maintenance"
        )
        # [#bo1uxf]
        notes = frappe.db.get_value("Vehicle Suspension", stop.name, "notes") or ""
        self.assertIn("2026-07-01", notes)
        self.assertIn("brakes", notes)
        self.assertFalse(frappe.db.get_value("Vehicle Suspension", stop.name, "return_date"))

    def test_workshop_out_closes_stop_and_restores_status(self):
        fleet_os.workshop_in(self.plate)
        stop_name = self._open_maintenance_stop().name
        fleet_os.workshop_out(self.plate)
        # [#25ns0m]
        self.assertEqual(frappe.db.get_value("Vehicle Suspension", stop_name, "docstatus"), 2)
        self.assertTrue(frappe.db.get_value("Vehicle Suspension", stop_name, "return_date"))
        # [#luh90t]
        self.assertEqual(
            frappe.db.get_value("Salis Vehicle", self.vehicle, "status"), "Active"
        )
        # [#7abhi0]
        self.assertIsNone(self._open_maintenance_stop())

    def test_workshop_out_without_open_stop_throws(self):
        # [#b9z9nk]
        with self.assertRaises(frappe.ValidationError):
            fleet_os.workshop_out(self.plate)


class TestBulkActions(FrappeTestCase):
    """Bulk stop / workshop-in fan a single-vehicle action over many plates,
    isolating each row so one bad plate can't abort the rest."""

    def setUp(self):
        frappe.set_user("Administrator")
        self.plates = []
        for _i in range(2):
            plate = f"BLK {frappe.generate_hash(length=12)}"
            frappe.get_doc(
                {"doctype": "Salis Vehicle", "plate_number": plate, "status": "Active"}
            ).insert(ignore_permissions=True)
            self.plates.append(plate)

    def test_bulk_stop_stops_every_selected_vehicle(self):
        res = fleet_os.bulk_stop_vehicles(self.plates, reason="rental return")
        self.assertTrue(res["ok"])
        self.assertEqual(res["succeeded"], 2)
        self.assertEqual(res["failed"], 0)
        for plate in self.plates:
            name = frappe.db.get_value("Salis Vehicle", {"plate_number": plate}, "name")
            self.assertEqual(frappe.db.get_value("Salis Vehicle", name, "status"), "Stopped")

    def test_bulk_workshop_in_sends_every_selected_vehicle(self):
        res = fleet_os.bulk_workshop_in(self.plates, notes="service")
        self.assertTrue(res["ok"])
        self.assertEqual(res["succeeded"], 2)
        for plate in self.plates:
            name = frappe.db.get_value("Salis Vehicle", {"plate_number": plate}, "name")
            self.assertEqual(
                frappe.db.get_value("Salis Vehicle", name, "status"), "Under Maintenance"
            )

    def test_bulk_isolates_a_failing_row(self):
        # [#q9phuj]
        ghost = f"NO-SUCH {frappe.generate_hash(length=12)}"
        res = fleet_os.bulk_stop_vehicles([self.plates[0], ghost])
        self.assertFalse(res["ok"])
        self.assertEqual(res["succeeded"], 1)
        self.assertEqual(res["failed"], 1)
        by_plate = {r["plate"]: r for r in res["results"]}
        self.assertTrue(by_plate[self.plates[0]]["ok"])
        self.assertFalse(by_plate[ghost]["ok"])
        self.assertIn("error", by_plate[ghost])
        # [#gjfsio]
        good = frappe.db.get_value("Salis Vehicle", {"plate_number": self.plates[0]}, "name")
        self.assertEqual(frappe.db.get_value("Salis Vehicle", good, "status"), "Stopped")

    def test_bulk_empty_selection_throws(self):
        with self.assertRaises(frappe.ValidationError):
            fleet_os.bulk_stop_vehicles([])


class TestReaderErrors(FrappeTestCase):
    """A failing secondary reader degrades to a dismissible notice, not a blank
    board: the vehicles still return and the failure is named in reader_errors."""

    def setUp(self):
        frappe.set_user("Administrator")

    def test_partial_reader_failure_is_signalled_not_thrown(self):
        plate = f"RE {frappe.generate_hash(length=12)}"
        frappe.get_doc(
            {"doctype": "Salis Vehicle", "plate_number": plate, "status": "Active"}
        ).insert(ignore_permissions=True)

        # [#piajr8]
        real_get_all = frappe.get_all

        def boom(doctype, *a, **kw):
            if doctype == "Vehicle Incident":
                raise RuntimeError("incident store offline")
            return real_get_all(doctype, *a, **kw)

        with patch(_RESOLVER, return_value=(True, None)), patch.object(frappe, "get_all", side_effect=boom):
            r = fleet_os.get_fleet_os()

        self.assertTrue(r["vehicles"], "the board must still return vehicles")
        self.assertIn(plate, [v["plate"] for v in r["vehicles"]])
        self.assertTrue(r["reader_errors"], "the failed reader must be signalled")
        self.assertTrue(any("error" in e and "reader" in e for e in r["reader_errors"]))

    def test_clean_read_has_empty_reader_errors(self):
        # [#hpyx73]
        with patch(_RESOLVER, return_value=(True, None)):
            r = fleet_os.get_fleet_os()
        self.assertEqual(r["reader_errors"], [])

    def test_empty_branches_carry_reader_errors_key(self):
        # [#ivjtqs]
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
        plate = f"WSL {frappe.generate_hash(length=12)}"
        frappe.get_doc(
            {"doctype": "Salis Vehicle", "plate_number": plate, "status": "Active"}
        ).insert(ignore_permissions=True)
        fleet_os.workshop_in(plate, notes="gearbox")

        row = self._row_for(plate)
        self.assertIsNotNone(row)
        self.assertEqual(row["vehicle_status"], "workshop")
        self.assertTrue(row["workshop_date"], "the workshop entry date must be set")
        self.assertIn("gearbox", row["workshop_notes"])
        self.assertGreaterEqual(row["days_in_workshop"], 0)
        self.assertIn("workshop_overstay", row)
        # [#4t55az]
        self.assertFalse(row["workshop_overstay"])

    def test_non_workshop_vehicle_has_blank_lane(self):
        plate = f"WSL {frappe.generate_hash(length=12)}"
        frappe.get_doc(
            {"doctype": "Salis Vehicle", "plate_number": plate, "status": "Active"}
        ).insert(ignore_permissions=True)
        row = self._row_for(plate)
        self.assertIsNotNone(row)
        self.assertEqual(row["workshop_date"], "")
        self.assertEqual(row["days_in_workshop"], 0)
        self.assertFalse(row["workshop_overstay"])


class TestStatusMeta(FrappeTestCase):
    """get_status_meta server-drives the SPA status chips off the DocType Select."""

    def setUp(self):
        frappe.set_user("Administrator")

    def test_returns_translated_status_options(self):
        res = fleet_os.get_status_meta()
        values = [s["value"] for s in res["statuses"]]
        # [#bp0cha]
        for opt in ("Active", "Stopped", "Under Maintenance", "Released"):
            self.assertIn(opt, values)
        # [#ipz4cp]
        self.assertTrue(all(s["label"] for s in res["statuses"]))


class TestCreateHandover(FrappeTestCase):
    """create_handover opens an OPTIONAL DRAFT Vehicle Handover after a reassign,
    reusing the native controller; from_driver comes from the latest Ended row."""

    def setUp(self):
        frappe.set_user("Administrator")
        self.plate = f"HO {frappe.generate_hash(length=12)}"
        self.vehicle = (
            frappe.get_doc(
                {"doctype": "Salis Vehicle", "plate_number": self.plate, "status": "Active"}
            )
            .insert(ignore_permissions=True)
            .name
        )

    def _driver(self):
        did = f"HOD-{frappe.generate_hash(length=12)}"
        return (
            frappe.get_doc(
                {
                    "doctype": "Salis Driver",
                    "full_name": "HO Driver",
                    "driver_id": did,
                    "status": "Active",
                }
            )
            .insert(ignore_permissions=True)
        )

    def test_draft_handover_carries_prev_and_new_driver(self):
        # [#lt96xt]
        a, b = self._driver(), self._driver()
        fleet_os.reassign(self.plate, a.driver_id)
        fleet_os.reassign(self.plate, b.driver_id)

        res = fleet_os.create_handover(self.plate, b.driver_id, odometer=120)
        self.assertTrue(res["ok"])
        ho = frappe.get_doc("Vehicle Handover", res["handover"])
        # [#13taxw]
        self.assertEqual(ho.docstatus, 0)
        self.assertEqual(ho.vehicle, self.vehicle)
        self.assertEqual(ho.to_driver, b.name)
        self.assertEqual(ho.from_driver, a.name)
        self.assertEqual(ho.odometer_reading, 120)

    def test_first_assignment_drafts_no_handover(self):
        # [#jfj02n]
        a = self._driver()
        fleet_os.reassign(self.plate, a.driver_id)
        res = fleet_os.create_handover(self.plate, a.driver_id)
        self.assertTrue(res["ok"])
        self.assertIsNone(res["handover"])
        self.assertEqual(res.get("skipped"), "no_prior_driver")
        # [#8unn2b]
        self.assertEqual(
            frappe.db.count("Vehicle Handover", {"vehicle": self.vehicle}), 0
        )

    def test_unknown_driver_throws(self):
        with self.assertRaises(frappe.ValidationError):
            fleet_os.create_handover(self.plate, f"NO-SUCH-{frappe.generate_hash(length=12)}")


class TestVehicleTimeline(FrappeTestCase):
    """get_vehicle_timeline merges assignments + stops + incidents + alerts into
    one descending feed, read-scoped and PII-gated."""

    def setUp(self):
        frappe.set_user("Administrator")

    def test_timeline_merges_every_source_descending(self):
        plate = f"TL {frappe.generate_hash(length=12)}"
        veh = (
            frappe.get_doc(
                {"doctype": "Salis Vehicle", "plate_number": plate, "status": "Active"}
            )
            .insert(ignore_permissions=True)
            .name
        )
        inc = frappe.get_doc(
            {
                "doctype": "Vehicle Incident",
                "incident_type": "Accident",
                "vehicle": veh,
                "incident_date": "2026-06-02",
                "description": "Side scrape.",
                "status": "Open",
            }
        ).insert(ignore_permissions=True)
        inc.submit()
        # [#9oina1]
        fleet_os.workshop_in(plate)  # [#85do72]

        res = fleet_os.get_vehicle_timeline(plate)
        kinds = {e["kind"] for e in res["events"]}
        self.assertIn("incident", kinds)
        self.assertIn("stop", kinds)
        # [#dud1wb]
        dates = [e["date"] for e in res["events"] if e["date"]]
        self.assertEqual(dates, sorted(dates, reverse=True))

    def test_timeline_blanks_driver_for_non_pii_role(self):
        plate = f"TL {frappe.generate_hash(length=12)}"
        veh = (
            frappe.get_doc(
                {"doctype": "Salis Vehicle", "plate_number": plate, "status": "Active"}
            )
            .insert(ignore_permissions=True)
            .name
        )
        driver = frappe.get_doc(
            {
                "doctype": "Salis Driver",
                "full_name": "TL Driver",
                "driver_id": f"TLD-{frappe.generate_hash(length=12)}",
                "status": "Active",
            }
        ).insert(ignore_permissions=True)
        asg = frappe.get_doc(
            {
                "doctype": "Vehicle Assignment",
                "vehicle": veh,
                "driver": driver.name,
                "start_date": "2026-06-01",
                "status": "Active",
            }
        ).insert(ignore_permissions=True)
        asg.submit()

        # [#qytune]
        rows = [e for e in fleet_os.get_vehicle_timeline(plate)["events"] if e["kind"] == "assignment"]
        self.assertTrue(rows)
        self.assertEqual(rows[0]["driver"], driver.name)

        # [#796x71]
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
        try:
            frappe.set_user(email)
            blanked = [
                e for e in fleet_os.get_vehicle_timeline(plate)["events"] if e["kind"] == "assignment"
            ]
        finally:
            frappe.set_user("Administrator")
        self.assertTrue(blanked, "the timeline must STILL be visible (non-vacuous check)")
        self.assertEqual(blanked[0]["driver"], "")
