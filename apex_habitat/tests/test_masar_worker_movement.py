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

import unittest

import frappe

from apex_habitat.salis.api import masar
from apex_habitat.tests.test_driver_portal import _ensure_test_driver


def _company():
    return (
        frappe.defaults.get_global_default("company")
        or frappe.get_all("Company", limit=1)[0].name
    )


def _project(name):
    p = frappe.db.get_value("Project", {"project_name": name}, "name")
    if not p:
        p = frappe.get_doc(
            {"doctype": "Project", "project_name": name}
        ).insert(ignore_permissions=True).name
    return p


def _site(name):
    s = frappe.db.get_value("Accommodation Site", {"site_name": name}, "name")
    if not s:
        s = frappe.get_doc(
            {"doctype": "Accommodation Site", "site_name": name, "company": _company()}
        ).insert(ignore_permissions=True).name
    return s


def _building(name):
    b = frappe.db.get_value("Accommodation Building", {"building_name": name}, "name")
    if not b:
        b = frappe.get_doc(
            {
                "doctype": "Accommodation Building",
                "building_name": name,
                "site": _site("Masar Test Site"),
                "total_capacity": 50,
                "google_maps_url": "https://maps.example/masar-building",
            }
        ).insert(ignore_permissions=True).name
    return b


def _employee(first_name):
    emp = frappe.db.get_value("Employee", {"employee_name": first_name}, "name")
    if not emp:
        emp = frappe.get_doc(
            {
                "doctype": "Employee",
                "first_name": first_name,
                "date_of_birth": "1990-01-01",
                "date_of_joining": frappe.utils.today(),
                "gender": "Male",
                "company": _company(),
            }
        ).insert(ignore_permissions=True).name
    return emp


def _driver_user_for(driver):
    """The login user behind a Salis Driver (via its Employee.user_id)."""
    emp = frappe.db.get_value("Salis Driver", driver, "employee")
    return frappe.db.get_value("Employee", emp, "user_id")


def _ensure_driver_chain(email, first_name):
    """Idempotently get-or-create a User+Employee+Salis Driver chain and return
    ``(driver_name, email)``. Mirrors the driver-portal test helpers so re-runs on
    a non-fresh DB never duplicate."""
    if not frappe.db.exists("User", email):
        u = frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": first_name,
                "send_welcome_email": 0,
            }
        )
        u.insert(ignore_permissions=True)
    user = frappe.get_doc("User", email)
    if "Driver" not in frappe.get_roles(email):
        user.add_roles("Driver")
    emp = frappe.db.get_value("Employee", {"user_id": email}, "name")
    if not emp:
        emp = frappe.get_doc(
            {
                "doctype": "Employee",
                "first_name": first_name,
                "user_id": email,
                "date_of_birth": "1990-01-01",
                "date_of_joining": frappe.utils.today(),
                "gender": "Male",
                "company": _company(),
            }
        ).insert(ignore_permissions=True).name
    drv = frappe.db.get_value("Salis Driver", {"employee": emp}, "name")
    if not drv:
        drv = frappe.get_doc(
            {
                "doctype": "Salis Driver",
                "employee": emp,
                "full_name": first_name,
                "status": "Active",
            }
        ).insert(ignore_permissions=True).name
    return drv, email


class _WorkerTripMixin:
    """Builds a complete Workers-line trip for a given driver and returns the
    handle records. Everything is created as Administrator."""

    def _worker_trip(self, driver, project, building, workers, route_name):
        tr = frappe.get_doc(
            {
                "doctype": "Transport Request",
                "service_line": "Workers",
                "request_type": "Accommodation to Project Shuttle",
                "project": project,
                "accommodation_building": building,
                "from_location": building,
                "to_location": "Project Site",
                "source_channel": "Desk",
                "status": "New",
                "workers": [
                    {"employee": e, "pickup_point": "Building Gate"} for e in workers
                ],
            }
        ).insert(ignore_permissions=True)
        # worker_count is server-derived on the Transport Request controller.
        tr.reload()

        rp = frappe.get_doc(
            {
                "doctype": "Route Plan",
                "route_name": route_name,
                "transport_request": tr.name,
                "project": project,
                "driver": driver,
                "stops": [
                    {
                        "sequence": 1,
                        "stop_name": "Housing Pickup",
                        "accommodation_building": building,
                        "location": "Building Gate",
                        "passengers": len(workers),
                    },
                    {
                        "sequence": 2,
                        "stop_name": "Project Drop-off",
                        "location": "Project Site",
                        "passengers": 0,
                    },
                ],
            }
        ).insert(ignore_permissions=True)

        dt = frappe.get_doc(
            {
                "doctype": "Dispatch Trip",
                "route_plan": rp.name,
                "transport_request": tr.name,
                "driver": driver,
                "trip_date": frappe.utils.today(),
                "depart_time": "06:30:00",
                "status": "Planned",
            }
        ).insert(ignore_permissions=True)
        frappe.db.commit()
        self.addCleanup(lambda: self._purge(dt.name, rp.name, tr.name))
        return tr, rp, dt

    @staticmethod
    def _purge(dt_name, rp_name, tr_name):
        frappe.set_user("Administrator")
        for dtp in (
            ("Dispatch Trip", dt_name),
            ("Route Plan", rp_name),
            ("Transport Request", tr_name),
        ):
            if frappe.db.exists(*dtp):
                doc = frappe.get_doc(*dtp)
                if doc.docstatus == 1:
                    try:
                        doc.cancel()
                    except Exception:
                        pass
                frappe.delete_doc(*dtp, ignore_permissions=True, force=True)
        frappe.db.commit()


