# Copyright (c) 2026, AFMCO and contributors
"""Driver-portal feature-flag gating: with ``Salis Settings.enable_driver_portal``
off, every driver-portal endpoint refuses.

The flag is the single kill-switch for the self-service portal, and this file is the
ONLY thing that proves it bites. The two shipped suites beside the controllers
(``test_masar_execution.py``, ``test_personal_service.py``) both ``patch.object(...,
"_require_enabled")`` so they can reach the body under test — which is right for them
and is exactly why the guard needs proving somewhere that does not patch it.

Repointed 2026-08-15: the four cases here called ``get_driver_context``,
``driver_check_in``, ``submit_fuel_request`` and ``my_support_tickets``. The first,
second and fourth no longer exist anywhere in the app; ``submit_fuel_request`` moved to
``apex/salis/api/fleet_employee.py``. Every case was therefore an AttributeError, not a
proof. They are replaced by one parameterised case over the surviving surface, taking a
read, a personal read and a write so the guard is graded on all three shapes rather than
on one endpoint that happened to survive.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.api import driver_portal
from apex.salis.api.driver_portal import personal
from apex.tests.factories import make_test_driver as _ensure_test_driver


class TestDriverPortalDisabledFlag(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.driver = _ensure_test_driver()
        cls.user = frappe.db.get_value(
            "Employee", frappe.db.get_value("Salis Driver", cls.driver, "employee"), "user_id"
        )

    def tearDown(self):
        frappe.set_user("Administrator")
        frappe.db.set_single_value("Salis Settings", "enable_driver_portal", 1)

    def test_every_live_endpoint_refuses_when_the_portal_is_off(self):
        """One case, three endpoint shapes, for a genuinely LINKED driver.

        Linked on purpose: an unlinked user is refused by identity resolution instead,
        so the refusal would prove nothing about the flag. The enabled half runs first
        and is asserted to SUCCEED, or a driver fixture that could not resolve at all
        would satisfy the disabled half and the whole case would be vacuous.
        """
        calls = {
            "profile read": driver_portal.get_driver_profile,
            "trips read": driver_portal.my_trips_today,
            # Reached through the submodule: personal.py's four endpoints are NOT
            # re-exported by the package __init__ (only profile/trips/execution are),
            # so `driver_portal.get_my_custody` is an AttributeError, not an endpoint.
            "personal read": personal.get_my_custody,
        }

        frappe.set_user(self.user)
        for label, call in calls.items():
            with self.subTest(endpoint=label, portal="on"):
                call()

        frappe.set_user("Administrator")
        frappe.db.set_single_value("Salis Settings", "enable_driver_portal", 0)
        frappe.set_user(self.user)
        for label, call in calls.items():
            with self.subTest(endpoint=label, portal="off"):
                with self.assertRaises(frappe.PermissionError):
                    call()
        frappe.set_user("Administrator")

    def test_the_write_path_refuses_when_the_portal_is_off(self):
        """The write half, kept separate because it needs no trip to fail closed.

        ``start_my_trip`` calls ``_require_enabled()`` before it resolves the trip
        (execution.py:57), so a disabled portal must answer PermissionError for a
        nonexistent trip id rather than DoesNotExistError — which is what distinguishes
        the guard firing from the lookup failing.
        """
        frappe.set_user("Administrator")
        frappe.db.set_single_value("Salis Settings", "enable_driver_portal", 0)
        frappe.set_user(self.user)
        with self.assertRaises(frappe.PermissionError):
            driver_portal.start_my_trip("NO-SUCH-TRIP-" + frappe.generate_hash(length=12))
        frappe.set_user("Administrator")
