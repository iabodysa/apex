# Copyright (c) 2026, afmcoltd

"""A portal capacity's User is never a desk user.

``driver@apex.internal`` and ``worker@apex.internal`` are the two shared identities
every driver's and every worker's portal write runs under (see the module docstring in
``portal_identity.py`` for why there is no per-person User). Their ``user_type`` is
what ``frappe/www/app.py:25`` reads to decide whether ``/app`` opens, and that field is
computed from the ``desk_access`` of the roles the user holds -- so the invariant under
test is not either role directly, it is the identity those roles' flags ultimately gate.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.utils.portal_identity import (
    CAPACITY_USERS,
    DRIVER,
    WORKER,
    close_all_capacity_desk_access,
    close_capacity_desk_access,
)
from apex.tests.factories import default_company, make_employee

DRIVER_CAPACITY_ROLE = "Portal Driver Capacity"
WORKER_CAPACITY_ROLE = "Portal Worker Capacity"


class TestDriverCapacityHasNoDeskAccess(FrappeTestCase):
    """Corrupts a role the way ``DocType.make_module_and_roles`` does, then proves
    the shared driver identity is not left as a desk user."""

    def tearDown(self):
        close_capacity_desk_access(DRIVER)

    def test_close_capacity_desk_access_corrects_a_hardcoded_role(self):
        frappe.db.set_value("Role", DRIVER_CAPACITY_ROLE, "desk_access", 1, update_modified=False)
        close_capacity_desk_access(DRIVER)
        self.assertEqual(frappe.db.get_value("Role", DRIVER, "desk_access"), 0)
        self.assertEqual(frappe.db.get_value("Role", DRIVER_CAPACITY_ROLE, "desk_access"), 0)
        self.assertEqual(
            frappe.db.get_value("User", CAPACITY_USERS[DRIVER], "user_type"), "Website User"
        )

    def test_a_driver_write_self_heals_the_capacity_users_type(self):
        """The invariant this ships to prove: a driver's User is not a desk user."""
        frappe.db.set_value("Role", DRIVER_CAPACITY_ROLE, "desk_access", 1, update_modified=False)
        driver = frappe.get_doc(
            {
                "doctype": "Salis Driver",
                "naming_series": "DRV-.######",
                "full_name": "_Test Portal Driver",
            }
        ).insert(ignore_permissions=True)
        self.addCleanup(
            lambda: frappe.delete_doc(
                "Salis Driver", driver.name, ignore_permissions=True, force=True
            )
        )
        self.assertEqual(frappe.db.get_value("Role", DRIVER_CAPACITY_ROLE, "desk_access"), 0)
        self.assertEqual(
            frappe.db.get_value("User", CAPACITY_USERS[DRIVER], "user_type"), "Website User"
        )

    def test_an_already_correct_role_is_left_alone(self):
        """No write happens when nothing is broken -- ``close_capacity_desk_access``
        reads before it writes, so a healthy site pays one query and nothing else."""
        close_capacity_desk_access(DRIVER)
        writes = []
        real_get_doc = frappe.get_doc

        def _tracking_get_doc(*args, **kwargs):
            if args and args[0] == "Role":
                writes.append(args)
            return real_get_doc(*args, **kwargs)

        frappe.get_doc = _tracking_get_doc
        try:
            close_capacity_desk_access(DRIVER)
        finally:
            frappe.get_doc = real_get_doc
        self.assertEqual(writes, [])


class TestWorkerCapacityHasNoDeskAccess(FrappeTestCase):
    """The Worker mirror of :class:`TestDriverCapacityHasNoDeskAccess` -- same
    mechanism, same primitive, the other capacity role pair."""

    def tearDown(self):
        close_capacity_desk_access(WORKER)

    def test_close_capacity_desk_access_corrects_a_hardcoded_role(self):
        frappe.db.set_value("Role", WORKER_CAPACITY_ROLE, "desk_access", 1, update_modified=False)
        close_capacity_desk_access(WORKER)
        self.assertEqual(frappe.db.get_value("Role", WORKER, "desk_access"), 0)
        self.assertEqual(frappe.db.get_value("Role", WORKER_CAPACITY_ROLE, "desk_access"), 0)
        self.assertEqual(
            frappe.db.get_value("User", CAPACITY_USERS[WORKER], "user_type"), "Website User"
        )

    def test_an_employee_write_self_heals_the_capacity_users_type(self):
        """The invariant this ships to prove: a worker's User is not a desk user."""
        frappe.db.set_value("Role", WORKER_CAPACITY_ROLE, "desk_access", 1, update_modified=False)
        employee = make_employee(name="_Test Portal Worker", company=default_company())
        self.addCleanup(
            lambda: frappe.delete_doc(
                "Employee", employee.name, ignore_permissions=True, force=True
            )
        )
        self.assertEqual(frappe.db.get_value("Role", WORKER_CAPACITY_ROLE, "desk_access"), 0)
        self.assertEqual(
            frappe.db.get_value("User", CAPACITY_USERS[WORKER], "user_type"), "Website User"
        )

    def test_an_already_correct_role_is_left_alone(self):
        """No write happens when nothing is broken -- ``close_capacity_desk_access``
        reads before it writes, so a healthy site pays one query and nothing else."""
        close_capacity_desk_access(WORKER)
        writes = []
        real_get_doc = frappe.get_doc

        def _tracking_get_doc(*args, **kwargs):
            if args and args[0] == "Role":
                writes.append(args)
            return real_get_doc(*args, **kwargs)

        frappe.get_doc = _tracking_get_doc
        try:
            close_capacity_desk_access(WORKER)
        finally:
            frappe.get_doc = real_get_doc
        self.assertEqual(writes, [])


class TestCloseAllCapacityDeskAccess(FrappeTestCase):
    """The single ``after_migrate`` entry point -- both capacities, one call."""

    def tearDown(self):
        close_all_capacity_desk_access()

    def test_sweeps_both_capacities_in_one_call(self):
        frappe.db.set_value("Role", DRIVER_CAPACITY_ROLE, "desk_access", 1, update_modified=False)
        frappe.db.set_value("Role", WORKER_CAPACITY_ROLE, "desk_access", 1, update_modified=False)
        close_all_capacity_desk_access()
        self.assertEqual(frappe.db.get_value("Role", DRIVER_CAPACITY_ROLE, "desk_access"), 0)
        self.assertEqual(frappe.db.get_value("Role", WORKER_CAPACITY_ROLE, "desk_access"), 0)
        self.assertEqual(
            frappe.db.get_value("User", CAPACITY_USERS[DRIVER], "user_type"), "Website User"
        )
        self.assertEqual(
            frappe.db.get_value("User", CAPACITY_USERS[WORKER], "user_type"), "Website User"
        )
