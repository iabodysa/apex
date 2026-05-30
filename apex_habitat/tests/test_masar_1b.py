"""Masar Phase 1b — read-only "my worker route today" surface tests.

Covers the additions of the standalone surface, all identity-scoped to the
CURRENT session user (no client-supplied driver id) and read-only (no
``frappe.db.commit`` of our own state — the worker-trip fixture commits via the
shared mixin, but every assertion here is a read):

  1. ``masar.get_my_worker_route_summary`` — the compact roll-up: trip/stop
     counts, expected total, and the earliest housing "next pickup", resolved
     for the session driver only; a different driver does not see it; a
     non-driver is rejected; the portal-disabled guard fires.
  2. the standalone ``/masar`` www page context — Masar is now the worker
     self-service app shell: it is guest-accessible (identity is the personal
     ``?w=<token>`` resolved server-side by the API, not a desk login), so the
     page never redirects, forwards the token verbatim to the SPA, and exposes
     the Salis Portal Theme appearance. (The old driver "my route today" view
     moved into the driver portal; see ``test_driver_portal``.)

The worker-trip fixture and the driver/employee chain are reused from
``test_masar_worker_movement`` so the two suites stay convention-aligned and
re-runs on a non-fresh DB never duplicate.
"""

import unittest

import frappe

from apex_habitat.salis.api import masar
from apex_habitat.tests.test_driver_portal import _ensure_test_driver
from apex_habitat.tests.test_masar_worker_movement import (
    _WorkerTripMixin,
    _building,
    _driver_user_for,
    _employee,
    _ensure_driver_chain,
    _project,
)
from apex_habitat.www import masar as masar_page


class TestMasarSummaryEndpoint(_WorkerTripMixin, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
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
        frappe.db.commit()

    def setUp(self):
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")

    def test_summary_rolls_up_counts_and_next_pickup_for_self(self):
        tr, rp, dt = self._worker_trip(
            self.driver, self.project, self.building, [self.w1, self.w2], "1b Route A"
        )
        frappe.set_user(self.driver_user)
        summary = masar.get_my_worker_route_summary()

        self.assertEqual(summary["driver"], self.driver)
        self.assertEqual(summary["date"], frappe.utils.today())
        # The fixture builds one trip with two stops and a two-worker manifest.
        self.assertGreaterEqual(summary["trip_count"], 1)
        self.assertGreaterEqual(summary["stop_count"], 2)
        self.assertGreaterEqual(summary["expected_total"], 2)

        # next_pickup points at the housing-pickup stop with the linked building.
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
            frappe.db.commit()
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


class TestMasarPageContext(_WorkerTripMixin, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        frappe.db.set_single_value("Salis Settings", "enable_driver_portal", 1)
        cls.project = _project("Masar 1b Page Project")
        cls.building = _building("Masar 1b Page Building")
        cls.driver = _ensure_test_driver()
        cls.driver_user = _driver_user_for(cls.driver)
        cls.w1 = _employee("Masar 1b Page Worker")
        frappe.db.commit()

    def setUp(self):
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")

    def test_guest_gets_app_shell_context_no_redirect(self):
        """Masar is now guest-accessible (identity is the personal token, resolved
        server-side by the API), so the page must NOT redirect a guest to login —
        it returns the populated SPA shell context instead."""
        frappe.set_user("Guest")
        frappe.local.form_dict = frappe._dict()
        try:
            ctx = masar_page.get_context(frappe._dict())
            self.assertEqual(ctx.no_cache, 1)
            self.assertTrue(ctx.portal_theme)
            # csrf is a string (a real token in a browser request; "" in a
            # session-less render — never a 500).
            self.assertIsInstance(ctx.csrf_token, str)
            # No token in the query → empty pass-through; never an employee id.
            self.assertEqual(ctx.masar_token, "")
        finally:
            frappe.local.form_dict = frappe._dict()
            frappe.set_user("Administrator")

    def test_personal_token_is_passed_through_to_shell(self):
        """The ``?w=<token>`` value is forwarded verbatim to the SPA; the page
        never resolves it to an employee (the whitelisted API does, server-side)."""
        frappe.set_user("Guest")
        frappe.local.form_dict = frappe._dict(w="opaque-personal-token")
        try:
            ctx = masar_page.get_context(frappe._dict())
            self.assertEqual(ctx.masar_token, "opaque-personal-token")
        finally:
            frappe.local.form_dict = frappe._dict()
            frappe.set_user("Administrator")

    def test_theme_appearance_is_exposed(self):
        """The shell carries the Salis Portal Theme appearance (theme slug + brand
        flag) so the SPA renders with the right design tokens."""
        frappe.set_user("Guest")
        frappe.local.form_dict = frappe._dict()
        try:
            ctx = masar_page.get_context(frappe._dict())
            self.assertIn(ctx.portal_theme, {"afmco", "frappe", "dark", "gemini"})
            self.assertIsInstance(ctx.portal_show_brand, bool)
        finally:
            frappe.local.form_dict = frappe._dict()
            frappe.set_user("Administrator")
