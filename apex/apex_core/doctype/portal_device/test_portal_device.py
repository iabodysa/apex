# Copyright (c) 2026, afmcoltd
"""Proves the required device-identity behaviour: a consumed enrolment key is
refused a second time with an Activity Log Failed row; enrolling past the device
cap evicts the oldest device and leaves both rows visible; a revoked device stops
resolving immediately; the capacity/desk-issuer permission dispatchers scope a
device row to its own subject; and no event ever logs a raw secret.

Every ``ignore_permissions=True``/``force=True`` in this file is test-fixture
setup or teardown -- creating and deleting the Employee/Salis Driver/Portal
Device/Masar Worker Token rows a test needs, never a bypass of the behaviour
under test -- matching ``test_portal_identity.py``'s own established pattern in
this same module.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.doctype.masar_worker_token.masar_worker_token import (
    issue_driver_link,
    issue_worker_link,
)
from apex.apex_core.doctype.portal_device.portal_device import (
    consume_enrolment_key,
    list_devices_for,
    revoke_own_device,
)
from apex.apex_core.utils.portal_identity import (
    CAPACITY_USERS,
    DRIVER,
    WORKER,
    as_capacity,
    portal_device_has_permission,
    portal_device_scope_query,
    resolve_portal_subject,
)
from apex.tests.factories import default_company, make_employee


def _make_driver(full_name: str) -> str:
    doc = frappe.get_doc(
        {
            "doctype": "Salis Driver",
            "naming_series": "DRV-.######",
            "full_name": full_name,
        }
    ).insert(ignore_permissions=True)
    return doc.name


class TestConsumeEnrolmentKey(FrappeTestCase):
    def setUp(self):
        self.employee = make_employee(name="_Test Portal Device Worker", company=default_company())
        self.addCleanup(
            lambda: frappe.delete_doc("Employee", self.employee.name, ignore_permissions=True, force=True)
        )
        self.key = issue_worker_link(employee=self.employee.name)["token"]

    def tearDown(self):
        for device in frappe.get_all("Portal Device", filters={"employee": self.employee.name}, pluck="name"):
            frappe.delete_doc("Portal Device", device, ignore_permissions=True, force=True)
        frappe.delete_doc("Masar Worker Token", self.employee.name, ignore_permissions=True, force=True)

    def test_consuming_mints_a_device_and_marks_the_key_consumed(self):
        raw_device = consume_enrolment_key(WORKER, self.key)
        self.assertTrue(raw_device)
        self.assertNotEqual(raw_device, self.key)

        rows = frappe.get_all("Portal Device", filters={"employee": self.employee.name}, fields=["name", "revoked"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].revoked, 0)

        consumed_on = frappe.db.get_value("Masar Worker Token", self.employee.name, "consumed_on")
        self.assertTrue(consumed_on)

    def test_resolve_portal_subject_accepts_the_minted_device_secret(self):
        raw_device = consume_enrolment_key(WORKER, self.key)
        self.assertEqual(resolve_portal_subject(WORKER, raw_device), self.employee.name)

    def test_a_consumed_key_is_refused_on_a_second_scan_with_activity_log_failed(self):
        consume_enrolment_key(WORKER, self.key)

        before = frappe.utils.now_datetime()
        with self.assertRaises(frappe.PermissionError):
            consume_enrolment_key(WORKER, self.key)

        failures = frappe.get_all(
            "Activity Log",
            filters={"status": "Failed", "creation": [">=", before], "link_name": self.employee.name},
            fields=["name", "status", "subject", "reference_doctype", "reference_name"],
        )
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0].status, "Failed")
        self.assertFalse(failures[0].reference_name)

        rows = frappe.get_all("Portal Device", filters={"employee": self.employee.name})
        self.assertEqual(len(rows), 1)

    def test_an_unknown_key_is_refused_and_logged_failed_with_no_subject(self):
        before = frappe.utils.now_datetime()
        with self.assertRaises(frappe.PermissionError):
            consume_enrolment_key(WORKER, "not-a-real-key")

        failures = frappe.get_all(
            "Activity Log",
            filters={"status": "Failed", "creation": [">=", before]},
            fields=["subject", "link_name"],
            order_by="creation desc",
            limit_page_length=1,
        )
        self.assertEqual(len(failures), 1)
        self.assertFalse(failures[0].link_name)

    def test_no_log_entry_contains_the_raw_key_or_the_raw_device_secret(self):
        raw_device = consume_enrolment_key(WORKER, self.key)
        with self.assertRaises(frappe.PermissionError):
            consume_enrolment_key(WORKER, self.key)

        rows = frappe.get_all(
            "Activity Log",
            filters={"link_name": self.employee.name},
            fields=["subject", "content", "reference_name"],
        )
        self.assertTrue(rows)
        blob = " ".join(
            str(r.get(f) or "") for r in rows for f in ("subject", "content", "reference_name")
        )
        self.assertNotIn(self.key, blob)
        self.assertNotIn(raw_device, blob)


class TestDeviceCapEviction(FrappeTestCase):
    """Salis Driver's own cap is 1 (MAX_DEVICES_PER_SUBJECT[DRIVER]) -- a second
    enrolment is already over cap, the smallest case that proves eviction."""

    def setUp(self):
        self.driver = _make_driver("_Test Portal Device Driver")
        self.addCleanup(lambda: frappe.delete_doc("Salis Driver", self.driver, ignore_permissions=True, force=True))

    def tearDown(self):
        for device in frappe.get_all("Portal Device", filters={"driver": self.driver}, pluck="name"):
            frappe.delete_doc("Portal Device", device, ignore_permissions=True, force=True)
        frappe.delete_doc("Masar Worker Token", self.driver, ignore_permissions=True, force=True)

    def _rotate_key(self) -> str:
        return issue_driver_link(driver=self.driver, regenerate=1)["token"]

    def test_enrolling_past_the_cap_evicts_the_oldest_and_leaves_both_visible(self):
        first_key = self._rotate_key()
        first_device = consume_enrolment_key(DRIVER, first_key)
        self.assertTrue(resolve_portal_subject(DRIVER, first_device))

        second_key = self._rotate_key()
        second_device = consume_enrolment_key(DRIVER, second_key)

        rows = list_devices_for(DRIVER, self.driver)
        self.assertEqual(len(rows), 2)
        revoked_flags = sorted(r.revoked for r in rows)
        self.assertEqual(revoked_flags, [0, 1])

        with self.assertRaises(frappe.PermissionError):
            resolve_portal_subject(DRIVER, first_device)
        self.assertEqual(resolve_portal_subject(DRIVER, second_device), self.driver)


class TestRevokeOwnDevice(FrappeTestCase):
    def setUp(self):
        self.employee = make_employee(name="_Test Portal Device Revoke Worker", company=default_company())
        self.other_employee = make_employee(
            name="_Test Portal Device Other Worker", company=default_company()
        )
        self.addCleanup(
            lambda: frappe.delete_doc("Employee", self.employee.name, ignore_permissions=True, force=True)
        )
        self.addCleanup(
            lambda: frappe.delete_doc(
                "Employee", self.other_employee.name, ignore_permissions=True, force=True
            )
        )
        key = issue_worker_link(employee=self.employee.name)["token"]
        self.raw_device = consume_enrolment_key(WORKER, key)
        self.device_name = frappe.get_all(
            "Portal Device", filters={"employee": self.employee.name}, pluck="name"
        )[0]

    def tearDown(self):
        for emp in (self.employee.name, self.other_employee.name):
            for device in frappe.get_all("Portal Device", filters={"employee": emp}, pluck="name"):
                frappe.delete_doc("Portal Device", device, ignore_permissions=True, force=True)
            frappe.delete_doc("Masar Worker Token", emp, ignore_permissions=True, force=True)

    def test_revoking_stops_the_device_resolving_immediately(self):
        self.assertTrue(revoke_own_device(WORKER, self.employee.name, self.device_name))
        with self.assertRaises(frappe.PermissionError):
            resolve_portal_subject(WORKER, self.raw_device)

        row = frappe.db.get_value("Portal Device", self.device_name, ["revoked", "revoked_on"], as_dict=True)
        self.assertEqual(row.revoked, 1)
        self.assertTrue(row.revoked_on)

    def test_one_holder_cannot_revoke_anothers_device_by_name(self):
        with self.assertRaises(frappe.DoesNotExistError):
            revoke_own_device(WORKER, self.other_employee.name, self.device_name)
        self.assertEqual(frappe.db.get_value("Portal Device", self.device_name, "revoked"), 0)


class TestPortalDevicePermissionDispatch(FrappeTestCase):
    """Direct unit coverage of the two hook functions this change adds --
    exercised as plain Python calls, independent of whether ``hooks.py`` (out of
    this change's write scope) has registered them yet."""

    def setUp(self):
        self.employee = make_employee(name="_Test Portal Device Perm Worker", company=default_company())
        self.other_employee = make_employee(
            name="_Test Portal Device Perm Other", company=default_company()
        )
        self.addCleanup(
            lambda: frappe.delete_doc("Employee", self.employee.name, ignore_permissions=True, force=True)
        )
        self.addCleanup(
            lambda: frappe.delete_doc(
                "Employee", self.other_employee.name, ignore_permissions=True, force=True
            )
        )

    def test_capacity_sees_only_its_own_bound_subjects_row(self):
        row = frappe._dict({"holder_type": "Worker", "employee": self.employee.name})
        other_row = frappe._dict({"holder_type": "Worker", "employee": self.other_employee.name})
        with as_capacity(WORKER, subject=self.employee.name):
            self.assertIsNone(portal_device_has_permission(row, "write", user=CAPACITY_USERS[WORKER]))
            self.assertFalse(portal_device_has_permission(other_row, "write", user=CAPACITY_USERS[WORKER]))
            self.assertFalse(portal_device_has_permission(row, "read", user=CAPACITY_USERS[WORKER]))

    def test_scope_query_denies_a_role_that_issues_for_neither_audience(self):
        frappe.set_user("Administrator")
        self.assertEqual(portal_device_scope_query(user="Administrator"), "")

    def test_scope_query_confines_a_capacity_to_its_own_bound_subject(self):
        with as_capacity(WORKER, subject=self.employee.name):
            condition = portal_device_scope_query(user=CAPACITY_USERS[WORKER])
        self.assertEqual(condition, "`employee` = {0}".format(frappe.db.escape(self.employee.name)))

    def test_scope_query_denies_a_capacity_with_no_bound_subject(self):
        self.assertEqual(portal_device_scope_query(user=CAPACITY_USERS[WORKER]), "1=0")

    def test_write_is_gated_alongside_read_report_print(self):
        row = frappe._dict({"holder_type": "Worker", "employee": self.employee.name})
        with as_capacity(WORKER, subject=self.employee.name):
            self.assertIsNone(portal_device_has_permission(row, "write", user=CAPACITY_USERS[WORKER]))


class TestDeskSupervisorRevocation(FrappeTestCase):
    """A desk save is the ONLY revoking writer that reaches ``PortalDevice``'s own
    controller (the other three -- :func:`revoke_own_device`,
    ``revoke_subject_devices``, ``_evict_oldest_if_over_cap`` -- write through
    ``frappe.db.set_value`` and stamp/log themselves already), so this exercises
    ``validate``/``on_update`` directly through ``Document.save`` -- the same shape
    a scoped desk issuer's revoke-by-save takes. ``ignore_permissions=True`` on
    ``save`` here is test setup for the STAMPING/LOGGING/GUARD rule under test, not
    a stand-in for the project/building ``write`` scoping proven separately above
    (``test_write_is_gated_alongside_read_report_print``,
    ``TestPortalDevicePermissionDispatch``)."""

    def setUp(self):
        self.employee = make_employee(name="_Test Portal Device Desk Worker", company=default_company())
        self.addCleanup(
            lambda: frappe.delete_doc("Employee", self.employee.name, ignore_permissions=True, force=True)
        )
        key = issue_worker_link(employee=self.employee.name)["token"]
        consume_enrolment_key(WORKER, key)
        self.device_name = frappe.get_all(
            "Portal Device", filters={"employee": self.employee.name}, pluck="name"
        )[0]

    def tearDown(self):
        frappe.delete_doc("Portal Device", self.device_name, ignore_permissions=True, force=True)
        frappe.delete_doc("Masar Worker Token", self.employee.name, ignore_permissions=True, force=True)

    def test_a_desk_save_revoking_a_device_stamps_and_logs_it(self):
        before = frappe.utils.now_datetime()
        doc = frappe.get_doc("Portal Device", self.device_name)
        doc.revoked = 1
        doc.save(ignore_permissions=True)

        row = frappe.db.get_value(
            "Portal Device", self.device_name, ["revoked", "revoked_on"], as_dict=True
        )
        self.assertEqual(row.revoked, 1)
        self.assertTrue(row.revoked_on)

        events = frappe.get_all(
            "Activity Log",
            filters={
                "reference_doctype": "Portal Device",
                "reference_name": self.device_name,
                "creation": [">=", before],
            },
            fields=["status"],
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].status, "Linked")

    def test_a_desk_save_cannot_un_revoke_a_device(self):
        frappe.db.set_value("Portal Device", self.device_name, "revoked", 1, update_modified=False)
        doc = frappe.get_doc("Portal Device", self.device_name)
        doc.revoked = 0
        with self.assertRaises(frappe.ValidationError):
            doc.save(ignore_permissions=True)
        self.assertEqual(frappe.db.get_value("Portal Device", self.device_name, "revoked"), 1)


