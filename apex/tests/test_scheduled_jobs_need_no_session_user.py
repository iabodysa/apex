# Copyright (c) 2026, AFMCO and contributors
"""The daily jobs must do their work without a privileged session user.

A scheduled job is handed Administrator by the framework and nothing else: the scheduler
tick connects the site (``frappe.connect`` sets Administrator), ``enqueue`` copies that
session user onto the queued job, and the worker calls ``frappe.set_user`` with it. Every
one of these four jobs writes with ``ignore_permissions`` precisely because of that — the
module docstrings say so in as many words — and a later reader who removes the flag would
break nothing visible on a desk and everything on the first cron run.

So the flag is only half the story, and asserting "session user is Administrator" would
assert the framework's behaviour rather than the app's. What is asserted here is the
property that MATTERS and that the app owns: run each job with a real signed-in operator
in the session instead, and it must still produce its record. A job that needs
Administrator specifically has a hidden dependency on who is logged in.

Two things make that assertion the only workable one. Each job isolates its rows in a
savepoint and swallows the exception into ``frappe.log_error``, so "did not raise" proves
nothing — only the record proves it. And each job reads through ``frappe.get_all``, which
does not check permissions, so a session user cannot narrow what the job sees; if the
record is missing, the WRITE was refused.

The operator is a Finance Manager: a real Apex role, a signed-in desk user, holding no
create or write on Cleaning Log, Occupancy Snapshot, Scheduled Task Instance or Fuel
Request, and holding no Fuel Request Workflow transition. Administrator would prove
nothing — it is exempt from the permission check and holds every role.
"""

import unittest

import frappe
from frappe.utils import add_days, today

from apex.habitat.tasks.cleaning import daily_cleaning_log_generator
from apex.habitat.tasks.occupancy import daily_occupancy_snapshot
from apex.habitat.tasks.scheduled_tasks import daily_scheduled_task_instance_generator
from apex.salis.tasks.fuel import unreverted_topup_watch
from apex.tests._helpers import _user, as_user
from apex.tests.factories import (
    default_company,
    make_building,
    make_driver_chain,
    make_room,
    make_vehicle,
    purge_doc,
)

OPERATOR = "a527.operator@example.com"
TAG = "A527"


class ScheduledJobCase(unittest.TestCase):
    """Runs one scheduled job as a signed-in operator and reports what it wrote."""

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cls.operator = _user(OPERATOR, "Finance Manager")

    def setUp(self):
        frappe.set_user("Administrator")
        self.addCleanup(frappe.set_user, "Administrator")

    def run_job(self, job):
        """Run ``job`` with the operator in the session; return the Error Logs it swallowed.

        The jobs catch per-row failures and log them, so the logs written during the run
        are the only account of what went wrong and belong in the failure message.
        """
        started = frappe.utils.now_datetime()
        with as_user(self.operator):
            self.assertNotEqual(
                frappe.session.user,
                "Administrator",
                "this job must be exercised as a real user, not Administrator",
            )
            job()
        frappe.set_user("Administrator")
        return frappe.get_all(
            "Error Log",
            filters={"creation": [">=", started]},
            fields=["method", "error"],
        )

    @staticmethod
    def explain(swallowed):
        """The swallowed failures, rendered for a failure message."""
        return "\n".join(f"{log.method}\n{log.error}" for log in swallowed) or "(nothing)"

    def assertWrote(self, doctype, filters, swallowed):
        rows = frappe.get_all(doctype, filters=filters, pluck="name")
        self.assertTrue(
            rows,
            f"{doctype} was not written with a signed-in operator in the session.\n"
            f"the job swallowed: {self.explain(swallowed)}",
        )
        return rows


