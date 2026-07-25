# Copyright (c) 2026, AFMCO and contributors
"""Idempotency tests for the Salis background engines: re-running a daily/weekly
job must never double-post its ledger/snapshot rows."""


import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.fuel_engine import accrue_fuel_consumption, monthly_fuel_reconciliation
from apex.salis.rental_engine import daily_rental_accrual
from apex.salis.tasks import reconcile_operations_alerts
from apex.salis.utilisation_engine import weekly_vehicle_utilisation_snapshot


class TestRentalAccrualIdempotency(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.office = frappe.db.get_value("Rental Office", {"office_name": "Eng Test Office"}, "name")
        if not cls.office:
            cls.office = frappe.get_doc({"doctype": "Rental Office",
                                         "office_name": "Eng Test Office",
                                         "status": "Active"}).insert(ignore_permissions=True).name
        cls.vehicle = frappe.db.get_value("Salis Vehicle", {"plate_number": "RENT ENG 1"}, "name")
        if not cls.vehicle:
            cls.vehicle = frappe.get_doc({"doctype": "Salis Vehicle", "plate_number": "RENT ENG 1",
                                          "ownership": "Rented", "status": "Active"}).insert(
                ignore_permissions=True).name
        if not frappe.db.exists("Rental Vehicle Movement",
                                {"vehicle": cls.vehicle, "movement_type": "Receipt", "docstatus": 1}):
            m = frappe.get_doc({"doctype": "Rental Vehicle Movement", "movement_type": "Receipt",
                                "vehicle": cls.vehicle, "rental_office": cls.office,
                                "movement_date": frappe.utils.today(), "daily_rate": 100}).insert(
                ignore_permissions=True)
            m.submit()

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        # [#nym08x]
        movements = frappe.db.get_all(
            "Rental Vehicle Movement",
            filters={"vehicle": cls.vehicle, "movement_type": "Receipt"},
            pluck="name",
        )
        for m_name in movements:
            doc = frappe.get_doc("Rental Vehicle Movement", m_name)
            if doc.docstatus == 1:
                doc.cancel()
            frappe.delete_doc("Rental Vehicle Movement", m_name, force=True, ignore_permissions=True)
        if cls.vehicle and frappe.db.exists("Salis Vehicle", cls.vehicle):
            frappe.delete_doc("Salis Vehicle", cls.vehicle, force=True, ignore_permissions=True)
        if cls.office and frappe.db.exists("Rental Office", cls.office):
            frappe.delete_doc("Rental Office", cls.office, force=True, ignore_permissions=True)
        super().tearDownClass()

    def test_accrual_is_idempotent(self):
        today = frappe.utils.today()
        frappe.db.delete("Rental Accrual Ledger", {"vehicle": self.vehicle, "accrual_date": today})
        daily_rental_accrual()
        first = frappe.db.count("Rental Accrual Ledger", {"vehicle": self.vehicle, "accrual_date": today})
        daily_rental_accrual()
        second = frappe.db.count("Rental Accrual Ledger", {"vehicle": self.vehicle, "accrual_date": today})
        self.assertEqual(first, 1)
        self.assertEqual(second, 1)


class TestUtilisationSnapshotIdempotency(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.vehicle = frappe.db.get_value("Salis Vehicle", {"plate_number": "UTIL ENG 1"}, "name")
        if not cls.vehicle:
            cls.vehicle = frappe.get_doc({"doctype": "Salis Vehicle", "plate_number": "UTIL ENG 1",
                                          "status": "Active"}).insert(ignore_permissions=True).name

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        if cls.vehicle and frappe.db.exists("Salis Vehicle", cls.vehicle):
            frappe.delete_doc("Salis Vehicle", cls.vehicle, force=True, ignore_permissions=True)
        super().tearDownClass()

    def test_snapshot_is_idempotent(self):
        today = frappe.utils.today()
        frappe.db.delete("Vehicle Utilisation Snapshot", {"vehicle": self.vehicle, "snapshot_date": today})
        weekly_vehicle_utilisation_snapshot()
        first = frappe.db.count("Vehicle Utilisation Snapshot", {"vehicle": self.vehicle, "snapshot_date": today})
        weekly_vehicle_utilisation_snapshot()
        second = frappe.db.count("Vehicle Utilisation Snapshot", {"vehicle": self.vehicle, "snapshot_date": today})
        self.assertEqual(first, 1)
        self.assertEqual(second, 1)


class TestFuelReconciliationNoDuplicateAlert(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.period = frappe.utils.today()[:7]
        cls.vehicle = frappe.db.get_value("Salis Vehicle", {"plate_number": "FUEL REC 1"}, "name")
        if not cls.vehicle:
            cls.vehicle = frappe.get_doc({"doctype": "Salis Vehicle", "plate_number": "FUEL REC 1",
                                          "status": "Active"}).insert(ignore_permissions=True).name
        if not frappe.db.exists("Fuel Quota", {"vehicle": cls.vehicle, "period_month": cls.period, "docstatus": 1}):
            q = frappe.get_doc({"doctype": "Fuel Quota", "vehicle": cls.vehicle,
                                "period_month": cls.period, "monthly_litres": 10,
                                "status": "Active"}).insert(ignore_permissions=True)
            q.submit()
        if not frappe.db.exists("Fuel Consumption Ledger", {"vehicle": cls.vehicle, "source_name": "FUELRECTEST"}):
            frappe.get_doc({"doctype": "Fuel Consumption Ledger", "vehicle": cls.vehicle,
                            "period_month": cls.period, "litres": 20, "amount": 300,
                            "source_type": "Fuel Daily Log", "source_name": "FUELRECTEST"}).insert(
                ignore_permissions=True)

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        # [#mlx5qk]
        frappe.db.delete("Fuel Consumption Ledger",
                         {"vehicle": cls.vehicle, "source_name": "FUELRECTEST"})
        quotas = frappe.db.get_all(
            "Fuel Quota",
            filters={"vehicle": cls.vehicle, "period_month": cls.period},
            pluck="name",
        )
        for q_name in quotas:
            doc = frappe.get_doc("Fuel Quota", q_name)
            if doc.docstatus == 1:
                doc.cancel()
            frappe.delete_doc("Fuel Quota", q_name, force=True, ignore_permissions=True)
        if cls.vehicle and frappe.db.exists("Salis Vehicle", cls.vehicle):
            frappe.delete_doc("Salis Vehicle", cls.vehicle, force=True, ignore_permissions=True)
        super().tearDownClass()

    def _window(self):
        from frappe.utils import get_first_day, get_last_day, getdate
        anchor = getdate(self.period + "-01")
        return [f"{get_first_day(anchor)} 00:00:00", f"{get_last_day(anchor)} 23:59:59"]

    def _count(self):
        return frappe.db.count("Operations Alert", {"alert_type": "Excessive Topup",
                               "vehicle": self.vehicle, "raised_on": ["between", self._window()]})

    def test_reconciliation_raises_exactly_one_alert(self):
        frappe.db.delete("Operations Alert", {"alert_type": "Excessive Topup",
                         "vehicle": self.vehicle, "raised_on": ["between", self._window()]})
        monthly_fuel_reconciliation()
        first = self._count()
        monthly_fuel_reconciliation()
        second = self._count()
        self.assertEqual(first, 1)
        self.assertEqual(second, 1)


class TestFuelAccrualLateDone(FrappeTestCase):
    """Regression: a Fuel Request created earlier that only flips to Done today
    (or any later day) must still be ledgered. The old window keyed accrual on
    ``request_date in [yesterday, today]`` AND status=Done, so a request with an
    old request_date that completes now was silently skipped and its litres
    vanished. Accrual is now driven off the un-ledgered Done set regardless of
    request_date, stamping a ``ledgered`` flag."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.vehicle = frappe.db.get_value("Salis Vehicle", {"plate_number": "FUEL LATE 1"}, "name")
        if not cls.vehicle:
            cls.vehicle = frappe.get_doc({"doctype": "Salis Vehicle", "plate_number": "FUEL LATE 1",
                                          "status": "Active"}).insert(ignore_permissions=True).name

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        if cls.vehicle and frappe.db.exists("Salis Vehicle", cls.vehicle):
            frappe.delete_doc("Salis Vehicle", cls.vehicle, force=True, ignore_permissions=True)
        super().tearDownClass()

    def _make_done_request(self, request_date):
        """Create a Done Fuel Request whose request_date is in the past, walking
        the legal Pending -> Approved -> Done flow. Transitions are owned by the
        native Fuel Request Workflow (driven here as Administrator); the approval
        carries a segregation-of-duties condition, so the requester is re-stamped
        to a distinct user first (this test exercises the ledger engine, not the
        SoD gate). Falls back to the direct save+submit path on a site without
        the workflow seeded."""
        from frappe.model.workflow import apply_workflow, get_workflow_name

        doc = frappe.get_doc({
            "doctype": "Fuel Request",
            "vehicle": self.vehicle,
            "request_date": request_date,
            "requested_litres": 5,
            "amount": 75,
            "status": "Pending",
        })
        doc.insert(ignore_permissions=True)
        if get_workflow_name("Fuel Request") == "Fuel Request Workflow":
            if doc.requested_by == frappe.session.user:
                doc.db_set("requested_by", "Guest")  # [#gzmtd5]
                doc.reload()
            apply_workflow(doc, "Approve")  # [#ms0ltc]
            doc.reload()
            apply_workflow(doc, "Complete")  # [#lpqooh]
        else:
            doc.status = "Approved"
            doc.save(ignore_permissions=True)
            doc.status = "Done"
            doc.save(ignore_permissions=True)
            doc.submit()
        return doc.name

    def test_late_done_request_is_ledgered(self):
        from frappe.utils import add_days, today

        old_date = add_days(today(), -10)  # [#eg5n9m]
        name = self._make_done_request(old_date)
        self.addCleanup(lambda: self._cleanup(name))

        # [#55bt65]
        self.assertEqual(frappe.db.get_value("Fuel Request", name, "ledgered"), 0)
        frappe.db.delete("Fuel Consumption Ledger", {"source_type": "Fuel Request", "source_name": name})

        accrue_fuel_consumption()

        rows = frappe.db.count("Fuel Consumption Ledger",
                               {"source_type": "Fuel Request", "source_name": name})
        self.assertEqual(rows, 1, "Late-Done request must be ledgered despite its old request_date.")
        self.assertEqual(frappe.db.get_value("Fuel Request", name, "ledgered"), 1,
                         "Request must be flagged ledgered after accrual.")

        # [#rla1hx]
        accrue_fuel_consumption()
        rows_again = frappe.db.count("Fuel Consumption Ledger",
                                     {"source_type": "Fuel Request", "source_name": name})
        self.assertEqual(rows_again, 1, "Re-running accrual must not double-ledger.")

    def _cleanup(self, name):
        frappe.set_user("Administrator")
        frappe.db.delete("Fuel Consumption Ledger", {"source_type": "Fuel Request", "source_name": name})


class TestFuelLedgerSourceUniqueIndex(FrappeTestCase):
    """The fuel engine asserts a DB-level UNIQUE index on the ledger as its hard
    idempotency backstop (``fuel_engine.accrue_fuel_consumption`` docstring). The
    engine's application guard (``_ledger_exists`` check-then-insert) is not atomic,
    so two overlapping accrual runs could both pass the check and double-post the
    same source. This test proves the database itself rejects a duplicate
    ``(source_type, source_name)`` row, making the claimed backstop real and
    preventing silently-doubled ledgered consumption."""

    SOURCE_NAME = "FCL DUP TEST 1"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.vehicle = frappe.db.get_value("Salis Vehicle", {"plate_number": "FCL DUP 1"}, "name")
        if not cls.vehicle:
            cls.vehicle = frappe.get_doc({"doctype": "Salis Vehicle", "plate_number": "FCL DUP 1",
                                          "status": "Active"}).insert(ignore_permissions=True).name
        frappe.db.delete("Fuel Consumption Ledger",
                         {"source_type": "Fuel Daily Log", "source_name": cls.SOURCE_NAME})

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        if cls.vehicle and frappe.db.exists("Salis Vehicle", cls.vehicle):
            frappe.delete_doc("Salis Vehicle", cls.vehicle, force=True, ignore_permissions=True)
        super().tearDownClass()

    def tearDown(self):
        frappe.set_user("Administrator")
        frappe.db.delete("Fuel Consumption Ledger",
                         {"source_type": "Fuel Daily Log", "source_name": self.SOURCE_NAME})

    def _row(self):
        return {"doctype": "Fuel Consumption Ledger", "vehicle": self.vehicle,
                "period_month": frappe.utils.today()[:7], "litres": 10, "amount": 150,
                "source_type": "Fuel Daily Log", "source_name": self.SOURCE_NAME}

    def test_unique_constraint_exists_on_source_key(self):
        # [#93hyar]
        constraints = frappe.db.sql(
            """SELECT CONSTRAINT_NAME FROM information_schema.TABLE_CONSTRAINTS
               WHERE table_schema = DATABASE() AND table_name = %s
                 AND constraint_type = 'UNIQUE'""",
            ("tabFuel Consumption Ledger",),
            pluck=True,
        )
        self.assertIn(
            "unique_fcl_source", constraints,
            "Fuel Consumption Ledger must carry the unique_fcl_source UNIQUE index "
            "on (source_type, source_name) — the engine's claimed DB backstop.",
        )

    def test_duplicate_source_row_rejected_by_db(self):
        # [#icn3d4]
        frappe.get_doc(self._row()).insert(ignore_permissions=True)

        # [#53huw3]
        from pymysql.err import IntegrityError as MySQLIntegrityError

        with self.assertRaises((frappe.UniqueValidationError, MySQLIntegrityError)):
            frappe.db.sql(
                """INSERT INTO `tabFuel Consumption Ledger`
                       (name, vehicle, period_month, litres, amount, source_type, source_name)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                ("FCL-DUPRAW", self.vehicle, frappe.utils.today()[:7], 10, 150,
                 "Fuel Daily Log", self.SOURCE_NAME),
            )
        frappe.db.rollback()


class TestOperationsAlertAutoResolve(FrappeTestCase):
    """The alert resolver must close alerts whose source condition has cleared,
    leave still-valid alerts open, and be idempotent on re-run."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        # [#h7huot]
        cls.driver_ok = frappe.db.get_value("Salis Driver", {"full_name": "Resolve OK Driver"}, "name")
        if not cls.driver_ok:
            cls.driver_ok = frappe.get_doc({"doctype": "Salis Driver", "full_name": "Resolve OK Driver",
                                            "status": "Active"}).insert(ignore_permissions=True).name
        # [#amrby2]
        cls.driver_gap = frappe.db.get_value("Salis Driver", {"full_name": "Resolve Gap Driver"}, "name")
        if not cls.driver_gap:
            cls.driver_gap = frappe.get_doc({"doctype": "Salis Driver", "full_name": "Resolve Gap Driver",
                                             "status": "Active"}).insert(ignore_permissions=True).name
        # [#1wx0gi]
        cls.vehicle_inactive = frappe.db.get_value("Salis Vehicle", {"plate_number": "RESOLVE OFF 1"}, "name")
        if not cls.vehicle_inactive:
            cls.vehicle_inactive = frappe.get_doc({"doctype": "Salis Vehicle", "plate_number": "RESOLVE OFF 1",
                                                   "status": "Stopped"}).insert(ignore_permissions=True).name
        else:
            frappe.db.set_value("Salis Vehicle", cls.vehicle_inactive, "status", "Stopped")

        # [#nw7np8]
        if not frappe.db.exists("Driver Attendance",
                                {"driver": cls.driver_ok, "attendance_date": frappe.utils.today(),
                                 "docstatus": 1}):
            att = frappe.get_doc({"doctype": "Driver Attendance", "driver": cls.driver_ok,
                                  "attendance_date": frappe.utils.today(), "status": "Present"})
            att.insert(ignore_permissions=True)
            att.submit()

    def _open_alert(self, alert_type, severity, **subject):
        a = frappe.get_doc({
            "doctype": "Operations Alert",
            "alert_type": alert_type,
            "severity": severity,
            "status": "Open",
            "raised_on": frappe.utils.now_datetime(),
            "message": "test fixture alert",
            **subject,
        }).insert(ignore_permissions=True)
        return a.name

    def test_resolves_cleared_and_keeps_valid(self):
        # [#dmkpum]
        a_ok = self._open_alert("Supervisor Delay", "Info", driver=self.driver_ok)
        # [#g74tb2]
        a_gap = self._open_alert("Supervisor Delay", "Info", driver=self.driver_gap)
        # [#op7fpg]
        a_idle = self._open_alert("Idle Vehicle", "Info", vehicle=self.vehicle_inactive)
        for n in (a_ok, a_gap, a_idle):
            self.addCleanup(lambda n=n: self._cleanup(n))

        reconcile_operations_alerts()

        self.assertEqual(frappe.db.get_value("Operations Alert", a_ok, "status"), "Resolved",
                         "Attendance recorded -> Supervisor Delay must resolve.")
        self.assertEqual(frappe.db.get_value("Operations Alert", a_idle, "status"), "Resolved",
                         "Inactive vehicle -> Idle Vehicle must resolve.")
        self.assertEqual(frappe.db.get_value("Operations Alert", a_gap, "status"), "Open",
                         "Still-missing attendance -> Supervisor Delay must stay open.")

    def test_resolution_is_idempotent(self):
        a_idle = self._open_alert("Idle Vehicle", "Info", vehicle=self.vehicle_inactive)
        self.addCleanup(lambda: self._cleanup(a_idle))

        reconcile_operations_alerts()
        first = frappe.db.get_value("Operations Alert", a_idle, "status")

        # [#91dvdr]
        reconcile_operations_alerts()
        second = frappe.db.get_value("Operations Alert", a_idle, "status")

        self.assertEqual(first, "Resolved")
        self.assertEqual(second, "Resolved")

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        # [#7rytqe]
        if cls.driver_ok and frappe.db.exists("Salis Driver", cls.driver_ok):
            attendances = frappe.db.get_all(
                "Driver Attendance",
                filters={"driver": cls.driver_ok, "attendance_date": frappe.utils.today()},
                pluck="name",
            )
            for att_name in attendances:
                att_doc = frappe.get_doc("Driver Attendance", att_name)
                if att_doc.docstatus == 1:
                    att_doc.cancel()
                frappe.delete_doc("Driver Attendance", att_name, force=True, ignore_permissions=True)
            frappe.delete_doc("Salis Driver", cls.driver_ok, force=True, ignore_permissions=True)
        if cls.driver_gap and frappe.db.exists("Salis Driver", cls.driver_gap):
            frappe.delete_doc("Salis Driver", cls.driver_gap, force=True, ignore_permissions=True)
        if cls.vehicle_inactive and frappe.db.exists("Salis Vehicle", cls.vehicle_inactive):
            frappe.delete_doc("Salis Vehicle", cls.vehicle_inactive, force=True, ignore_permissions=True)
        super().tearDownClass()

    def _cleanup(self, name):
        frappe.set_user("Administrator")
        if frappe.db.exists("Operations Alert", name):
            frappe.delete_doc("Operations Alert", name, force=True, ignore_permissions=True)