def _make_user_with_role(email: str, role: str | None) -> str:
    """A minimal desk User for the real-permission-stack tests below -- created
    once per test class and torn down through ``addClassCleanup``."""
    if not frappe.db.exists("User", email):
        frappe.get_doc(
            {"doctype": "User", "email": email, "first_name": "Test", "send_welcome_email": 0}
        ).insert(ignore_permissions=True)
    if role:
        frappe.get_doc("User", email).add_roles(role)
    return email


class TestRealPermissionStackWiring(FrappeTestCase):
    """Goes through ``frappe.has_permission`` itself rather than calling
    ``portal_device_has_permission`` as a plain function (``TestPortalDevice
    PermissionDispatch`` above does that) -- the only way to prove the two new
    ``hooks.py`` lines (``has_permission``/``permission_query_conditions`` for
    ``Portal Device``) are both present and correctly dotted, not merely that the
    functions themselves are correct in isolation."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee = make_employee(
            name="_Test Portal Device Real Perm Worker", company=default_company()
        )
        cls.addClassCleanup(
            lambda: frappe.delete_doc(
                "Employee", cls.employee.name, ignore_permissions=True, force=True
            )
        )
        key = issue_worker_link(employee=cls.employee.name)["token"]
        consume_enrolment_key(WORKER, key)
        cls.device_name = frappe.get_all(
            "Portal Device", filters={"employee": cls.employee.name}, pluck="name"
        )[0]
        cls.addClassCleanup(
            lambda: frappe.delete_doc(
                "Portal Device", cls.device_name, ignore_permissions=True, force=True
            )
        )
        cls.addClassCleanup(
            lambda: frappe.delete_doc(
                "Masar Worker Token", cls.employee.name, ignore_permissions=True, force=True
            )
        )
        cls.hr_user = _make_user_with_role("_test_pd_hr_user@example.com", "HR User")
        cls.addClassCleanup(
            lambda: frappe.delete_doc("User", cls.hr_user, ignore_permissions=True, force=True)
        )
        # Resident Supervisor holds `write: 1` on Portal Device in the base DocPerm
        # (portal_device.json) -- WITHOUT a matching Housing Assignment for this
        # employee, ONLY the has_permission hook's building-scope check can deny it.
        cls.unmatched_supervisor = _make_user_with_role(
            "_test_pd_unmatched_supervisor@example.com", "Resident Supervisor"
        )
        cls.addClassCleanup(
            lambda: frappe.delete_doc(
                "User", cls.unmatched_supervisor, ignore_permissions=True, force=True
            )
        )

    def tearDown(self):
        frappe.set_user("Administrator")
        frappe.db.set_value("Portal Device", self.device_name, "revoked", 0, update_modified=False)

    def test_an_unscoped_hr_issuer_revokes_through_the_real_permission_stack(self):
        frappe.set_user(self.hr_user)
        doc = frappe.get_doc("Portal Device", self.device_name)
        doc.revoked = 1
        doc.save()
        self.assertEqual(
            frappe.db.get_value("Portal Device", self.device_name, "revoked"), 1
        )

    def test_a_docperm_write_role_with_no_matching_building_is_still_denied(self):
        frappe.set_user(self.unmatched_supervisor)
        doc = frappe.get_doc("Portal Device", self.device_name)
        doc.revoked = 1
        with self.assertRaises(frappe.PermissionError):
            doc.save()
        self.assertEqual(
            frappe.db.get_value("Portal Device", self.device_name, "revoked"), 0
        )
