# Copyright (c) 2026, afmcoltd


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


class TestPushSubscriptionListIsShutToACapacity(FrappeTestCase):

    def setUp(self):
        self.employee = make_employee(company=default_company()).name
        self.rows = []
        for endpoint in ("https://fcm.googleapis.com/fcm/send/apex-a", "https://fcm.googleapis.com/fcm/send/apex-b"):
            doc = frappe.get_doc(
                {
                    "doctype": "Portal Push Subscription",
                    "holder_type": "Worker",
                    "employee": self.employee,
                    "endpoint": endpoint,
                    "p256dh": "test-p256dh",
                    "auth": "test-auth",
                }
            ).insert(ignore_permissions=True)
            self.rows.append(doc.name)

    def tearDown(self):
        frappe.set_user("Administrator")
        for name in self.rows:
            frappe.delete_doc(
                "Portal Push Subscription", name, force=True, ignore_permissions=True
            )

    def test_administrator_sees_the_rows_the_capacity_must_not(self):
        listed = {r.name for r in frappe.get_list("Portal Push Subscription", limit_page_length=0)}
        self.assertTrue(set(self.rows).issubset(listed))

    def test_each_capacity_lists_nothing(self):
        for audience in (DRIVER, WORKER):
            frappe.set_user(CAPACITY_USERS[audience])
            listed = frappe.get_list("Portal Push Subscription", limit_page_length=0)
            frappe.set_user("Administrator")
            self.assertEqual(listed, [], f"{CAPACITY_USERS[audience]} listed a push registration")
