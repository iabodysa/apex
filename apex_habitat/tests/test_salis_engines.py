"""Idempotency tests for the Salis background engines: re-running a daily/weekly
job must never double-post its ledger/snapshot rows."""

import unittest

import frappe

from apex_habitat.salis.fuel_engine import accrue_fuel_consumption, monthly_fuel_reconciliation
from apex_habitat.salis.rental_engine import daily_rental_accrual
from apex_habitat.salis.tasks import reconcile_operations_alerts
from apex_habitat.salis.utilisation_engine import weekly_vehicle_utilisation_snapshot


class TestRentalAccrualIdempotency(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
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
        frappe.db.commit()

    def test_accrual_is_idempotent(self):
        today = frappe.utils.today()
        frappe.db.delete("Rental Accrual Ledger", {"vehicle": self.vehicle, "accrual_date": today})
        frappe.db.commit()
        daily_rental_accrual()
        frappe.db.commit()
        first = frappe.db.count("Rental Accrual Ledger", {"vehicle": self.vehicle, "accrual_date": today})
        daily_rental_accrual()
        frappe.db.commit()
        second = frappe.db.count("Rental Accrual Ledger", {"vehicle": self.vehicle, "accrual_date": today})
        self.assertEqual(first, 1)
        self.assertEqual(second, 1)


class TestUtilisationSnapshotIdempotency(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cls.vehicle = frappe.db.get_value("Salis Vehicle", {"plate_number": "UTIL ENG 1"}, "name")
        if not cls.vehicle:
            cls.vehicle = frappe.get_doc({"doctype": "Salis Vehicle", "plate_number": "UTIL ENG 1",
                                          "status": "Active"}).insert(ignore_permissions=True).name
        frappe.db.commit()

    def test_snapshot_is_idempotent(self):
        today = frappe.utils.today()
        frappe.db.delete("Vehicle Utilisation Snapshot", {"vehicle": self.vehicle, "snapshot_date": today})
        frappe.db.commit()
        weekly_vehicle_utilisation_snapshot()
        frappe.db.commit()
        first = frappe.db.count("Vehicle Utilisation Snapshot", {"vehicle": self.vehicle, "snapshot_date": today})
        weekly_vehicle_utilisation_snapshot()
        frappe.db.commit()
        second = frappe.db.count("Vehicle Utilisation Snapshot", {"vehicle": self.vehicle, "snapshot_date": today})
        self.assertEqual(first, 1)
        self.assertEqual(second, 1)


class TestFuelReconciliationNoDuplicateAlert(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
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
        frappe.db.commit()

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
        frappe.db.commit()
        monthly_fuel_reconciliation()
        frappe.db.commit()
        first = self._count()
        monthly_fuel_reconciliation()
        frappe.db.commit()
        second = self._count()
        self.assertEqual(first, 1)
        self.assertEqual(second, 1)


class TestFuelAccrualLateDone(unittest.TestCase):
    """Regression: a Fuel Request created earlier that only flips to Done today
    (or any later day) must still be ledgered. The old window keyed accrual on
    ``request_date in [yesterday, today]`` AND status=Done, so a request with an
    old request_date that completes now was silently skipped and its litres
    vanished. Accrual is now driven off the un-ledgered Done set regardless of
    request_date, stamping a ``ledgered`` flag."""

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cls.vehicle = frappe.db.get_value("Salis Vehicle", {"plate_number": "FUEL LATE 1"}, "name")
        if not cls.vehicle:
            cls.vehicle = frappe.get_doc({"doctype": "Salis Vehicle", "plate_number": "FUEL LATE 1",
                                          "status": "Active"}).insert(ignore_permissions=True).name
        frappe.db.commit()

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
                doc.db_set("requested_by", "Guest")  # any user != the Administrator driver
                doc.reload()
            apply_workflow(doc, "Approve")  # Pending -> Approved (submits)
            doc.reload()
            apply_workflow(doc, "Complete")  # Approved -> Done (post-submit)
        else:
            doc.status = "Approved"
            doc.save(ignore_permissions=True)
            doc.status = "Done"
            doc.save(ignore_permissions=True)
            doc.submit()
        frappe.db.commit()
        return doc.name

    def test_late_done_request_is_ledgered(self):
        from frappe.utils import add_days, today

        old_date = add_days(today(), -10)  # well outside the old [yesterday, today] window
        name = self._make_done_request(old_date)
        self.addCleanup(lambda: self._cleanup(name))

        # Pre-state: not yet ledgered, no ledger row.
        self.assertEqual(frappe.db.get_value("Fuel Request", name, "ledgered"), 0)
        frappe.db.delete("Fuel Consumption Ledger", {"source_type": "Fuel Request", "source_name": name})
        frappe.db.commit()

        accrue_fuel_consumption()
        frappe.db.commit()

        rows = frappe.db.count("Fuel Consumption Ledger",
                               {"source_type": "Fuel Request", "source_name": name})
        self.assertEqual(rows, 1, "Late-Done request must be ledgered despite its old request_date.")
        self.assertEqual(frappe.db.get_value("Fuel Request", name, "ledgered"), 1,
                         "Request must be flagged ledgered after accrual.")

        # Idempotent: a second run must not double-post.
        accrue_fuel_consumption()
        frappe.db.commit()
        rows_again = frappe.db.count("Fuel Consumption Ledger",
                                     {"source_type": "Fuel Request", "source_name": name})
        self.assertEqual(rows_again, 1, "Re-running accrual must not double-ledger.")

    def _cleanup(self, name):
        frappe.set_user("Administrator")
        frappe.db.delete("Fuel Consumption Ledger", {"source_type": "Fuel Request", "source_name": name})
        frappe.db.commit()


class TestOperationsAlertAutoResolve(unittest.TestCase):
    """The alert resolver must close alerts whose source condition has cleared,
    leave still-valid alerts open, and be idempotent on re-run."""

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        # A driver WITH attendance today (Supervisor Delay should clear).
        cls.driver_ok = frappe.db.get_value("Salis Driver", {"full_name": "Resolve OK Driver"}, "name")
        if not cls.driver_ok:
            cls.driver_ok = frappe.get_doc({"doctype": "Salis Driver", "full_name": "Resolve OK Driver",
                                            "status": "Active"}).insert(ignore_permissions=True).name
        # A driver WITHOUT attendance today (Supervisor Delay should stay open).
        cls.driver_gap = frappe.db.get_value("Salis Driver", {"full_name": "Resolve Gap Driver"}, "name")
        if not cls.driver_gap:
            cls.driver_gap = frappe.get_doc({"doctype": "Salis Driver", "full_name": "Resolve Gap Driver",
                                             "status": "Active"}).insert(ignore_permissions=True).name
        # An INACTIVE vehicle (Idle Vehicle should clear — no longer Active).
        cls.vehicle_inactive = frappe.db.get_value("Salis Vehicle", {"plate_number": "RESOLVE OFF 1"}, "name")
        if not cls.vehicle_inactive:
            cls.vehicle_inactive = frappe.get_doc({"doctype": "Salis Vehicle", "plate_number": "RESOLVE OFF 1",
                                                   "status": "Stopped"}).insert(ignore_permissions=True).name
        else:
            frappe.db.set_value("Salis Vehicle", cls.vehicle_inactive, "status", "Stopped")

        # Attendance today for driver_ok.
        if not frappe.db.exists("Driver Attendance",
                                {"driver": cls.driver_ok, "attendance_date": frappe.utils.today(),
                                 "docstatus": 1}):
            att = frappe.get_doc({"doctype": "Driver Attendance", "driver": cls.driver_ok,
                                  "attendance_date": frappe.utils.today(), "status": "Present"})
            att.insert(ignore_permissions=True)
            att.submit()
        frappe.db.commit()

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
        # Supervisor Delay for a driver who DOES have attendance -> should resolve.
        a_ok = self._open_alert("Supervisor Delay", "Info", driver=self.driver_ok)
        # Supervisor Delay for a driver WITHOUT attendance -> should stay open.
        a_gap = self._open_alert("Supervisor Delay", "Info", driver=self.driver_gap)
        # Idle Vehicle for an inactive vehicle -> should resolve.
        a_idle = self._open_alert("Idle Vehicle", "Info", vehicle=self.vehicle_inactive)
        for n in (a_ok, a_gap, a_idle):
            self.addCleanup(lambda n=n: self._cleanup(n))
        frappe.db.commit()

        reconcile_operations_alerts()
        frappe.db.commit()

        self.assertEqual(frappe.db.get_value("Operations Alert", a_ok, "status"), "Resolved",
                         "Attendance recorded -> Supervisor Delay must resolve.")
        self.assertEqual(frappe.db.get_value("Operations Alert", a_idle, "status"), "Resolved",
                         "Inactive vehicle -> Idle Vehicle must resolve.")
        self.assertEqual(frappe.db.get_value("Operations Alert", a_gap, "status"), "Open",
                         "Still-missing attendance -> Supervisor Delay must stay open.")

    def test_resolution_is_idempotent(self):
        a_idle = self._open_alert("Idle Vehicle", "Info", vehicle=self.vehicle_inactive)
        self.addCleanup(lambda: self._cleanup(a_idle))
        frappe.db.commit()

        reconcile_operations_alerts()
        frappe.db.commit()
        first = frappe.db.get_value("Operations Alert", a_idle, "status")

        # Second run must not error and must leave the already-Resolved alert as-is.
        reconcile_operations_alerts()
        frappe.db.commit()
        second = frappe.db.get_value("Operations Alert", a_idle, "status")

        self.assertEqual(first, "Resolved")
        self.assertEqual(second, "Resolved")

    def _cleanup(self, name):
        frappe.set_user("Administrator")
        if frappe.db.exists("Operations Alert", name):
            frappe.delete_doc("Operations Alert", name, force=True, ignore_permissions=True)
        frappe.db.commit()
