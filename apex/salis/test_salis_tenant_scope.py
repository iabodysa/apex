# Copyright (c) 2026, AFMCO and contributors
"""Project row-scoping for the Salis indirect-tenant DocTypes.

These DocTypes carry no own ``project`` field; they reach their tenant through a
Salis Driver link (``driver`` / ``related_driver`` -> Salis Driver -> project) or,
for Movement Cost Transfer, through two direct project Links (``from_project`` /
``to_project``). Before this pass a Fleet Supervisor scoped to one project could
enumerate every project's driver attendance, stops, boarding scans, incidents,
write-offs, clearances, vehicle stops and cost transfers in the list/report view
and open them directly — a cross-project PII / disciplinary leak.

Each test proves: a Fleet Supervisor scoped to Project A sees zero rows resolving
to Project B (the generated query fragment, run as a real subquery, excludes B's
driver, and the has_permission hook denies a B-resolved doc); oversight roles are
unaffected (empty fragment / deferred hook); and the Driver if_owner self-record
path still returns the driver's own rows where such a DocPerm exists.
"""


import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.permissions import (
    boarding_scan_log_has_permission,
    boarding_scan_log_query,
    driver_attendance_has_permission,
    driver_attendance_query,
    driver_clearance_has_permission,
    driver_clearance_query,
    driver_stop_has_permission,
    driver_stop_query,
    movement_cost_transfer_has_permission,
    movement_cost_transfer_query,
    vehicle_damage_write_off_has_permission,
    vehicle_damage_write_off_query,
    vehicle_incident_has_permission,
    vehicle_incident_query,
    vehicle_stop_has_permission,
    vehicle_stop_query,
)
from apex.tests._helpers import _user


