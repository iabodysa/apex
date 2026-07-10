# Copyright (c) 2026, AFMCO and contributors
"""Masar (Worker Movement — the Workers division of Salis) Phase 1 backend tests.

Covers the four deliverables of the backend foundation:

  1. schema install — the ``Trip Start Log`` + ``Trip Boarding Event`` DocTypes
     exist, and ``Route Stop`` carries the new optional ``accommodation_building``
     pickup link (existing/unset rows unaffected);
  2. ``Trip Start Log`` controller — ``boarded_count`` derives from the boarding
     child rows, ``expected_count`` derives from the linked Transport Request's
     worker manifest, the registered/unregistered boarding rule is enforced, and
     the end-before-start guard fires; no GL is posted;
  3. the Habitat-Salis bridge - a Route Stop that links an Accommodation
     Building IS a housing pickup, and the read endpoint surfaces that building;
  4. the read endpoint ``masar.get_my_worker_route_today`` — identity-scoped to
     the CURRENT driver (no client-supplied id): a driver sees only their own
     Workers route, a different driver does not, and a non-driver is rejected.

The worker-trip fixture is built as Administrator with ``ignore_permissions`` (we
exercise the new DocType + endpoint, not the Transport Request approval workflow,
which has its own tests). The endpoint is then called as the driver's own user to
prove server-side identity resolution.
"""


import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.api import masar
from apex.tests import factories

# All fixture builders + the worker-trip mixin live in tests/factories.py (P-135);
# this module calls them via the ``factories`` namespace — no local re-export aliases,
# so the cross-test-import ratchet (test_no_cross_test_imports) stays empty.


class TestMasarSchemaInstall(FrappeTestCase):
    def test_doctypes_installed(self):
        self.assertTrue(frappe.db.exists("DocType", "Trip Start Log"))
        self.assertTrue(frappe.db.exists("DocType", "Trip Boarding Event"))

    def test_trip_start_log_is_submittable_in_salis(self):
        meta = frappe.get_meta("Trip Start Log")
        self.assertTrue(meta.is_submittable)
        self.assertEqual(meta.module, "Salis")

    def test_route_stop_has_accommodation_building_link(self):
        """The new optional housing-pickup link exists on Route Stop and targets
        Accommodation Building (the Habitat-Salis bridge)."""
        field = frappe.get_meta("Route Stop").get_field("accommodation_building")
        self.assertIsNotNone(field)
        self.assertEqual(field.fieldtype, "Link")
        self.assertEqual(field.options, "Building")

    def test_route_stop_link_is_optional(self):
        """Existing/unset rows are unaffected: the link is nullable (not reqd)."""
        field = frappe.get_meta("Route Stop").get_field("accommodation_building")
        self.assertFalse(field.reqd)