class TestMasarSchemaInstall(unittest.TestCase):
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
        self.assertEqual(field.options, "Accommodation Building")

    def test_route_stop_link_is_optional(self):
        """Existing/unset rows are unaffected: the link is nullable (not reqd)."""
        field = frappe.get_meta("Route Stop").get_field("accommodation_building")
        self.assertFalse(field.reqd)


class TestTripStartLogController(_WorkerTripMixin, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cls.project = _project("Masar TSL Project")
        cls.building = _building("Masar TSL Building")
        cls.driver = _ensure_test_driver()
        cls.w1 = _employee("Masar Worker One")
        cls.w2 = _employee("Masar Worker Two")
        frappe.db.commit()

    def setUp(self):
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")

    def test_counts_derived_from_manifest_and_boarding_rows(self):
        tr, rp, dt = self._worker_trip(
            self.driver, self.project, self.building, [self.w1, self.w2], "TSL Route A"
        )
        # The TR manifest has two registered workers.
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
        # expected_count derived from the TR manifest (2); boarded_count from the
        # single boarding row (1) — both read-only, server-derived.
        self.assertEqual(log.expected_count, 2)
        self.assertEqual(log.boarded_count, 1)
        # Fetched trip context resolved from the Dispatch Trip.
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
        frappe.db.commit()


class TestMasarReadEndpoint(_WorkerTripMixin, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        frappe.db.set_single_value("Salis Settings", "enable_driver_portal", 1)
        cls.project = _project("Masar EP Project")
        cls.building = _building("Masar EP Building")
        cls.driver = _ensure_test_driver()
        cls.driver_user = _driver_user_for(cls.driver)
        cls.w1 = _employee("Masar EP Worker One")
        # A second, unrelated driver — created once so re-runs never duplicate.
        cls.other_driver, cls.other_user = _ensure_driver_chain(
            "masar_other_drv@example.com", "Masar Other"
        )
        frappe.db.commit()

    def setUp(self):
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")

    def test_current_driver_sees_own_worker_route_with_housing_pickup(self):
        tr, rp, dt = self._worker_trip(
            self.driver, self.project, self.building, [self.w1], "EP Route A"
        )
        # Call the endpoint AS the driver's own user — identity resolved server-side.
        frappe.set_user(self.driver_user)
        payload = masar.get_my_worker_route_today()

        self.assertEqual(payload["driver"], self.driver)
        self.assertEqual(payload["date"], frappe.utils.today())
        names = [t["dispatch_trip"] for t in payload["trips"]]
        self.assertIn(dt.name, names)

        trip = next(t for t in payload["trips"] if t["dispatch_trip"] == dt.name)
        # Registered manifest surfaced.
        self.assertEqual(trip["expected_count"], 1)
        self.assertEqual(trip["workers"][0]["employee"], self.w1)
        # Ordered stops, and the first stop is a housing pickup with the building.
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
        # driver A's worker trip
        tr, rp, dt = self._worker_trip(
            self.driver, self.project, self.building, [self.w1], "EP Route B"
        )
        # Call as the SECOND, unrelated driver (built once in setUpClass).
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
        frappe.db.commit()
        frappe.set_user(outsider)
        with self.assertRaises(frappe.PermissionError):
            masar.get_my_worker_route_today()

    def test_representatives_trip_excluded(self):
        """Only Workers-line trips are returned; a Representatives trip for the
        same driver today is excluded from the worker route view."""
        rep_tr = frappe.get_doc(
            {
                "doctype": "Transport Request",
                "service_line": "Representatives",
                "request_type": "Administrative Trip / Document Signing",
                "project": self.project,
                # A Representatives trip now requires the representative (an Employee)
                # and must not carry labour-accommodation/worker context.
                "representative": _employee("EP Representative"),
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
        frappe.db.commit()
        self.addCleanup(lambda: self._purge(rep_dt.name, rep_rp.name, rep_tr.name))

        frappe.set_user(self.driver_user)
        payload = masar.get_my_worker_route_today()
        names = [t["dispatch_trip"] for t in payload["trips"]]
        self.assertNotIn(rep_dt.name, names)
