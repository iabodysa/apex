"""F-01 / F-08 row-scoping for Salis Vehicle, Salis Driver and Passenger Manifest.

Closes the desk-list enumeration leak (a scoped Fleet Supervisor could list every
project's vehicles/drivers/manifests at /app/salis-vehicle etc.), while preserving
the Driver `if_owner` self-profile (a Driver still sees their own row)."""


import frappe
from frappe.tests.utils import FrappeTestCase

from apex_habitat.salis.permissions import (
    passenger_manifest_query,
    salis_driver_query,
    salis_vehicle_query,
    scoped_has_permission,
    trip_start_log_has_permission,
    trip_start_log_query,
)
from apex_habitat.tests._helpers import _user


class TestSalisFleetScoping(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.pa = cls._project("Fleet Scope A")
        cls.sup = _user("fleet_sup@example.com", "Fleet Supervisor")   # scoped to pa
        cls.mgr = _user("fleet_mgr@example.com", "Fleet Manager")      # unscoped oversight
        cls.drv = _user("fleet_drv@example.com", "Driver")             # scoped, no project grant
        if not frappe.db.exists(
            "User Permission", {"allow": "Project", "for_value": cls.pa, "user": cls.sup}
        ):
            frappe.get_doc(
                {"doctype": "User Permission", "allow": "Project", "for_value": cls.pa, "user": cls.sup}
            ).insert(ignore_permissions=True)

    @staticmethod
    def _project(name):
        p = frappe.db.get_value("Project", {"project_name": name}, "name")
        if not p:
            p = frappe.get_doc({"doctype": "Project", "project_name": name}).insert(
                ignore_permissions=True
            ).name
        return p

    # --- list-query scoping (the F-01 / F-08 leak) -----------------------------

    def test_vehicle_query_scoped_for_supervisor(self):
        frag = salis_vehicle_query(self.sup)
        self.assertIn("project", frag)
        self.assertIn(self.pa, frag)

    def test_vehicle_query_open_for_oversight(self):
        self.assertEqual(salis_vehicle_query(self.mgr), "")

    def test_driver_query_preserves_self_profile(self):
        # Scoped supervisor: project scope OR owner, so the if_owner self row survives.
        frag = salis_driver_query(self.sup)
        self.assertIn("owner", frag)
        self.assertIn(self.pa, frag)
        # A Driver with no project grant sees ONLY their own row (owner; no project list).
        drv_frag = salis_driver_query(self.drv)
        self.assertIn("owner", drv_frag)
        self.assertNotIn(self.pa, drv_frag)
        # Oversight: no restriction.
        self.assertEqual(salis_driver_query(self.mgr), "")

    def test_manifest_query_scoped_for_supervisor(self):
        self.assertNotEqual(passenger_manifest_query(self.sup).strip(), "")
        self.assertEqual(passenger_manifest_query(self.mgr), "")

    def test_trip_start_log_query_preserves_self_records(self):
        # M-4: a scoped supervisor sees project-in-scope OR their own logs.
        frag = trip_start_log_query(self.sup)
        self.assertIn("owner", frag)
        self.assertIn("route_plan", frag)
        self.assertIn(self.pa, frag)
        # A Driver with no project grant sees ONLY their own logs (owner; no project).
        drv_frag = trip_start_log_query(self.drv)
        self.assertIn("owner", drv_frag)
        self.assertNotIn("route_plan", drv_frag)
        self.assertNotIn(self.pa, drv_frag)
        # Oversight: no restriction.
        self.assertEqual(trip_start_log_query(self.mgr), "")

    def test_trip_start_log_has_permission_owner_and_scope(self):
        # M-4: the owner-aware hook never blocks a Driver from their own log,
        # mirrors project scope otherwise, and defers entirely for oversight.
        own = frappe._dict(
            {"doctype": "Trip Start Log", "owner": self.drv, "route_plan": None}
        )
        self.assertIsNone(
            trip_start_log_has_permission(own, "write", user=self.drv)
        )
        # A non-owned, project-less log is invisible to a scoped user.
        foreign = frappe._dict(
            {"doctype": "Trip Start Log", "owner": "someone@example.com", "route_plan": None}
        )
        self.assertFalse(
            trip_start_log_has_permission(foreign, "read", user=self.sup)
        )
        # Oversight defers regardless.
        self.assertIsNone(
            trip_start_log_has_permission(foreign, "read", user=self.mgr)
        )

    # --- per-doc has_permission for Salis Vehicle ------------------------------

    def test_vehicle_has_permission(self):
        v_in = frappe._dict({"doctype": "Salis Vehicle", "project": self.pa})
        v_out = frappe._dict({"doctype": "Salis Vehicle", "project": "NO-SUCH-PROJECT"})
        self.assertIsNone(scoped_has_permission(v_in, "read", user=self.sup))
        self.assertFalse(scoped_has_permission(v_out, "read", user=self.sup))
        self.assertIsNone(scoped_has_permission(v_out, "read", user=self.mgr))
