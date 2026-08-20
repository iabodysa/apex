# Copyright (c) 2026, afmcoltd

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.doctype.fuel_request.fuel_request import FuelRequest
from frappe.model.workflow import apply_workflow, get_transitions, get_workflow_name
from apex.tests._helpers import _user
from apex.tests.factories import make_project, make_vehicle, purge_doc
from frappe.utils import add_days, today
from apex.salis.utils import (
    raise_rider_clearance_task,
    rider_block_reason,
)
from apex.tests import factories


class TestFuelRequest(FrappeTestCase):
    def test_explicit_blank_request_type_is_not_silently_defaulted(self):
        request = FuelRequest(
            {
                "doctype": "Fuel Request",
                "request_type": "Standard",
                "status": "Pending",
                "requested_by": "Administrator",
            }
        )
        request.request_type = None

        with (
            patch.object(FuelRequest, "_validate_standard"),
            patch.object(FuelRequest, "_enforce_rider_active"),
            patch.object(FuelRequest, "_guard_initial_status"),
            patch.object(FuelRequest, "_stamp_approver"),
            self.assertRaisesRegex(frappe.ValidationError, "Invalid Request Type"),
        ):
            request.validate()

test_ignore = ['Employee', 'Company', 'Project', 'Salis Vehicle', 'Salis Driver', 'User', 'Role', 'Leave Application', 'Leave Type', 'Holiday List']


# --- merged from test_fuel_request_workflow.py ---
WORKFLOW = "Fuel Request Workflow"
def _actions(doc):
    """The set of workflow action names currently available to the session user."""
    return {t.action for t in get_transitions(doc)}
