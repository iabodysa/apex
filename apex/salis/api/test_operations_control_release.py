# Copyright (c) 2026, AFMCO and contributors
"""Guard for the Fleet Control drawer 'Release vehicle' action
(salis/api/operations_control.release_vehicle).

Two properties must hold:

  1. Release closes the vehicle's open Vehicle Suspension through the NATIVE submittable
     lifecycle — the stop is cancelled (docstatus 2) so its on_cancel restores the
     vehicle to its previous status (Active), and the release audit fields
     (return_date / released_on / released_by) are stamped on the stop. The
     controller is never bypassed, so a refactor that pokes the vehicle status
     directly or skips the cancel fails here.
  2. The action is permission-gated on Salis Vehicle "write": a read-only oversight
     role (Internal Auditor) is refused.

The vehicle is the shipped fixture. The stop each case needs IS the subject, so it is
still built here; everything the cases do to the borrowed vehicle is handed back.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.api.operations_control import get_fleet, release_vehicle

test_dependencies = ["Salis Vehicle"]

PLATE = "_T ABC 1001"
SPARE_PLATE = "_T ABC 1002"


def _vehicle(plate):
    return frappe.db.get_value("Salis Vehicle", {"plate_number": plate}, "name")


def _restore(plate):
    """Cancel whatever stop the case left behind (on_cancel restores the previous status),
    then pin the borrowed vehicle back to the state the fixture ships."""
    name = _vehicle(plate)
    for stop in frappe.get_all(
        "Vehicle Suspension", filters={"vehicle": name, "docstatus": 1}, pluck="name"
    ):
        frappe.get_doc("Vehicle Suspension", stop).cancel()
    frappe.db.set_value(
        "Salis Vehicle",
        name,
        {"status": "Active", "compliance_status": "Not Tracked", "next_expiry_date": None},
    )


class TestOperationsControlRelease(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        # Registered LIFO: the session is handed back to Administrator FIRST, so the
        # restore that follows it runs with the rights to cancel what the case submitted.
        self.addCleanup(_restore, PLATE)
        self.addCleanup(frappe.set_user, "Administrator")
        self.vehicle = _vehicle(PLATE)

    def _stopped_vehicle(self):
        """The fixture vehicle taken to 'Stopped' by submitting a Vehicle Suspension, so
        the release path has a real open stop to close."""
        stop = frappe.get_doc(
            {
                "doctype": "Vehicle Suspension",
                "vehicle": self.vehicle,
                "stop_reason": "Maintenance",
                "stop_date": frappe.utils.today(),
            }
        )
        stop.insert(ignore_permissions=True)
        stop.submit()
        self.assertEqual(
            frappe.db.get_value("Salis Vehicle", self.vehicle, "status"), "Stopped"
        )
        return stop.name

    def _auditor_user(self):
        """A read-only oversight role: read but NOT write on Salis Vehicle, so the
        endpoint's write-gate (not row scope) is what refuses it."""
        email = "oc-release-auditor@test.local"
        if not frappe.db.exists("User", email):
            frappe.get_doc(
                {
                    "doctype": "User",
                    "email": email,
                    "first_name": "OC Release Auditor",
                    "roles": [{"role": "Internal Auditor"}],
                }
            ).insert(ignore_permissions=True)
        return email

    def test_release_closes_stop_and_restores_vehicle(self):
        stop = self._stopped_vehicle()
        res = release_vehicle(self.vehicle)
        self.assertTrue(res.get("ok"))
        self.assertEqual(res.get("stop"), stop)
        self.assertEqual(frappe.db.get_value("Vehicle Suspension", stop, "docstatus"), 2)
        self.assertEqual(frappe.db.get_value("Salis Vehicle", self.vehicle, "status"), "Active")
        row = frappe.db.get_value(
            "Vehicle Suspension", stop, ["return_date", "released_on", "released_by"], as_dict=True
        )
        today = frappe.utils.getdate()
        self.assertEqual(frappe.utils.getdate(row.return_date), today)
        self.assertEqual(frappe.utils.getdate(row.released_on), today)
        self.assertEqual(row.released_by, "Administrator")

    def test_release_honours_supplied_return_date(self):
        stop = self._stopped_vehicle()
        ret = frappe.utils.add_days(frappe.utils.today(), -2)
        release_vehicle(self.vehicle, return_date=ret)
        self.assertEqual(
            frappe.utils.getdate(frappe.db.get_value("Vehicle Suspension", stop, "return_date")),
            frappe.utils.getdate(ret),
        )

    def test_release_with_no_open_stop_throws(self):
        with self.assertRaises(frappe.ValidationError):
            release_vehicle(self.vehicle)

    def test_release_gated_on_vehicle_write(self):
        self._stopped_vehicle()
        frappe.set_user(self._auditor_user())
        with self.assertRaises(frappe.PermissionError):
            release_vehicle(self.vehicle)


class TestOperationsControlFleet(FrappeTestCase):
    """get_fleet must carry each vehicle's compliance fields to the cards, so the
    board can flag at-risk vehicles without a second per-card read."""

    def setUp(self):
        frappe.set_user("Administrator")
        self.addCleanup(_restore, SPARE_PLATE)
        self.vehicle = _vehicle(SPARE_PLATE)

    def test_get_fleet_returns_compliance_fields(self):
        expiry = frappe.utils.add_days(frappe.utils.today(), 10)
        frappe.db.set_value(
            "Salis Vehicle",
            self.vehicle,
            {"compliance_status": "Expiring Soon", "next_expiry_date": expiry},
        )

        row = next(v for v in get_fleet(search=SPARE_PLATE)["vehicles"] if v["name"] == self.vehicle)
        self.assertEqual(row["compliance_status"], "Expiring Soon")
        self.assertEqual(frappe.utils.getdate(row["next_expiry_date"]), frappe.utils.getdate(expiry))

    def test_summary_counts_compliance_at_risk(self):
        """The board summary counts the same 'at risk' compliance states the card
        flags (Expiring Soon / Expired), and carries the stopped-overdue keys."""
        frappe.db.set_value("Salis Vehicle", self.vehicle, "compliance_status", "Expired")

        summary = get_fleet(search=SPARE_PLATE)["summary"]
        self.assertGreaterEqual(summary["compliance_at_risk"], 1)
        self.assertIn("stopped_over_n", summary)
        self.assertIn("stopped_over_days", summary)

    def test_summary_counts_stopped_over_n(self):
        """A vehicle still Stopped on a Maintenance stop older than the overstay
        cutoff is counted by stopped_over_n (reusing tasks._overstay_stops)."""
        stop = frappe.get_doc(
            {
                "doctype": "Vehicle Suspension",
                "vehicle": self.vehicle,
                "stop_reason": "Maintenance",
                "stop_date": frappe.utils.today(),
            }
        )
        stop.insert(ignore_permissions=True)
        stop.submit()
        frappe.db.set_value(
            "Vehicle Suspension", stop.name, "stop_date", frappe.utils.add_days(frappe.utils.today(), -30)
        )

        summary = get_fleet(search=SPARE_PLATE)["summary"]
        self.assertGreaterEqual(summary["stopped_over_n"], 1)
