# Copyright (c) 2026, AFMCO and contributors
"""F-01 / F-08 row-scoping for Salis Vehicle, Salis Driver and Passenger Manifest.

Closes the desk-list enumeration leak (a scoped Fleet Supervisor could list every
project's vehicles/drivers/manifests at /app/salis-vehicle etc.), while preserving
the Driver `if_owner` self-profile (a Driver still sees their own row).

``project_scope_query`` renders the fragment for the DocType named in ``doctype``
— the keyword ``frappe`` itself passes — and ``project_scoped_has_permission``
routes the document check on ``doc.doctype``. Both read the same ``SALIS_SCOPE``
row, so the fragment and the check cannot disagree about what is in scope."""


import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.permissions import (
    project_scope_query,
    project_scoped_has_permission,
    scoped_has_permission,
)
from apex.tests._helpers import _user
from apex.tests.factories import make_project


class TestSalisFleetScoping(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.pa = make_project("Fleet Scope A")
        cls.sup = _user("fleet_sup@example.com", "Fleet Supervisor")
        cls.mgr = _user("fleet_mgr@example.com", "Fleet Manager")
        cls.drv = _user("fleet_drv@example.com", "Driver")
        if not frappe.db.exists(
            "User Permission", {"allow": "Project", "for_value": cls.pa, "user": cls.sup}
        ):
            frappe.get_doc(
                {"doctype": "User Permission", "allow": "Project", "for_value": cls.pa, "user": cls.sup}
            ).insert(ignore_permissions=True)

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        frappe.db.delete("User Permission",
                         {"allow": "Project", "for_value": cls.pa, "user": cls.sup})
        if frappe.db.exists("Project", cls.pa):
            frappe.delete_doc("Project", cls.pa, ignore_permissions=True, force=True)
        frappe.db.commit()
        super().tearDownClass()


    def test_vehicle_query_scoped_for_supervisor(self):
        frag = project_scope_query(self.sup, doctype="Salis Vehicle")
        self.assertIn("project", frag)
        self.assertIn(self.pa, frag)

    def test_vehicle_query_open_for_oversight(self):
        self.assertEqual(project_scope_query(self.mgr, doctype="Salis Vehicle"), "")

    def test_driver_query_preserves_self_profile(self):
        frag = project_scope_query(self.sup, doctype="Salis Driver")
        self.assertIn("owner", frag)
        self.assertIn(self.pa, frag)
        drv_frag = project_scope_query(self.drv, doctype="Salis Driver")
        self.assertIn("owner", drv_frag)
        self.assertNotIn(self.pa, drv_frag)
        self.assertEqual(project_scope_query(self.mgr, doctype="Salis Driver"), "")

    def test_manifest_query_scoped_for_supervisor(self):
        self.assertNotEqual(
            project_scope_query(self.sup, doctype="Passenger Manifest").strip(), ""
        )
        self.assertEqual(project_scope_query(self.mgr, doctype="Passenger Manifest"), "")

    def test_trip_start_log_query_preserves_self_records(self):
        frag = project_scope_query(self.sup, doctype="Trip Start Log")
        self.assertIn("owner", frag)
        self.assertIn("route_plan", frag)
        self.assertIn(self.pa, frag)
        drv_frag = project_scope_query(self.drv, doctype="Trip Start Log")
        self.assertIn("owner", drv_frag)
        self.assertNotIn("route_plan", drv_frag)
        self.assertNotIn(self.pa, drv_frag)
        self.assertEqual(project_scope_query(self.mgr, doctype="Trip Start Log"), "")

    def test_trip_start_log_has_permission_owner_and_scope(self):
        own = frappe._dict(
            {"doctype": "Trip Start Log", "owner": self.drv, "route_plan": None}
        )
        self.assertIsNone(
            project_scoped_has_permission(own, "write", user=self.drv)
        )
        foreign = frappe._dict(
            {"doctype": "Trip Start Log", "owner": "someone@example.com", "route_plan": None}
        )
        self.assertFalse(
            project_scoped_has_permission(foreign, "read", user=self.sup)
        )
        self.assertIsNone(
            project_scoped_has_permission(foreign, "read", user=self.mgr)
        )


    def test_vehicle_has_permission(self):
        v_in = frappe._dict({"doctype": "Salis Vehicle", "project": self.pa})
        v_out = frappe._dict({"doctype": "Salis Vehicle", "project": "NO-SUCH-PROJECT"})
        self.assertIsNone(scoped_has_permission(v_in, "read", user=self.sup))
        self.assertFalse(scoped_has_permission(v_out, "read", user=self.sup))
        self.assertIsNone(scoped_has_permission(v_out, "read", user=self.mgr))