class TestFuelRequestWorkflow(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # mandatory Salis workflow (salis_workflow_seed, every install/migrate);
        # absence is a regression - FAIL, never skip.
        if get_workflow_name("Fuel Request") != WORKFLOW:
            raise AssertionError(
                f"Mandatory Salis workflow {WORKFLOW!r} not active for "
                "'Fuel Request' (salis_workflow_seed regression)"
            )
        frappe.set_user("Administrator")
        cls.requester = _user("frwf_req@example.com", "Fleet Project Manager")
        cls.manager = _user("frwf_mgr@example.com", "Fleet Manager")
        cls.manager_maker = _user("frwf_mgrmaker@example.com", "Fleet Manager")
        frappe.get_doc("User", cls.manager_maker).add_roles("Fleet Project Manager")
        cls.project = make_project("FR Workflow Project")
        cls.vehicle = make_vehicle("FR-WF-1")
        for u in (cls.requester, cls.manager, cls.manager_maker):
            if not frappe.db.exists(
                "User Permission", {"user": u, "allow": "Project", "for_value": cls.project}
            ):
                frappe.get_doc({
                    "doctype": "User Permission",
                    "user": u,
                    "allow": "Project",
                    "for_value": cls.project,
                }).insert(ignore_permissions=True)

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        for u in (cls.requester, cls.manager, cls.manager_maker):
            frappe.db.delete("User Permission",
                {"user": u, "allow": "Project", "for_value": cls.project})
        if frappe.db.exists("Salis Vehicle", cls.vehicle):
            frappe.delete_doc("Salis Vehicle", cls.vehicle, ignore_permissions=True, force=True)
        if frappe.db.exists("Project", cls.project):
            frappe.delete_doc("Project", cls.project, ignore_permissions=True, force=True)
        frappe.db.commit()
        super().tearDownClass()

    def setUp(self):
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")


    def _quota(self, monthly_litres=100):
        """A fresh Active Fuel Quota for the test vehicle/project."""
        q = frappe.get_doc({
            "doctype": "Fuel Quota",
            "vehicle": self.vehicle,
            "project": self.project,
            "period_month": "2026-05",
            "monthly_litres": monthly_litres,
            "consumed_litres": 0,
            "status": "Active",
        }).insert(ignore_permissions=True)
        self.addCleanup(lambda: self._purge_quota(q.name))
        return q

    def _new(self, request_type, requested_by=None, **overrides):
        """A draft Fuel Request at Pending, stamped to ``requested_by`` (defaults
		to the standard requester). Inserted as Administrator so ``owner`` is
		Administrator and the SoD gate is exercised purely via requested_by."""
        data = {
            "doctype": "Fuel Request",
            "request_type": request_type,
            "vehicle": self.vehicle,
            "project": self.project,
            "requested_by": requested_by or self.requester,
            "status": "Pending",
        }
        data.update(overrides)
        doc = frappe.get_doc(data).insert(ignore_permissions=True)
        self.addCleanup(lambda: purge_doc("Fuel Request", doc.name))
        return doc

    @staticmethod
    def _purge_quota(name):
        frappe.set_user("Administrator")
        if frappe.db.exists("Fuel Quota", name):
            frappe.delete_doc("Fuel Quota", name, ignore_permissions=True, force=True)


    def test_workflow_is_seeded_and_active(self):
        self.assertEqual(get_workflow_name("Fuel Request"), WORKFLOW)
        self.assertTrue(frappe.db.get_value("Workflow", WORKFLOW, "is_active"))
        self.assertEqual(
            frappe.db.get_value("Workflow", WORKFLOW, "workflow_state_field"), "status"
        )


    def test_standard_post_submit_pending_approved_done(self):
        fr = self._new("Standard", requested_litres=8, amount=120)
        self.assertEqual(fr.docstatus, 0)

        frappe.set_user(self.manager)
        self.assertIn("Approve", _actions(fr))
        apply_workflow(fr, "Approve")
        fr.reload()
        self.assertEqual(fr.status, "Approved")
        self.assertEqual(fr.docstatus, 1)
        self.assertEqual(fr.approved_by, self.manager)

        self.assertIn("Complete", _actions(fr))
        apply_workflow(fr, "Complete")
        fr.reload()
        self.assertEqual(fr.status, "Done")
        self.assertEqual(fr.docstatus, 1)

    def test_topup_post_submit_then_revert(self):
        # A Top-up raises the ceiling of a specific allocation, so
        # FuelRequest._validate_topup refuses one that names no Fuel Quota.
        q = self._quota()
        fr = self._new(
            "Top-up", topup_litres=12, is_temporary=1,
            revert_due_date=frappe.utils.add_days(frappe.utils.today(), -2),
            fuel_quota=q.name,
        )
        frappe.set_user(self.manager)
        apply_workflow(fr, "Approve")
        fr.reload()
        apply_workflow(fr, "Complete")
        fr.reload()
        self.assertEqual(fr.status, "Done")
        self.assertEqual(fr.docstatus, 1)

        self.assertIn("Revert", _actions(fr))
        apply_workflow(fr, "Revert")
        fr.reload()
        self.assertEqual(fr.status, "Reverted")
        self.assertEqual(fr.docstatus, 1)

    def test_chip_post_submit_pending_approved_done(self):
        fr = self._new("Chip", action="Issue", chip_number="CHIP-WF-A")
        frappe.set_user(self.manager)
        apply_workflow(fr, "Approve")
        fr.reload()
        self.assertEqual(fr.status, "Approved")
        self.assertEqual(fr.docstatus, 1)
        apply_workflow(fr, "Complete")
        fr.reload()
        self.assertEqual(fr.status, "Done")
        self.assertEqual(fr.docstatus, 1)


    def test_sod_requester_cannot_approve(self):
        fr = self._new("Standard", requested_by=self.manager_maker, requested_litres=5)

        frappe.set_user(self.manager_maker)
        self.assertNotIn("Approve", _actions(fr))
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(fr, "Approve")

        frappe.set_user(self.manager)
        self.assertIn("Approve", _actions(fr))
        apply_workflow(fr, "Approve")
        fr.reload()
        self.assertEqual(fr.status, "Approved")


    def test_revert_is_topup_only(self):
        """A Standard request, once Done, is NOT offered Revert (Top-up only)."""
        fr = self._new("Standard", requested_litres=4, amount=60)
        frappe.set_user(self.manager)
        apply_workflow(fr, "Approve")
        fr.reload()
        apply_workflow(fr, "Complete")
        fr.reload()
        self.assertEqual(fr.status, "Done")
        self.assertNotIn("Revert", _actions(fr))

    def test_mark_failed_is_standard_only(self):
        """A Chip request, once Approved, is NOT offered Mark Failed (Standard
		only); a Standard request IS."""
        chip = self._new("Chip", action="Issue", chip_number="CHIP-WF-B")
        frappe.set_user(self.manager)
        apply_workflow(chip, "Approve")
        chip.reload()
        self.assertNotIn("Mark Failed", _actions(chip))

        frappe.set_user("Administrator")
        std = self._new("Standard", requested_litres=6, amount=90)
        frappe.set_user(self.manager)
        apply_workflow(std, "Approve")
        std.reload()
        self.assertIn("Mark Failed", _actions(std))
        apply_workflow(std, "Mark Failed")
        std.reload()
        self.assertEqual(std.status, "Failed")
        self.assertEqual(std.docstatus, 1)


    def test_standard_quota_applied_on_post_submit_done(self):
        q = self._quota()
        fr = self._new("Standard", requested_litres=8, amount=120, fuel_quota=q.name)

        frappe.set_user(self.manager)
        apply_workflow(fr, "Approve")
        fr.reload()
        self.assertEqual(fr.quota_applied, 0)
        self.assertEqual(frappe.db.get_value("Fuel Quota", q.name, "consumed_litres"), 0)

        apply_workflow(fr, "Complete")
        fr.reload()
        self.assertEqual(fr.status, "Done")
        self.assertEqual(fr.quota_applied, 1)
        self.assertEqual(frappe.db.get_value("Fuel Quota", q.name, "consumed_litres"), 8)

        frappe.set_user(self.manager)
        apply_workflow(fr, "Cancel")
        fr.reload()
        self.assertEqual(fr.status, "Cancelled")
        self.assertEqual(fr.docstatus, 2)
        self.assertEqual(frappe.db.get_value("Fuel Quota", q.name, "consumed_litres"), 0)

    def test_exhausted_quota_blocks_a_second_standard_draw(self):
        """An Exhausted quota must refuse the next Standard draw instead of letting
		it approve and overrun the allocation. Top-up is the sanctioned way to add
		fuel beyond the quota, so it must stay approvable against the same quota."""
        q = self._quota(monthly_litres=10)

        first = self._new("Standard", requested_litres=10, amount=150, fuel_quota=q.name)
        frappe.set_user(self.manager)
        apply_workflow(first, "Approve")
        first.reload()
        apply_workflow(first, "Complete")
        first.reload()
        self.assertEqual(first.status, "Done")
        self.assertEqual(frappe.db.get_value("Fuel Quota", q.name, "consumed_litres"), 10)
        self.assertEqual(frappe.db.get_value("Fuel Quota", q.name, "status"), "Exhausted")

        # The exhausted quota must refuse the next Standard draw and stay at 10 L.
        frappe.set_user("Administrator")
        second = self._new("Standard", requested_litres=5, amount=75, fuel_quota=q.name)
        frappe.set_user(self.manager)
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(second, "Approve")
        self.assertEqual(frappe.db.get_value("Fuel Quota", q.name, "consumed_litres"), 10)
        self.assertEqual(frappe.db.get_value("Fuel Request", second.name, "docstatus"), 0)
        self.assertEqual(frappe.db.get_value("Fuel Request", second.name, "quota_applied"), 0)

        # A Top-up against the very same exhausted quota still goes through.
        frappe.set_user("Administrator")
        topup = self._new("Top-up", topup_litres=5, fuel_quota=q.name)
        frappe.set_user(self.manager)
        apply_workflow(topup, "Approve")
        topup.reload()
        apply_workflow(topup, "Complete")
        topup.reload()
        self.assertEqual(topup.status, "Done")
        self.assertEqual(topup.docstatus, 1)
        # A Top-up posts no quota consumption, so the quota is untouched.
        self.assertEqual(frappe.db.get_value("Fuel Quota", q.name, "consumed_litres"), 10)

    def test_oversized_first_standard_draw_is_refused(self):
        """A FIRST draw larger than the whole allocation must be refused too.

		The exhaustion test alone cannot see this one: 15 L against a 10 L quota
		with nothing consumed satisfies ``consumed < monthly``, so the request used
		to approve, complete, and push consumed_litres to 15 — a silent 5 L overrun
		that only a msgprint on the quota ever mentioned. Top-up is the sanctioned
		way to draw beyond the allocation, so the same 15 L as a Top-up must still
		go through."""
        q = self._quota(monthly_litres=10)

        oversized = self._new("Standard", requested_litres=15, amount=225, fuel_quota=q.name)
        frappe.set_user(self.manager)
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(oversized, "Approve")

        # Refused before submit: nothing consumed, nothing submitted, no flag set.
        self.assertEqual(frappe.db.get_value("Fuel Quota", q.name, "consumed_litres"), 0)
        self.assertEqual(frappe.db.get_value("Fuel Quota", q.name, "status"), "Active")
        self.assertEqual(frappe.db.get_value("Fuel Request", oversized.name, "docstatus"), 0)
        self.assertEqual(frappe.db.get_value("Fuel Request", oversized.name, "quota_applied"), 0)

        # The same size as a Top-up is the sanctioned route and stays open.
        frappe.set_user("Administrator")
        topup = self._new("Top-up", topup_litres=15, fuel_quota=q.name)
        frappe.set_user(self.manager)
        apply_workflow(topup, "Approve")
        topup.reload()
        apply_workflow(topup, "Complete")
        topup.reload()
        self.assertEqual(topup.status, "Done")
        self.assertEqual(topup.docstatus, 1)
        self.assertEqual(frappe.db.get_value("Fuel Quota", q.name, "consumed_litres"), 0)

    def test_two_in_flight_draws_cannot_jointly_overrun_the_quota(self):
        """Each draw fits alone, both approve, and the second is caught at Complete.

		This is why the gate is re-checked inside the locked consumption step and
		not only before submit: at Approve time both 6 L requests fit the 10 L
		allocation, and only the authoritative read after the first one posts can
		see that the second would overrun. Asserted on the SIDE EFFECT
		(consumed_litres / quota_applied), never on the status field — Frappe writes
		the row before ``on_update_after_submit`` runs, so the status is not
		evidence of whether the hook refused."""
        q = self._quota(monthly_litres=10)

        first = self._new("Standard", requested_litres=6, amount=90, fuel_quota=q.name)
        second = self._new("Standard", requested_litres=6, amount=90, fuel_quota=q.name)

        frappe.set_user(self.manager)
        apply_workflow(first, "Approve")
        first.reload()
        apply_workflow(second, "Approve")
        second.reload()
        # Both fit the allocation on their own, so both reach Approved.
        self.assertEqual(first.docstatus, 1)
        self.assertEqual(second.docstatus, 1)

        apply_workflow(first, "Complete")
        first.reload()
        self.assertEqual(first.status, "Done")
        self.assertEqual(frappe.db.get_value("Fuel Quota", q.name, "consumed_litres"), 6)

        # 6 + 6 > 10: the locked read refuses the second draw at Complete.
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(second, "Complete")
        self.assertEqual(frappe.db.get_value("Fuel Quota", q.name, "consumed_litres"), 6)
        self.assertEqual(frappe.db.get_value("Fuel Request", second.name, "quota_applied"), 0)


# --- merged from test_rider_leave_guard.py ---
def _driver(full_name, status="Active", employee=None, supervisor=None, project=None):
    """Get-or-create a Salis Driver carrying ``status``.

    The status is written with ``frappe.db.set_value`` rather than through the
    document, because ``SalisDriver._refuse_a_hand_written_status`` forces a new
    record to Active and refuses a change on save — a value passed to ``insert``
    silently becomes Active and the guard under test is then never reached.
    """
    name = frappe.db.get_value("Salis Driver", {"full_name": full_name}, "name")
    if not name:
        name = frappe.get_doc(
            {
                "doctype": "Salis Driver",
                "full_name": full_name,
                "employee": employee,
                "supervisor": supervisor,
                "project": project,
            }
        ).insert(ignore_permissions=True).name
    frappe.db.set_value(
        "Salis Driver",
        name,
        {"status": status, "employee": employee, "supervisor": supervisor, "project": project},
    )
    return name
def _unpaid_leave_type():
    """A Leave Without Pay type: ``is_lwp`` skips the HRMS balance check, so the
    application needs no Leave Allocation standing behind it."""
    name = "T119 Unpaid Leave"
    if not frappe.db.exists("Leave Type", name):
        frappe.get_doc(
            {"doctype": "Leave Type", "leave_type_name": name, "is_lwp": 1}
        ).insert(ignore_permissions=True)
    return name
def _empty_holiday_list():
    """A Holiday List spanning the test window with no holidays in it.

    HRMS refuses an application whose every day is a holiday, and
    ``create_leave_ledger_entry`` resolves the employee's holiday list on submit
    with ``raise_exception=True``, so the employee needs one that exists.
    """
    name = "T119 No Holidays"
    if not frappe.db.exists("Holiday List", name):
        frappe.get_doc(
            {
                "doctype": "Holiday List",
                "holiday_list_name": name,
                "from_date": add_days(today(), -730),
                "to_date": add_days(today(), 730),
            }
        ).insert(ignore_permissions=True)
    return name
def _supervisor_user():
    """An enabled user holding Fleet Supervisor, to receive the clearance task."""
    email = "t119_sup@example.com"
    if not frappe.db.exists("User", email):
        u = frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": "T119 Sup",
                "send_welcome_email": 0,
            }
        ).insert(ignore_permissions=True)
    else:
        u = frappe.get_doc("User", email)
    if "Fleet Supervisor" not in frappe.get_roles(email):
        u.add_roles("Fleet Supervisor")
    return email