class TestTripStartLogController(factories.WorkerTripMixin, FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.project = factories.make_project("Masar TSL Project")
        cls.building = factories.make_masar_building("Masar TSL Building")
        cls.driver = factories.make_test_driver()
        cls.w1 = factories.make_worker_employee("Masar Worker One")
        cls.w2 = factories.make_worker_employee("Masar Worker Two")

    @classmethod
    def tearDownClass(cls):
        # setUpClass commits a per-class Project OUTSIDE the per-method savepoint
        # rollback; delete it so the committed Project does not leak across the
        # test DB. (Site/Building/Employees are reuse-or-create shared fixtures.)
        frappe.set_user("Administrator")
        if frappe.db.exists("Project", cls.project):
            frappe.delete_doc("Project", cls.project, ignore_permissions=True, force=True)
        frappe.db.commit()
        super().tearDownClass()

    def setUp(self):
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")

    def test_counts_derived_from_manifest_and_boarding_rows(self):
        tr, rp, dt = self._worker_trip(
            self.driver, self.project, self.building, [self.w1, self.w2], "TSL Route A"
        )
        # [#f3ue6h]
        self.assertEqual(tr.worker_count, 2)

        log = frappe.get_doc(
            {
                "doctype": "Trip Start Log",
                "dispatch_trip": dt.name,
                "status": "Started",
                "start_datetime": frappe.utils.now_datetime(),
                "boarding_events": [
                    {
                        "worker": self.w1,
                        "stop_name": "Housing Pickup",
                        "accommodation_building": self.building,
                        "boarded_at": frappe.utils.now_datetime(),
                        "method": "Manual",
                    }
                ],
            }
        )
        log.insert(ignore_permissions=True)
        self.addCleanup(
            lambda: frappe.delete_doc(
                "Trip Start Log", log.name, ignore_permissions=True, force=True
            )
        )
        # [#ksolmx]
        self.assertEqual(log.expected_count, 2)
        self.assertEqual(log.boarded_count, 1)
        # [#2ouc2e]
        self.assertEqual(log.transport_request, tr.name)
        self.assertEqual(log.route_plan, rp.name)

    def test_boarded_count_updates_when_rows_added(self):
        tr, rp, dt = self._worker_trip(
            self.driver, self.project, self.building, [self.w1, self.w2], "TSL Route B"
        )
        log = frappe.get_doc(
            {"doctype": "Trip Start Log", "dispatch_trip": dt.name, "status": "Started"}
        )
        log.insert(ignore_permissions=True)
        self.addCleanup(
            lambda: frappe.delete_doc(
                "Trip Start Log", log.name, ignore_permissions=True, force=True
            )
        )
        self.assertEqual(log.boarded_count, 0)
        log.append("boarding_events", {"worker": self.w1, "method": "Manual"})
        log.append("boarding_events", {"worker": self.w2, "method": "QR"})
        log.save(ignore_permissions=True)
        self.assertEqual(log.boarded_count, 2)

    def test_unregistered_worker_row_supported(self):
        """An unregistered contractor/temp boards with a name/id, no Employee."""
        tr, rp, dt = self._worker_trip(
            self.driver, self.project, self.building, [self.w1], "TSL Route C"
        )
        log = frappe.get_doc(
            {
                "doctype": "Trip Start Log",
                "dispatch_trip": dt.name,
                "status": "Started",
                "boarding_events": [
                    {
                        "is_unregistered": 1,
                        "worker_name": "Temp Contractor",
                        "contractor_id": "IQ-12345",
                        "method": "Manual",
                    }
                ],
            }
        )
        log.insert(ignore_permissions=True)
        self.addCleanup(
            lambda: frappe.delete_doc(
                "Trip Start Log", log.name, ignore_permissions=True, force=True
            )
        )
        self.assertEqual(log.boarded_count, 1)

    def test_boarding_row_requires_worker_or_unregistered(self):
        """A boarding row with neither a worker nor the unregistered path is
        rejected — the headcount must always identify who boarded."""
        tr, rp, dt = self._worker_trip(
            self.driver, self.project, self.building, [self.w1], "TSL Route D"
        )
        log = frappe.get_doc(
            {
                "doctype": "Trip Start Log",
                "dispatch_trip": dt.name,
                "status": "Started",
                "boarding_events": [{"method": "Manual"}],
            }
        )
        with self.assertRaises(frappe.ValidationError):
            log.insert(ignore_permissions=True)

    def test_unregistered_row_requires_name_or_id(self):
        tr, rp, dt = self._worker_trip(
            self.driver, self.project, self.building, [self.w1], "TSL Route E"
        )
        log = frappe.get_doc(
            {
                "doctype": "Trip Start Log",
                "dispatch_trip": dt.name,
                "status": "Started",
                "boarding_events": [{"is_unregistered": 1, "method": "Manual"}],
            }
        )
        with self.assertRaises(frappe.ValidationError):
            log.insert(ignore_permissions=True)

    def test_end_before_start_rejected(self):
        tr, rp, dt = self._worker_trip(
            self.driver, self.project, self.building, [self.w1], "TSL Route F"
        )
        log = frappe.get_doc(
            {
                "doctype": "Trip Start Log",
                "dispatch_trip": dt.name,
                "status": "Completed",
                "start_datetime": "2026-05-30 08:00:00",
                "end_datetime": "2026-05-30 07:00:00",
            }
        )
        with self.assertRaises(frappe.ValidationError):
            log.insert(ignore_permissions=True)

    def test_submit_posts_no_gl_entry(self):
        """No-financial-impact boundary: submitting a Trip Start Log creates no
        GL Entry."""
        tr, rp, dt = self._worker_trip(
            self.driver, self.project, self.building, [self.w1], "TSL Route G"
        )
        log = frappe.get_doc(
            {
                "doctype": "Trip Start Log",
                "dispatch_trip": dt.name,
                "status": "Completed",
                "start_datetime": "2026-05-30 06:30:00",
                "end_datetime": "2026-05-30 08:00:00",
                "boarding_events": [{"worker": self.w1, "method": "Manual"}],
            }
        )
        log.insert(ignore_permissions=True)
        log.submit()
        self.addCleanup(
            lambda: self._purge_log(log.name)
        )
        self.assertEqual(log.docstatus, 1)
        self.assertFalse(
            frappe.db.exists("GL Entry", {"voucher_no": log.name})
        )

    @staticmethod
    def _purge_log(name):
        frappe.set_user("Administrator")
        if not frappe.db.exists("Trip Start Log", name):
            return
        doc = frappe.get_doc("Trip Start Log", name)
        if doc.docstatus == 1:
            try:
                doc.cancel()
            except Exception:
                pass
        frappe.delete_doc("Trip Start Log", name, ignore_permissions=True, force=True)


class TestMasarReadEndpoint(factories.WorkerTripMixin, FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        frappe.db.set_single_value("Salis Settings", "enable_driver_portal", 1)
        cls.project = factories.make_project("Masar EP Project")
        cls.building = factories.make_masar_building("Masar EP Building")
        cls.driver = factories.make_test_driver()
        cls.driver_user = factories.driver_user(cls.driver)
        cls.w1 = factories.make_worker_employee("Masar EP Worker One")
        # [#n2d8l0]
        cls.other_driver, cls.other_user = factories.make_driver_chain(
            "masar_other_drv@example.com", "Masar Other"
        )

    @classmethod
    def tearDownClass(cls):
        # setUpClass commits a per-class Project OUTSIDE the per-method savepoint
        # rollback; delete it so the committed Project does not leak across the
        # test DB. (Site/Building/Employees are reuse-or-create shared fixtures.)
        frappe.set_user("Administrator")
        if frappe.db.exists("Project", cls.project):
            frappe.delete_doc("Project", cls.project, ignore_permissions=True, force=True)
        frappe.db.commit()
        super().tearDownClass()

    def setUp(self):
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")

    def test_current_driver_sees_own_worker_route_with_housing_pickup(self):
        tr, rp, dt = self._worker_trip(
            self.driver, self.project, self.building, [self.w1], "EP Route A"
        )
        # [#8b85uv]
        frappe.set_user(self.driver_user)
        payload = masar.get_my_worker_route_today()

        self.assertEqual(payload["driver"], self.driver)
        self.assertEqual(payload["date"], frappe.utils.today())
        names = [t["dispatch_trip"] for t in payload["trips"]]
        self.assertIn(dt.name, names)

        trip = next(t for t in payload["trips"] if t["dispatch_trip"] == dt.name)
        # [#pz81yt]
        self.assertEqual(trip["expected_count"], 1)
        self.assertEqual(trip["workers"][0]["employee"], self.w1)
        # [#cjmx2z]
        self.assertEqual([s["sequence"] for s in trip["stops"]], [1, 2])
        pickup_stop = trip["stops"][0]
        self.assertEqual(pickup_stop["accommodation_building"], self.building)
        self.assertIsNotNone(pickup_stop["pickup"])
        self.assertEqual(pickup_stop["pickup"]["name"], self.building)
        self.assertEqual(
            pickup_stop["pickup"]["google_maps_url"],
            "https://maps.example/masar-building",
        )

    def test_endpoint_is_identity_scoped_to_self(self):
        """A different driver does not see another driver's worker route — the
        endpoint resolves the SESSION user, never a supplied id."""
        # [#iqjipe]
        tr, rp, dt = self._worker_trip(
            self.driver, self.project, self.building, [self.w1], "EP Route B"
        )
        # [#tu0oi1]
        frappe.set_user(self.other_user)
        payload = masar.get_my_worker_route_today()
        self.assertEqual(payload["driver"], self.other_driver)
        names = [t["dispatch_trip"] for t in payload["trips"]]
        self.assertNotIn(dt.name, names)

    def test_non_driver_is_rejected(self):
        outsider = "masar_outsider@example.com"
        if not frappe.db.exists("User", outsider):
            frappe.get_doc(
                {
                    "doctype": "User",
                    "email": outsider,
                    "first_name": "Masar Outsider",
                    "send_welcome_email": 0,
                }
            ).insert(ignore_permissions=True)
        frappe.set_user(outsider)
        with self.assertRaises(frappe.PermissionError):
            masar.get_my_worker_route_today()

    def test_representatives_trip_excluded(self):
        """Only worker-transport trips (Site Transport / Inter-City Relocation) are
        returned; an Administrative Trip for the same driver today is excluded from
        the worker route view."""
        rep_tr = frappe.get_doc(
            {
                "doctype": "Transport Request",
                "service_line": "Administrative Trip",
                "request_type": "Administrative Trip / Document Signing",
                "project": self.project,
                # [#per8o9]
                "representative": factories.make_worker_employee("EP Representative"),
                "destination": "Ministry",
                "from_location": "HQ",
                "to_location": "Ministry",
                "source_channel": "Desk",
                "status": "New",
            }
        ).insert(ignore_permissions=True)
        rep_rp = frappe.get_doc(
            {
                "doctype": "Route Plan",
                "route_name": "EP Rep Route",
                "transport_request": rep_tr.name,
                "project": self.project,
                "driver": self.driver,
            }
        ).insert(ignore_permissions=True)
        rep_dt = frappe.get_doc(
            {
                "doctype": "Dispatch Trip",
                "route_plan": rep_rp.name,
                "transport_request": rep_tr.name,
                "driver": self.driver,
                "trip_date": frappe.utils.today(),
                "status": "Planned",
            }
        ).insert(ignore_permissions=True)
        self.addCleanup(lambda: self._purge(rep_dt.name, rep_rp.name, rep_tr.name))

        frappe.set_user(self.driver_user)
        payload = masar.get_my_worker_route_today()
        names = [t["dispatch_trip"] for t in payload["trips"]]
        self.assertNotIn(rep_dt.name, names)


def tearDownModule():
    # P-148: drop this module's committed Accommodation Buildings so the suite's
    # post-run building count returns to the pre-suite baseline (see factories.py).
    from apex.tests import factories

    factories.purge_test_buildings()
