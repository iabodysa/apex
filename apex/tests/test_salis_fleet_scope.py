# Copyright (c) 2026, AFMCO and contributors
"""F-01 / F-08 row-scoping for Salis Vehicle, Salis Driver and Passenger Manifest.

Closes the desk-list enumeration leak (a scoped Fleet Supervisor could list every
project's vehicles/drivers/manifests at /app/salis-vehicle etc.), while preserving
the Driver `if_owner` self-profile (a Driver still sees their own row)."""


import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.permissions import (
    passenger_manifest_query,
    salis_driver_query,
    salis_vehicle_query,
    scoped_has_permission,
    trip_start_log_has_permission,
    trip_start_log_query,
)
from apex.tests._helpers import _user


class TestSalisFleetScoping(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.pa = cls._project("Fleet Scope A")
        cls.sup = _user("fleet_sup@example.com", "Fleet Supervisor")   # [#8j7xbz]
        cls.mgr = _user("fleet_mgr@example.com", "Fleet Manager")      # [#11zo7x]
        cls.drv = _user("fleet_drv@example.com", "Driver")             # [#hvm9mm]
        if not frappe.db.exists(
            "User Permission", {"allow": "Project", "for_value": cls.pa, "user": cls.sup}
        ):
            frappe.get_doc(
                {"doctype": "User Permission", "allow": "Project", "for_value": cls.pa, "user": cls.sup}
            ).insert(ignore_permissions=True)

    @classmethod
    def tearDownClass(cls):
        # setUpClass commits a Project + User Permission OUTSIDE FrappeTestCase's
        # per-method savepoint rollback; without this they leak across the test DB
        # (the @example.com Project User Permission cross-test-pollution class).
        frappe.set_user("Administrator")
        frappe.db.delete("User Permission",
                         {"allow": "Project", "for_value": cls.pa, "user": cls.sup})
        if frappe.db.exists("Project", cls.pa):
            frappe.delete_doc("Project", cls.pa, ignore_permissions=True, force=True)
        frappe.db.commit()
        super().tearDownClass()

    @staticmethod
    def _project(name):
        p = frappe.db.get_value("Project", {"project_name": name}, "name")
        if not p:
            p = frappe.get_doc({"doctype": "Project", "project_name": name}).insert(
                ignore_permissions=True
            ).name
        return p

    # [#tlagf1]

    def test_vehicle_query_scoped_for_supervisor(self):
        frag = salis_vehicle_query(self.sup)
        self.assertIn("project", frag)
        self.assertIn(self.pa, frag)

    def test_vehicle_query_open_for_oversight(self):
        self.assertEqual(salis_vehicle_query(self.mgr), "")

    def test_driver_query_preserves_self_profile(self):
        # [#16p2k1]
        frag = salis_driver_query(self.sup)
        self.assertIn("owner", frag)
        self.assertIn(self.pa, frag)
        # [#sxwqtz]
        drv_frag = salis_driver_query(self.drv)
        self.assertIn("owner", drv_frag)
        self.assertNotIn(self.pa, drv_frag)
        # [#iuhzj4]
        self.assertEqual(salis_driver_query(self.mgr), "")

    def test_manifest_query_scoped_for_supervisor(self):
        self.assertNotEqual(passenger_manifest_query(self.sup).strip(), "")
        self.assertEqual(passenger_manifest_query(self.mgr), "")

    def test_trip_start_log_query_preserves_self_records(self):
        # [#a0piq0]
        frag = trip_start_log_query(self.sup)
        self.assertIn("owner", frag)
        self.assertIn("route_plan", frag)
        self.assertIn(self.pa, frag)
        # [#ix7j3f]
        drv_frag = trip_start_log_query(self.drv)
        self.assertIn("owner", drv_frag)
        self.assertNotIn("route_plan", drv_frag)
        self.assertNotIn(self.pa, drv_frag)
        # [#iuhzj4]
        self.assertEqual(trip_start_log_query(self.mgr), "")

    def test_trip_start_log_has_permission_owner_and_scope(self):
        # [#m9kv5z]
        own = frappe._dict(
            {"doctype": "Trip Start Log", "owner": self.drv, "route_plan": None}
        )
        self.assertIsNone(
            trip_start_log_has_permission(own, "write", user=self.drv)
        )
        # [#coluet]
        foreign = frappe._dict(
            {"doctype": "Trip Start Log", "owner": "someone@example.com", "route_plan": None}
        )
        self.assertFalse(
            trip_start_log_has_permission(foreign, "read", user=self.sup)
        )
        # [#5tb95b]
        self.assertIsNone(
            trip_start_log_has_permission(foreign, "read", user=self.mgr)
        )

    # [#qo03wb]

    def test_vehicle_has_permission(self):
        v_in = frappe._dict({"doctype": "Salis Vehicle", "project": self.pa})
        v_out = frappe._dict({"doctype": "Salis Vehicle", "project": "NO-SUCH-PROJECT"})
        self.assertIsNone(scoped_has_permission(v_in, "read", user=self.sup))
        self.assertFalse(scoped_has_permission(v_out, "read", user=self.sup))
        self.assertIsNone(scoped_has_permission(v_out, "read", user=self.mgr))