def _project_scoped_supervisor(email, project):
    """A Fleet Supervisor user permitted only on ``project`` by User Permission;
    returns the login email. The permission is a fixture, kept for the whole
    module rather than deleted per test, matching ``_supervisor_user``."""
    if not frappe.db.exists("User", email):
        u = frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": email.split("@")[0],
                "send_welcome_email": 0,
            }
        ).insert(ignore_permissions=True)
    else:
        u = frappe.get_doc("User", email)
    if "Fleet Supervisor" not in frappe.get_roles(email):
        u.add_roles("Fleet Supervisor")
    if not frappe.db.exists(
        "User Permission", {"user": email, "allow": "Project", "for_value": project}
    ):
        frappe.get_doc(
            {
                "doctype": "User Permission",
                "user": email,
                "allow": "Project",
                "for_value": project,
            }
        ).insert(ignore_permissions=True)
    return email
def _open_clearance_todos(driver):
    return frappe.get_all(
        "ToDo",
        filters={
            "reference_type": "Salis Driver",
            "reference_name": driver,
            "status": "Open",
        },
        pluck="name",
    )
class TestRiderLeaveGuard(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.supervisor = _supervisor_user()
        self.project = factories.make_project("T119 Rider Guard Project")
        self.other_project = factories.make_project("T119 Rider Guard Other Project")

    def tearDown(self):
        frappe.set_user("Administrator")


    def test_active_rider_is_not_blocked(self):
        driver = _driver("T119 Active Rider", status="Active")
        self.assertIsNone(
            rider_block_reason(driver),
            "An Active rider with no leave must not be blocked.",
        )

    def test_local_driver_status_blocks(self):
        """Stopped and Released are the whole blocking set the master can hold —
        the Select carries only Active / Stopped / Released."""
        for status in ("Stopped", "Released"):
            driver = _driver(f"T119 {status} Rider", status=status)
            reason = rider_block_reason(driver)
            self.assertTrue(
                reason,
                f"A rider whose Salis Driver status is {status} must be blocked.",
            )

    def test_approved_leave_blocks_an_active_rider(self):
        """The leave source, reached the way the app reads it: the driver stays
        Active and the block comes from the approved HRMS Leave Application."""
        emp = self._employee_on_leave("T119 Leave Emp")
        driver = _driver("T119 Leave Rider", status="Active", employee=emp)
        reason = rider_block_reason(driver)
        self.assertTrue(
            reason, "A rider on approved leave today must be blocked."
        )

    def test_inactive_employee_blocks_when_hrms_present(self):
        """A rider whose HRMS Employee has Left must be blocked.

 hrms and erpnext are both in hooks.required_apps, so Employee is
        always installed wherever apex is. The old ``skipTest`` on its absence made
        this the one rider-block source that CI never actually exercised.
        """
        self.assertTrue(
            frappe.db.exists("DocType", "Employee"),
            "Employee must be installed — hrms is a required app",
        )
        emp = self._left_employee("T119 Left Emp")
        driver = _driver("T119 EmpLeft Rider", status="Active", employee=emp)
        reason = rider_block_reason(driver)
        self.assertTrue(
            reason, "A rider linked to a Left Employee must be blocked."
        )


    def test_fuel_request_rejected_for_onleave_rider(self):
        """The rejection, and the clearance task that must OUTLIVE it.

        In production the controller throws, and ``app.py`` rolls the whole request
        transaction back with it, so a ToDo inserted inline is created and discarded in
        the same breath — never reaching a supervisor. The clearance task is therefore
        raised via ``frappe.enqueue``, which puts it outside the transaction, so this
        case grades the hand-off rather than a row that only a test's own uncommitted
        transaction can see.
        """
        emp = self._employee_on_leave("T119 Fuel OnLeave Emp")
        driver = _driver(
            "T119 Fuel OnLeave", status="Active", employee=emp, supervisor=self.supervisor
        )
        vehicle = factories.make_vehicle("T119-FUEL-1")
        fr = frappe.get_doc(
            {
                "doctype": "Fuel Request",
                "request_type": "Standard",
                "vehicle": vehicle,
                "driver": driver,
                "request_date": today(),
                "requested_litres": 40,
                "status": "Pending",
            }
        )
        with patch.object(frappe, "enqueue") as enqueue:
            with self.assertRaises(frappe.ValidationError):
                fr.insert(ignore_permissions=True)

        enqueue.assert_called_once()
        self.assertEqual(
            enqueue.call_args.args[0], "apex.salis.utils.raise_rider_clearance_task"
        )
        self.assertEqual(enqueue.call_args.kwargs["driver"], driver)
        self.assertFalse(
            _open_clearance_todos(driver),
            "the task was written inside the transaction the throw discards",
        )
        self.addCleanup(lambda: self._purge_todos(driver))

    def test_the_enqueued_task_still_reaches_the_supervisor(self):
        """The other half: the job the endpoint hands off must do what it promises."""
        driver = _driver(
            "T119 Fuel Handoff", status="Stopped", supervisor=self.supervisor
        )

        raise_rider_clearance_task(driver, vehicle=None)

        allocated = frappe.get_all(
            "ToDo",
            filters={"reference_type": "Salis Driver", "reference_name": driver, "status": "Open"},
            pluck="allocated_to",
        )
        self.assertIn(self.supervisor, allocated)
        self.addCleanup(lambda: self._purge_todos(driver))

    def test_role_fallback_skips_a_supervisor_scoped_to_another_project(self):
        """No per-record supervisor: the Fleet Supervisor role fallback must still
        respect project scope, or an out-of-scope supervisor gets a task whose
        link they cannot open."""
        in_scope = _project_scoped_supervisor("t119_in_scope@example.com", self.project)
        out_of_scope = _project_scoped_supervisor(
            "t119_out_of_scope@example.com", self.other_project
        )
        driver = _driver("T119 Role Fallback", status="Stopped", project=self.project)

        raise_rider_clearance_task(driver, vehicle=None)

        allocated = frappe.get_all(
            "ToDo",
            filters={"reference_type": "Salis Driver", "reference_name": driver, "status": "Open"},
            pluck="allocated_to",
        )
        self.assertIn(in_scope, allocated)
        self.assertNotIn(out_of_scope, allocated)
        self.addCleanup(lambda: self._purge_todos(driver))

    def test_vehicle_assignment_rejected_for_inactive_rider(self):
        driver = _driver("T119 VA Stopped", status="Stopped")
        vehicle = factories.make_vehicle("T119-VA-1")
        va = frappe.get_doc(
            {
                "doctype": "Vehicle Assignment",
                "vehicle": vehicle,
                "driver": driver,
                "start_date": today(),
                "status": "Active",
            }
        )
        with self.assertRaises(frappe.ValidationError):
            va.insert(ignore_permissions=True)

    def test_vehicle_handover_rejected_when_to_driver_onleave(self):
        good = _driver("T119 HO From", status="Active")
        on_leave = _driver(
            "T119 HO To OnLeave",
            status="Active",
            employee=self._employee_on_leave("T119 HO OnLeave Emp"),
        )
        vehicle = factories.make_vehicle("T119-HO-1")
        ho = frappe.get_doc(
            {
                "doctype": "Vehicle Handover",
                "vehicle": vehicle,
                "from_driver": good,
                "to_driver": on_leave,
                "handover_date": today(),
                "odometer_reading": 0,
            }
        )
        with self.assertRaises(frappe.ValidationError):
            ho.insert(ignore_permissions=True)

    def test_active_rider_fuel_request_passes(self):
        driver = _driver("T119 Fuel Active", status="Active")
        vehicle = factories.make_vehicle("T119-FUEL-OK")
        fr = frappe.get_doc(
            {
                "doctype": "Fuel Request",
                "request_type": "Standard",
                "vehicle": vehicle,
                "driver": driver,
                "request_date": today(),
                "requested_litres": 40,
                "status": "Pending",
            }
        )
        fr.insert(ignore_permissions=True)
        self.assertTrue(fr.name)
        self.assertFalse(
            _open_clearance_todos(driver),
            "An active rider must not trigger a clearance task.",
        )
        self.addCleanup(lambda: frappe.delete_doc("Fuel Request", fr.name, force=True, ignore_permissions=True))

    def test_clearance_task_is_idempotent(self):
        driver = _driver("T119 Idem Rider", status="Stopped", supervisor=self.supervisor)
        first = raise_rider_clearance_task(driver, vehicle=None)
        second = raise_rider_clearance_task(driver, vehicle=None)
        self.assertEqual(len(first), 1, "First call opens exactly one clearance task.")
        self.assertEqual(second, [], "A re-run must not open a duplicate task.")
        self.assertEqual(
            len(_open_clearance_todos(driver)), 1,
            "Only one open clearance ToDo may exist for the rider.",
        )
        self.addCleanup(lambda: self._purge_todos(driver))


    @staticmethod
    def _left_employee(name):
        emp = frappe.db.get_value("Employee", {"employee_name": name}, "name")
        if emp:
            frappe.db.set_value("Employee", emp, "status", "Left")
            return emp
        # Built, not assumed: an Employee needs a Company, and nothing in
        # before_tests guarantees one on a site that was never wizard-bootstrapped.
        company = factories.ensure_company()
        doc = frappe.get_doc(
            {
                "doctype": "Employee",
                "employee_name": name,
                "first_name": name,
                "status": "Left",
                "company": company,
                "gender": "Male",
                "date_of_birth": "1990-01-01",
                "date_of_joining": add_days(today(), -3650),
                "relieving_date": add_days(today(), -1),
            }
        )
        doc.insert(ignore_permissions=True)
        return doc.name

    @staticmethod
    def _employee_on_leave(name):
        """An ACTIVE Employee carrying an approved, submitted Leave Application
        that covers today.

        The employee stays Active on purpose: that is what isolates the leave
        source from the employee-status source, both of which
        ``rider_block_reason`` reads. HRMS refuses to validate a leave for an
        inactive employee anyway.
        """
        company = factories.ensure_company()
        holiday_list = _empty_holiday_list()
        emp = frappe.db.get_value("Employee", {"employee_name": name}, "name")
        if not emp:
            emp = frappe.get_doc(
                {
                    "doctype": "Employee",
                    "employee_name": name,
                    "first_name": name,
                    "status": "Active",
                    "company": company,
                    "gender": "Male",
                    "date_of_birth": "1990-01-01",
                    "date_of_joining": add_days(today(), -3650),
                    "holiday_list": holiday_list,
                }
            ).insert(ignore_permissions=True).name

        covering = frappe.db.exists(
            "Leave Application",
            {
                "employee": emp,
                "status": "Approved",
                "docstatus": 1,
                "from_date": ["<=", today()],
                "to_date": [">=", today()],
            },
        )
        if not covering:
            leave = frappe.get_doc(
                {
                    "doctype": "Leave Application",
                    "employee": emp,
                    "company": company,
                    "leave_type": _unpaid_leave_type(),
                    "from_date": add_days(today(), -1),
                    "to_date": add_days(today(), 1),
                    "status": "Approved",
                }
            )
            leave.insert(ignore_permissions=True)
            leave.submit()
        return emp

    @staticmethod
    def _purge_todos(driver):
        for t in _open_clearance_todos(driver):
            frappe.delete_doc("ToDo", t, force=True, ignore_permissions=True)
