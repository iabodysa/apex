# Copyright (c) 2026, AFMCO and contributors
"""Active Resident Register must survive the DESK run path, not only ``execute()``.

Every existing case for this report calls ``active_resident_register.execute()``
directly. That proves the SQL and the building scope, and it can never reach the
step that actually broke the page: ``frappe.desk.query_report.run`` post-processes
the rows through ``get_filtered_data`` (``frappe/desk/query_report.py:110``), which
collects every Link column carrying a value (``get_linked_doctypes``, :824) and asks
``build_match_conditions`` for each linked doctype (:905). That bottoms out in
``frappe/model/db_query.py:1014``, which raises ``No permission to read {0}`` for a
doctype the caller can neither read nor select.

Two properties made the gap invisible. The post-processing runs only ``if result``,
so the report was healthy on an empty site and refused the moment one real row
existed. And the refusal names whichever linked doctype comes first, so fixing one
only moves the 403 to the next: this report's columns name Employee, Project and
Cost Center, and Resident Supervisor — the role the report is published to — could
select none of them.

These cases therefore drive the whitelisted endpoint the Desk itself calls, as the
supervisor, with a row present. ``test_every_link_column_is_selectable`` is the part
that will not accept a one-doctype fix.

Run standalone:
  bench --site <site> run-tests --module apex.habitat.report.test_active_resident_register_desk_run
"""

import unittest

import frappe
from frappe.desk.query_report import run as desk_run
from frappe.tests.utils import FrappeTestCase

from apex.habitat.report.active_resident_register import active_resident_register
from apex.tests._helpers import _user, as_user
from apex.tests.factories import make_assignment, make_project, purge_doc

REPORT = "Active Resident Register"


class TestActiveResidentRegisterDeskRun(FrappeTestCase):
    """The Desk endpoint, as the audience the report is published to, with data."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.tag = frappe.generate_hash(length=12).upper()

        cls.company = frappe.db.get_value("Company", {})
        cost_center = frappe.db.get_value("Cost Center", {"is_group": 0, "company": cls.company})
        cls.site = (
            frappe.get_doc({"doctype": "Site", "site_name": "ARR " + cls.tag})
            .insert(ignore_permissions=True)
            .name
        )
        cls.building = (
            frappe.get_doc(
                {
                    "doctype": "Building",
                    "building_name": "ARR B " + cls.tag,
                    "site": cls.site,
                    "company": cls.company,
                    "total_capacity": 10,
                    "default_cost_center": cost_center,
                    "annual_rent": 36500,
                }
            )
            .insert(ignore_permissions=True)
            .name
        )
        cls.project = make_project("ARR Project " + cls.tag)
        cls.employee = (
            frappe.get_doc(
                {
                    "doctype": "Employee",
                    "employee_name": "ARR Emp " + cls.tag,
                    "first_name": "ARR" + cls.tag,
                    "company": cls.company,
                    "status": "Active",
                    "gender": "Male",
                    "date_of_joining": "2024-01-01",
                    "date_of_birth": "1990-01-01",
                }
            )
            .insert(ignore_permissions=True)
            .name
        )
        cls.assignment = make_assignment(cls.employee, cls.building, cls.project)

        cls.sup = _user("arr_desk_res_sup@example.com", "Resident Supervisor")
        cls.permission = (
            frappe.get_doc(
                {
                    "doctype": "User Permission",
                    "user": cls.sup,
                    "allow": "Building",
                    "for_value": cls.building,
                }
            )
            .insert(ignore_permissions=True)
            .name
        )

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        frappe.delete_doc(
            "User Permission", cls.permission, force=True, ignore_permissions=True
        )
        purge_doc("Housing Assignment", cls.assignment)
        frappe.db.commit()
        super().tearDownClass()

    def tearDown(self):
        frappe.set_user("Administrator")

    def _run_as_supervisor(self):
        frappe.set_user("Administrator")
        frappe.local.cache.pop("apex_allowed_buildings", None)
        with as_user(self.sup):
            frappe.local.cache.pop("apex_allowed_buildings", None)
            return desk_run(REPORT, filters={})

    # [#j03s5a]

    def test_supervisor_runs_the_report_with_data(self):
        """THE DEFECT. One real row used to turn the Desk run into a 403."""
        result = self._run_as_supervisor()
        rows = [r for r in result["result"] if r.get("name") == self.assignment]
        self.assertEqual(len(rows), 1, "the supervisor's own row did not come back")
        self.assertEqual(rows[0]["building"], self.building)

    def test_every_link_column_is_selectable(self):
        """A one-doctype fix is not a fix: ``get_user_match_filters`` walks EVERY Link
        column that carries a value, so the refusal simply moves to the next name.

        Read straight off the report's own column list rather than off a Desk run, so
        this case stays a usable discriminator even while the run is still refusing.
        """
        columns = active_resident_register.execute({})[0]
        linked = {
            col["options"]
            for col in columns
            if col.get("fieldtype") == "Link" and col.get("options")
        }
        self.assertIn("Employee", linked)  # guards against a column being dropped instead
        with as_user(self.sup):
            unreachable = [
                doctype
                for doctype in sorted(linked)
                if not (
                    frappe.has_permission(doctype, "select")
                    or frappe.has_permission(doctype, "read")
                )
            ]
        self.assertEqual(
            unreachable,
            [],
            "these Link columns name doctypes the report's own audience cannot "
            "select, so build_match_conditions will refuse the run",
        )

    def test_an_unscoped_manager_still_runs(self):
        """NEGATIVE CONTROL. The oversight role was never blocked; it must stay that
        way, so a green run above cannot be an artefact of the report going empty."""
        manager = _user("arr_desk_acc_mgr@example.com", "Accommodation Manager")
        with as_user(manager):
            result = desk_run(REPORT, filters={})
        self.assertTrue(
            any(r.get("name") == self.assignment for r in result["result"]),
            "oversight lost sight of the row",
        )


if __name__ == "__main__":
    unittest.main()
