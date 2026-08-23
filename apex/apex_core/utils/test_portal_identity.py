# Copyright (c) 2026, afmcoltd

"""The driver capacity user is never a desk user.

``driver@apex.internal`` is the one shared identity every driver's portal write runs
under (see the module docstring in ``portal_identity.py`` for why there is no
per-driver User). Its ``user_type`` is what ``frappe/www/app.py:25`` reads to decide
whether ``/app`` opens, and that field is computed from the ``desk_access`` of the
roles the user holds -- so the invariant under test is not the Driver role directly,
it is the identity that role's flag ultimately gates.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.utils.portal_identity import (
    CAPACITY_USERS,
    DRIVER,
    close_driver_desk_access,
)

DRIVER_CAPACITY_ROLE = "Portal Driver Capacity"


class TestDriverCapacityHasNoDeskAccess(FrappeTestCase):
    """Corrupts a role the way ``DocType.make_module_and_roles`` does, then proves
    the shared driver identity is not left as a desk user."""

    def tearDown(self):
        close_driver_desk_access()

    def test_close_driver_desk_access_corrects_a_hardcoded_role(self):
        frappe.db.set_value("Role", DRIVER_CAPACITY_ROLE, "desk_access", 1, update_modified=False)
        close_driver_desk_access()
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
        """No write happens when nothing is broken -- ``close_driver_desk_access``
        reads before it writes, so a healthy site pays one query and nothing else."""
        writes = []
        real_get_doc = frappe.get_doc

        def _tracking_get_doc(*args, **kwargs):
            if args and args[0] == "Role":
                writes.append(args)
            return real_get_doc(*args, **kwargs)

        frappe.get_doc = _tracking_get_doc
        try:
            close_driver_desk_access()
        finally:
            frappe.get_doc = real_get_doc
        self.assertEqual(writes, [])
