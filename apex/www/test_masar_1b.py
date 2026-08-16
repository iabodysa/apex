# Copyright (c) 2026, AFMCO and contributors
"""Masar Phase 1b — read-only "my worker route today" surface tests.

Covers ``masar.get_my_worker_route_summary``, identity-scoped to the CURRENT
session user (no client-supplied driver id) and read-only (no ``frappe.db.commit``
of our own state — the worker-trip fixture commits via the shared mixin, but every
assertion here is a read): the compact roll-up of trip/stop counts, expected total
and the earliest housing "next pickup", resolved for the session driver only; a
different driver does not see it; a non-driver is rejected; the portal-disabled
guard fires.

This module has no page-context test class: ``masar.py:64`` delegates page context to
``publish_portal_context`` (portal_bootstrap.py:130-160 publishes only no_cache,
csrf_token, shell_meta and boot), so no controller sets ``ctx.portal_theme``,
``ctx.portal_show_brand`` or ``ctx.masar_has_token``, and ``THEME_SLUGS`` does not exist
anywhere in the app. Both contracts ship covered elsewhere:
``apex/www/test_portal_shell_contract.py`` asserts ``context.masar_has_token`` is
ABSENT from masar.py, and ``apex/www/test_portal_token_entry.py`` covers the
token-to-``/masar/`` redirect, with the trailing slash masar.py:55 sends.

The worker-trip fixture and the driver/employee chain are reused from
``test_masar_worker_movement`` so the two suites stay convention-aligned and
re-runs on a non-fresh DB never duplicate.
"""


import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.api import masar
from apex.tests.factories import (
    WorkerTripMixin as _WorkerTripMixin,
    driver_user as _driver_user_for,
    make_driver_chain as _ensure_driver_chain,
    make_masar_building as _building,
    make_test_driver as _ensure_test_driver,
    make_worker_employee as _employee,
    make_project as _project,
)


class TestMasarSummaryEndpoint(_WorkerTripMixin, FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        frappe.db.set_single_value("Salis Settings", "enable_driver_portal", 1)
        cls.project = _project("Masar 1b Project")
        cls.building = _building("Masar 1b Building")
        cls.driver = _ensure_test_driver()
        cls.driver_user = _driver_user_for(cls.driver)
        cls.w1 = _employee("Masar 1b Worker One")
        cls.w2 = _employee("Masar 1b Worker Two")
        cls.other_driver, cls.other_user = _ensure_driver_chain(
            "masar_1b_other_drv@example.com", "Masar 1b Other"
        )

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        if frappe.db.exists("Project", cls.project):
            frappe.delete_doc("Project", cls.project, ignore_permissions=True, force=True)
        frappe.db.commit()
        super().tearDownClass()

    def setUp(self):
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")

    def test_summary_rolls_up_counts_and_next_pickup_for_self(self):
        # ``_today_worker_trips`` (apex/salis/api/masar_routes.py:96-103) only
        # reads Dispatch Trips at ``status: "Dispatched"``, the same filter every
        # driver-facing "today" surface applies; a trip left at the factory's
        # default ``Planned`` is invisible to the summary.
        tr, rp, dt = self._worker_trip(
            self.driver,
            self.project,
            self.building,
            [self.w1, self.w2],
            "1b Route A",
            status="Dispatched",
        )
        frappe.set_user(self.driver_user)
        summary = masar.get_my_worker_route_summary()

        self.assertEqual(summary["driver"], self.driver)
        self.assertEqual(summary["date"], frappe.utils.today())
        self.assertGreaterEqual(summary["trip_count"], 1)
        self.assertGreaterEqual(summary["stop_count"], 2)
        self.assertGreaterEqual(summary["expected_total"], 2)

        self.assertIsNotNone(summary["next_pickup"])
        self.assertEqual(summary["next_pickup"]["dispatch_trip"], dt.name)
        self.assertEqual(summary["next_pickup"]["sequence"], 1)
        self.assertEqual(summary["next_pickup"]["building_name"], "Masar 1b Building")
        self.assertEqual(
            summary["next_pickup"]["google_maps_url"],
            "https://maps.example/masar-building",
        )

    def test_summary_is_identity_scoped_to_self(self):
        """The unrelated driver sees their own (empty) summary, never the first
        driver's trip — the endpoint resolves the SESSION user."""
        self._worker_trip(
            self.driver, self.project, self.building, [self.w1], "1b Route B"
        )
        frappe.set_user(self.other_user)
        summary = masar.get_my_worker_route_summary()
        self.assertEqual(summary["driver"], self.other_driver)
        self.assertEqual(summary["trip_count"], 0)
        self.assertIsNone(summary["next_pickup"])

    def test_summary_rejects_non_driver(self):
        outsider = "masar_1b_outsider@example.com"
        if not frappe.db.exists("User", outsider):
            frappe.get_doc(
                {
                    "doctype": "User",
                    "email": outsider,
                    "first_name": "Masar 1b Outsider",
                    "send_welcome_email": 0,
                }
            ).insert(ignore_permissions=True)
        frappe.set_user(outsider)
        with self.assertRaises(frappe.PermissionError):
            masar.get_my_worker_route_summary()

    def test_summary_guarded_when_portal_disabled(self):
        frappe.set_user("Administrator")
        frappe.db.set_single_value("Salis Settings", "enable_driver_portal", 0)
        try:
            frappe.set_user(self.driver_user)
            with self.assertRaises(frappe.PermissionError):
                masar.get_my_worker_route_summary()
        finally:
            frappe.set_user("Administrator")
            frappe.db.set_single_value("Salis Settings", "enable_driver_portal", 1)


def tearDownModule():
    from apex.tests import factories

    factories.purge_test_buildings()
