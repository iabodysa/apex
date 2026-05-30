"""Driver portal identity-scope tests: a driver only sees their own data, and a
fuel request without an assigned vehicle is rejected."""

import unittest

import frappe

from apex_habitat.salis.api import driver_portal
from apex_habitat.tests.test_driver_portal import _ensure_test_driver


def _driver_without_vehicle(email):
    if not frappe.db.exists("User", email):
        # Idempotent + resilient to the full-suite isolation race (a sibling class
        # committed this user, leaving the exists() guard above stale).
        try:
            u = frappe.get_doc(
                {"doctype": "User", "email": email, "first_name": "NoVeh", "send_welcome_email": 0}
            )
            u.add_roles("Driver")
            u.insert(ignore_permissions=True)
        except frappe.DuplicateEntryError:
            pass
    emp = frappe.db.get_value("Employee", {"user_id": email}, "name")
    if not emp:
        company = (frappe.defaults.get_global_default("company")
                   or frappe.get_all("Company", limit=1)[0].name)
        emp = frappe.get_doc({"doctype": "Employee", "first_name": "NoVeh", "user_id": email,
                              "date_of_birth": "1990-01-01", "date_of_joining": frappe.utils.today(),
                              "gender": "Male", "company": company}).insert(ignore_permissions=True).name
    drv = frappe.db.get_value("Salis Driver", {"employee": emp}, "name")
    if not drv:
        drv = frappe.get_doc({"doctype": "Salis Driver", "employee": emp,
                              "full_name": "NoVeh", "status": "Active"}).insert(
            ignore_permissions=True).name
    return drv, email


def _ensure_unlinked_user(email):
    """A logged-in user with NO Employee/Salis Driver chain — e.g. an admin
    previewing /driver. The portal must greet them, never 403."""
    if not frappe.db.exists("User", email):
        try:
            frappe.get_doc(
                {"doctype": "User", "email": email, "first_name": "Unlinked", "send_welcome_email": 0}
            ).insert(ignore_permissions=True)
        except frappe.DuplicateEntryError:
            pass
    return email


def _ensure_staff_user(email, role):
    """A logged-in Salis *staff* user (holds a desk role) with NO Salis Driver.
    Opening /driver must give them a useful staff payload, never a dead-end."""
    if not frappe.db.exists("User", email):
        try:
            u = frappe.get_doc(
                {"doctype": "User", "email": email, "first_name": "Staff", "send_welcome_email": 0}
            )
            u.insert(ignore_permissions=True)
        except frappe.DuplicateEntryError:
            pass
    user = frappe.get_doc("User", email)
    if role not in {r.role for r in user.roles}:
        user.add_roles(role)
    return email


