"""Guard for the Fleet Control drawer 'Release vehicle' action
(salis/api/operations_control.release_vehicle).

Two properties must hold:

  1. Release closes the vehicle's open Vehicle Stop through the NATIVE submittable
     lifecycle — the stop is cancelled (docstatus 2) so its on_cancel restores the
     vehicle to its previous status (Active), and the release audit fields
     (return_date / released_on / released_by) are stamped on the stop. The
     controller is never bypassed, so a refactor that pokes the vehicle status
     directly or skips the cancel fails here.
  2. The action is permission-gated on Salis Vehicle "write": a read-only oversight
     role (Internal Auditor) is refused.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex_habitat.salis.api.operations_control import release_vehicle


class TestOperationsControlRelease(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")

    def _stopped_vehicle(self):
        """An Active vehicle taken to 'Stopped' by submitting a Vehicle Stop, so
        the release path has a real open stop to close. Keyed off the test method
        so the plate stays unique per test."""
        tag = self._testMethodName
        plate = "OCREL " + tag
        vehicle = frappe.get_doc(
            {
                "doctype": "Salis Vehicle",
                "plate_number": plate,
                "status": "Active",
            }
        ).insert(ignore_permissions=True)
        stop = frappe.get_doc(
            {
                "doctype": "Vehicle Stop",
                "vehicle": vehicle.name,
                "stop_reason": "Maintenance",
                "stop_date": frappe.utils.today(),
            }
        )
        stop.insert(ignore_permissions=True)
        stop.submit()
        # on_submit must have stopped the vehicle for the precondition to hold.
        self.assertEqual(
            frappe.db.get_value("Salis Vehicle", vehicle.name, "status"), "Stopped"
        )
        return vehicle.name, stop.name

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
        vehicle, stop = self._stopped_vehicle()
        res = release_vehicle(vehicle)
        self.assertTrue(res.get("ok"))
        self.assertEqual(res.get("stop"), stop)
        # The stop is cancelled via the native lifecycle...
        self.assertEqual(frappe.db.get_value("Vehicle Stop", stop, "docstatus"), 2)
        # ...whose on_cancel restored the vehicle to its previous (Active) status.
        self.assertEqual(
            frappe.db.get_value("Salis Vehicle", vehicle, "status"), "Active"
        )
        # Release audit fields are stamped on the stop.
        row = frappe.db.get_value(
            "Vehicle Stop", stop, ["return_date", "released_on", "released_by"], as_dict=True
        )
        today = frappe.utils.getdate()
        self.assertEqual(frappe.utils.getdate(row.return_date), today)
        self.assertEqual(frappe.utils.getdate(row.released_on), today)
        self.assertEqual(row.released_by, "Administrator")

    def test_release_honours_supplied_return_date(self):
        vehicle, stop = self._stopped_vehicle()
        ret = frappe.utils.add_days(frappe.utils.today(), -2)
        release_vehicle(vehicle, return_date=ret)
        self.assertEqual(
            frappe.utils.getdate(frappe.db.get_value("Vehicle Stop", stop, "return_date")),
            frappe.utils.getdate(ret),
        )

    def test_release_with_no_open_stop_throws(self):
        plate = "OCREL-NOSTOP"
        if not frappe.db.exists("Salis Vehicle", {"plate_number": plate}):
            frappe.get_doc(
                {"doctype": "Salis Vehicle", "plate_number": plate, "status": "Active"}
            ).insert(ignore_permissions=True)
        name = frappe.db.get_value("Salis Vehicle", {"plate_number": plate}, "name")
        with self.assertRaises(frappe.ValidationError):
            release_vehicle(name)

    def test_release_gated_on_vehicle_write(self):
        vehicle, _stop = self._stopped_vehicle()
        frappe.set_user(self._auditor_user())
        with self.assertRaises(frappe.PermissionError):
            release_vehicle(vehicle)