class TestSalisTenantScope(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.pa = cls._project("Tenant Scope A")
        cls.pb = cls._project("Tenant Scope B")
        cls.sup = _user("tenant_sup@example.com", "Fleet Supervisor")
        cls.mgr = _user("tenant_mgr@example.com", "Fleet Manager")  # [#dpuh30]
        cls.drv = _user("tenant_drv@example.com", "Driver")
        cls._user_perm(cls.sup, cls.pa)
        # [#d5aiv0]
        cls.drv_a = cls._driver("Tenant Driver A", cls.pa)
        cls.drv_b = cls._driver("Tenant Driver B", cls.pb)

    @classmethod
    def tearDownClass(cls):
        # [#di2n48]
        frappe.set_user("Administrator")
        frappe.db.delete("User Permission",
                         {"allow": "Project", "for_value": cls.pa, "user": cls.sup})
        for d in (cls.drv_a, cls.drv_b):
            if frappe.db.exists("Salis Driver", d):
                frappe.delete_doc("Salis Driver", d, ignore_permissions=True, force=True)
        for p in (cls.pa, cls.pb):
            if frappe.db.exists("Project", p):
                frappe.delete_doc("Project", p, ignore_permissions=True, force=True)
        frappe.db.commit()
        super().tearDownClass()

    # [#kjq1ae]

    @staticmethod
    def _project(name):
        p = frappe.db.get_value("Project", {"project_name": name}, "name")
        if not p:
            p = (
                frappe.get_doc({"doctype": "Project", "project_name": name})
                .insert(ignore_permissions=True)
                .name
            )
        return p

    @staticmethod
    def _user_perm(user, project):
        if not frappe.db.exists(
            "User Permission",
            {"allow": "Project", "for_value": project, "user": user},
        ):
            frappe.get_doc(
                {
                    "doctype": "User Permission",
                    "allow": "Project",
                    "for_value": project,
                    "user": user,
                }
            ).insert(ignore_permissions=True)

    @staticmethod
    def _driver(full_name, project):
        name = frappe.db.get_value(
            "Salis Driver", {"full_name": full_name}, "name"
        )
        if name:
            return name
        doc = frappe.new_doc("Salis Driver")
        doc.full_name = full_name
        doc.project = project
        # [#1dxhyg]
        doc.flags.ignore_validate = True
        doc.flags.ignore_mandatory = True
        doc.insert(ignore_permissions=True)
        return doc.name

    # [#7i064h]

    def _resolves_to_b(self, fragment, column):
        """True if a row pointing at the Project-B driver passes ``fragment``.

        Runs the generated WHERE fragment as a real query against a one-row table
        carrying the B driver in ``column``; an empty result proves the supervisor
        sees zero rows resolving to Project B.
        """
        col = column.strip("`")
        rows = frappe.db.sql(
            "select 1 from (select %s as `{c}`, %s as `owner`) t where {frag}".format(
                c=col, frag=fragment
            ),
            (self.drv_b, "stranger@example.com"),
        )
        return bool(rows)

    def _resolves_to_a(self, fragment, column):
        col = column.strip("`")
        rows = frappe.db.sql(
            "select 1 from (select %s as `{c}`, %s as `owner`) t where {frag}".format(
                c=col, frag=fragment
            ),
            (self.drv_a, "stranger@example.com"),
        )
        return bool(rows)

    # [#h66stu]

    def test_driver_attendance_query_excludes_other_project(self):
        frag = driver_attendance_query(self.sup)
        self.assertIn(self.pa, frag)
        self.assertNotIn(self.pb, frag)
        self.assertIn("owner", frag)  # [#dtub9p]
        self.assertFalse(self._resolves_to_b(frag, "`driver`"))
        self.assertTrue(self._resolves_to_a(frag, "`driver`"))

    def test_driver_stop_query_excludes_other_project(self):
        frag = driver_stop_query(self.sup)
        self.assertIn(self.pa, frag)
        self.assertNotIn(self.pb, frag)
        self.assertFalse(self._resolves_to_b(frag, "`driver`"))
        self.assertTrue(self._resolves_to_a(frag, "`driver`"))

    def test_boarding_scan_log_query_excludes_other_project(self):
        frag = boarding_scan_log_query(self.sup)
        self.assertIn(self.pa, frag)
        self.assertNotIn(self.pb, frag)
        self.assertFalse(self._resolves_to_b(frag, "`driver`"))
        self.assertTrue(self._resolves_to_a(frag, "`driver`"))

    def test_vehicle_damage_write_off_query_excludes_other_project(self):
        frag = vehicle_damage_write_off_query(self.sup)
        self.assertIn(self.pa, frag)
        self.assertNotIn(self.pb, frag)
        self.assertNotIn("owner", frag)  # [#awgsrs]
        self.assertFalse(self._resolves_to_b(frag, "`driver`"))
        self.assertTrue(self._resolves_to_a(frag, "`driver`"))

    def test_vehicle_incident_query_excludes_other_project(self):
        frag = vehicle_incident_query(self.sup)
        self.assertIn(self.pa, frag)
        self.assertNotIn(self.pb, frag)
        self.assertFalse(self._resolves_to_b(frag, "`driver`"))
        self.assertTrue(self._resolves_to_a(frag, "`driver`"))

    def test_driver_clearance_query_excludes_other_project(self):
        frag = driver_clearance_query(self.sup)
        self.assertIn(self.pa, frag)
        self.assertNotIn(self.pb, frag)
        self.assertFalse(self._resolves_to_b(frag, "`driver`"))
        self.assertTrue(self._resolves_to_a(frag, "`driver`"))

    def test_vehicle_stop_query_excludes_other_project(self):
        frag = vehicle_stop_query(self.sup)
        self.assertIn(self.pa, frag)
        self.assertNotIn(self.pb, frag)
        self.assertIn("related_driver", frag)  # [#piuopr]
        self.assertFalse(self._resolves_to_b(frag, "`related_driver`"))
        self.assertTrue(self._resolves_to_a(frag, "`related_driver`"))

    def test_movement_cost_transfer_query_excludes_other_project(self):
        frag = movement_cost_transfer_query(self.sup)
        self.assertIn(self.pa, frag)
        self.assertNotIn(self.pb, frag)
        # [#91ks9d]
        rows = frappe.db.sql(
            "select 1 from (select %s as `from_project`, %s as `to_project`) t "
            "where {frag}".format(frag=frag),
            (self.pb, self.pb),
        )
        self.assertFalse(bool(rows))
        # [#2114v5]
        rows_a = frappe.db.sql(
            "select 1 from (select %s as `from_project`, %s as `to_project`) t "
            "where {frag}".format(frag=frag),
            (self.pb, self.pa),
        )
        self.assertTrue(bool(rows_a))

    # [#cy09nh]

    def test_oversight_sees_all(self):
        for q in (
            driver_attendance_query,
            driver_stop_query,
            boarding_scan_log_query,
            vehicle_damage_write_off_query,
            vehicle_incident_query,
            driver_clearance_query,
            vehicle_stop_query,
            movement_cost_transfer_query,
        ):
            self.assertEqual(q(self.mgr), "", "%s must not restrict oversight" % q.__name__)

    # [#a8x34i]

    def test_driver_self_record_path_preserved(self):
        # [#305o9b]
        for q in (driver_attendance_query, driver_stop_query, boarding_scan_log_query):
            frag = q(self.drv)
            self.assertIn("owner", frag)
            self.assertNotIn(self.pa, frag)
            self.assertNotIn(self.pb, frag)
            # [#838xys]
            rows = frappe.db.sql(
                "select 1 from (select %s as `driver`, %s as `owner`) t "
                "where {frag}".format(frag=frag),
                (self.drv_b, self.drv),
            )
            self.assertTrue(bool(rows), "%s must keep the driver's own row" % q.__name__)

    # [#3xfstd]

    def test_driver_chain_has_permission_blocks_other_project(self):
        cases = (
            (driver_attendance_has_permission, "driver", True),
            (driver_stop_has_permission, "driver", True),
            (boarding_scan_log_has_permission, "driver", True),
            (vehicle_damage_write_off_has_permission, "driver", False),
            (vehicle_incident_has_permission, "driver", False),
            (driver_clearance_has_permission, "driver", False),
            (vehicle_stop_has_permission, "related_driver", False),
        )
        for fn, field, _owner in cases:
            doc_b = frappe._dict({field: self.drv_b, "owner": "stranger@example.com"})
            self.assertFalse(
                fn(doc_b, "read", user=self.sup),
                "%s must deny a Project-B doc to the scoped supervisor" % fn.__name__,
            )
            doc_a = frappe._dict({field: self.drv_a, "owner": "stranger@example.com"})
            self.assertIsNone(
                fn(doc_a, "read", user=self.sup),
                "%s must allow a Project-A doc to the scoped supervisor" % fn.__name__,
            )
            # [#qf6l1z]
            self.assertIsNone(fn(doc_b, "read", user=self.mgr))

    def test_if_owner_has_permission_keeps_own_row(self):
        # [#mcu2ns]
        for fn in (
            driver_attendance_has_permission,
            driver_stop_has_permission,
            boarding_scan_log_has_permission,
        ):
            own = frappe._dict({"driver": self.drv_b, "owner": self.drv})
            self.assertIsNone(
                fn(own, "read", user=self.drv),
                "%s must keep the Driver's own row" % fn.__name__,
            )

    def test_movement_cost_transfer_has_permission(self):
        # [#24npxl]
        a_in = frappe._dict({"from_project": self.pb, "to_project": self.pa})
        b_only = frappe._dict({"from_project": self.pb, "to_project": self.pb})
        self.assertIsNone(movement_cost_transfer_has_permission(a_in, "read", user=self.sup))
        self.assertFalse(movement_cost_transfer_has_permission(b_only, "read", user=self.sup))
        self.assertIsNone(movement_cost_transfer_has_permission(b_only, "read", user=self.mgr))