class TestDriverPortalScope(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        frappe.db.set_single_value("Salis Settings", "enable_driver_portal", 1)
        cls.driver_a = _ensure_test_driver()
        cls.driver_b, cls.user_b = _driver_without_vehicle("drv_noveh@example.com")
        cls.unlinked_user = _ensure_unlinked_user("drv_unlinked@example.com")
        frappe.db.commit()

    def tearDown(self):
        frappe.set_user("Administrator")

    def test_context_for_unlinked_user_is_friendly(self):
        """Regression (1.0.1): get_driver_context() for a user with no linked
        Salis Driver returns a friendly payload and does NOT raise."""
        frappe.set_user(self.unlinked_user)
        ctx = driver_portal.get_driver_context()
        self.assertTrue(ctx["enabled"])
        self.assertFalse(ctx["linked"])
        self.assertIsNone(ctx["driver"])

    def test_context_for_unlinked_nonstaff_has_no_links(self):
        """A plain logged-in user with no Salis role and no driver gets a friendly
        non-staff payload: not staff, no desk links, and it never raises."""
        frappe.set_user(self.unlinked_user)
        ctx = driver_portal.get_driver_context()
        self.assertFalse(ctx["is_staff"])
        self.assertEqual(ctx["links"], [])
        self.assertIn("full_name", ctx)

    def test_context_for_unlinked_staff_returns_links(self):
        """Expect-the-worst: a Fleet Supervisor with NO Salis Driver opens /driver.
        The bootstrap must NOT raise and must return a useful staff payload —
        is_staff:true plus permission-filtered desk links — so the screen is never
        a dead-end."""
        staff_user = _ensure_staff_user("drv_staff@example.com", "Fleet Supervisor")
        frappe.set_user(staff_user)
        ctx = driver_portal.get_driver_context()
        self.assertTrue(ctx["enabled"])
        self.assertFalse(ctx["linked"])
        self.assertIsNone(ctx["driver"])
        self.assertTrue(ctx["is_staff"])
        labels = {link["label"] for link in ctx["links"]}
        # A Fleet Supervisor sees the workspace and the Dispatch Board at minimum.
        self.assertIn("Salis Workspace", labels)
        self.assertIn("Dispatch Board", labels)
        # Every link carries a label and an /app URL.
        for link in ctx["links"]:
            self.assertTrue(link["label"])
            self.assertTrue(link["url"].startswith("/app/"))

    def test_staff_links_exclude_unpermitted_destinations(self):
        """A Fleet Supervisor is NOT a fuel approver, so the Fuel Approval Console
        link must be withheld — links are permission-scoped, not a fixed list."""
        staff_user = _ensure_staff_user("drv_staff@example.com", "Fleet Supervisor")
        frappe.set_user(staff_user)
        labels = {link["label"] for link in driver_portal.get_driver_context()["links"]}
        self.assertNotIn("Fuel Approval Console", labels)

    def test_no_vehicle_blocks_fuel_request(self):
        frappe.set_user(self.user_b)
        with self.assertRaises(frappe.ValidationError):
            driver_portal.submit_fuel_request(litres=10)

    def test_fuel_request_rejects_vehicle_not_bound_to_driver(self):
        """A driver passing an arbitrary vehicle id that is NOT theirs (not their
        current_vehicle and no Active Vehicle Assignment) must be rejected — they
        cannot charge fuel against someone else's vehicle."""
        # driver_a has a bound current_vehicle; create a foreign vehicle that is
        # NOT assigned to driver_a in any way.
        frappe.set_user("Administrator")
        foreign = frappe.get_doc(
            {"doctype": "Salis Vehicle", "plate_number": "FOREIGN VEH 1", "status": "Active"}
        ).insert(ignore_permissions=True).name
        frappe.db.commit()
        emp = frappe.db.get_value("Salis Driver", self.driver_a, "employee")
        user_a = frappe.db.get_value("Employee", emp, "user_id")
        frappe.set_user(user_a)
        with self.assertRaises(frappe.PermissionError):
            driver_portal.submit_fuel_request(litres=20, vehicle=foreign)
        frappe.set_user("Administrator")
        frappe.delete_doc("Salis Vehicle", foreign, ignore_permissions=True, force=True)
        frappe.db.commit()

    def test_fuel_request_accepts_vehicle_via_active_assignment(self):
        """A vehicle bound through an Active Vehicle Assignment is accepted even
        when it is not the driver's current_vehicle."""
        frappe.set_user("Administrator")
        assigned = frappe.get_doc(
            {"doctype": "Salis Vehicle", "plate_number": "ASSIGNED VEH 1", "status": "Active"}
        ).insert(ignore_permissions=True).name
        va = frappe.get_doc(
            {"doctype": "Vehicle Assignment", "driver": self.driver_a,
             "vehicle": assigned, "status": "Active",
             "start_date": frappe.utils.today()}
        ).insert(ignore_permissions=True)
        frappe.db.commit()
        emp = frappe.db.get_value("Salis Driver", self.driver_a, "employee")
        user_a = frappe.db.get_value("Employee", emp, "user_id")
        frappe.set_user(user_a)
        res = driver_portal.submit_fuel_request(litres=15, vehicle=assigned)
        self.assertEqual(frappe.db.get_value("Fuel Request", res["name"], "vehicle"), assigned)
        frappe.set_user("Administrator")
        frappe.delete_doc("Fuel Request", res["name"], ignore_permissions=True, force=True)
        va.delete(ignore_permissions=True)
        frappe.delete_doc("Salis Vehicle", assigned, ignore_permissions=True, force=True)
        frappe.db.commit()

    def test_trips_scoped_to_self(self):
        trip = frappe.get_doc({"doctype": "Dispatch Trip", "driver": self.driver_a,
                               "trip_date": frappe.utils.today(), "status": "Planned"}).insert(
            ignore_permissions=True)
        frappe.db.commit()
        frappe.set_user(self.user_b)
        names = [t["name"] for t in driver_portal.my_trips_today()]
        self.assertNotIn(trip.name, names)
        frappe.set_user("Administrator")
        trip.delete(ignore_permissions=True)
        frappe.db.commit()