class TestDailyCleaningLogGenerator(ScheduledJobCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.building = make_building(f"{TAG} Cleaning Building", company=default_company()).name
        make_room(cls.building, f"{TAG}-CLEAN-R01")

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        for name in frappe.get_all(
            "Cleaning Log", filters={"building": cls.building}, pluck="name"
        ):
            purge_doc("Cleaning Log", name)

    def test_writes_its_draft_log_for_a_signed_in_operator(self):
        swallowed = self.run_job(daily_cleaning_log_generator)
        self.assertWrote(
            "Cleaning Log",
            {"building": self.building, "cleaning_date": today()},
            swallowed,
        )


class TestDailyOccupancySnapshot(ScheduledJobCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.building = make_building(f"{TAG} Occupancy Building", company=default_company()).name
        make_room(cls.building, f"{TAG}-OCC-R01")

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        for name in frappe.get_all(
            "Occupancy Snapshot", filters={"building": cls.building}, pluck="name"
        ):
            purge_doc("Occupancy Snapshot", name)

    def test_writes_its_snapshot_for_a_signed_in_operator(self):
        swallowed = self.run_job(daily_occupancy_snapshot)
        self.assertWrote(
            "Occupancy Snapshot",
            {"building": self.building, "snapshot_date": today()},
            swallowed,
        )


class TestDailyScheduledTaskInstanceGenerator(ScheduledJobCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.building = make_building(f"{TAG} Scheduled Task Building", company=default_company()).name
        cls.catalog = frappe.get_doc(
            {
                "doctype": "Safety Task Catalog",
                "task_title": f"{TAG} Daily Check",
                "task_code": f"{TAG}-DC-01",
                "department": "Fire Safety",
                "frequency": "Daily",
            }
        ).insert(ignore_permissions=True).name
        cls.template = frappe.get_doc(
            {
                "doctype": "Scheduled Task Template",
                "template_name": f"{TAG} Daily Template",
                "frequency": "Daily",
                "is_active": 1,
                "template_items": [{"task_catalog": cls.catalog, "is_active": 1}],
            }
        ).insert(ignore_permissions=True).name
        cls.assignment = frappe.get_doc(
            {
                "doctype": "Scheduled Task Assignment",
                "template": cls.template,
                "building": cls.building,
                "effective_from": today(),
                "is_active": 1,
            }
        ).insert(ignore_permissions=True).name

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        for name in frappe.get_all(
            "Scheduled Task Instance", filters={"assignment": cls.assignment}, pluck="name"
        ):
            purge_doc("Scheduled Task Instance", name)
        purge_doc("Scheduled Task Assignment", cls.assignment)
        purge_doc("Scheduled Task Template", cls.template)
        purge_doc("Safety Task Catalog", cls.catalog)

    def test_writes_its_instance_for_a_signed_in_operator(self):
        swallowed = self.run_job(daily_scheduled_task_instance_generator)
        self.assertWrote(
            "Scheduled Task Instance",
            {"assignment": self.assignment, "due_date": today()},
            swallowed,
        )


class TestUnrevertedTopupWatch(ScheduledJobCase):
    """The Salis job: an overdue temporary top-up must be auto-reverted."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.vehicle = make_vehicle(f"{TAG}-TOPUP-1")
        cls.driver, _email = make_driver_chain(
            "a527.topup.driver@example.com", f"{TAG} Topup Driver"
        )
        cls.quota = frappe.get_doc(
            {
                "doctype": "Fuel Quota",
                "vehicle": cls.vehicle,
                "driver": cls.driver,
                "period_month": today()[:7],
                "monthly_litres": 500,
                "status": "Active",
                "company": default_company(),
            }
        ).insert(ignore_permissions=True).name

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        for name in frappe.get_all(
            "Fuel Request", filters={"fuel_quota": cls.quota}, pluck="name"
        ):
            purge_doc("Fuel Request", name)
        purge_doc("Fuel Quota", cls.quota)

    def _overdue_topup(self, status):
        """An overdue temporary top-up parked at ``status``.

        The row is landed at its terminal state by direct column writes rather than by
        driving the workflow: the state is this test's PRECONDITION, and driving it
        through the desk would need the very role whose absence is the subject.
        """
        doc = frappe.get_doc(
            {
                "doctype": "Fuel Request",
                "request_type": "Top-up",
                "vehicle": self.vehicle,
                "driver": self.driver,
                "fuel_quota": self.quota,
                "topup_litres": 20,
                "is_temporary": 1,
                "revert_due_date": add_days(today(), -3),
                "status": "Pending",
            }
        ).insert(ignore_permissions=True)
        frappe.db.set_value(
            "Fuel Request",
            doc.name,
            {"status": status, "docstatus": 1},
            update_modified=False,
        )
        self.addCleanup(purge_doc, "Fuel Request", doc.name)
        return doc.name

    def test_reverts_an_overdue_done_topup_for_a_signed_in_operator(self):
        name = self._overdue_topup("Done")
        swallowed = self.run_job(unreverted_topup_watch)
        self.assertEqual(
            frappe.db.get_value("Fuel Request", name, "reverted"),
            1,
            f"{name} was not auto-reverted with a signed-in operator in the session.\n"
            f"the job swallowed: {self.explain(swallowed)}",
        )


if __name__ == "__main__":
    unittest.main()
