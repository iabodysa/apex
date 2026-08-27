# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.model.workflow import apply_workflow
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from apex.tests.factories import default_company, make_project


def _template(name="_T-RA Template"):
    label = name + " " + frappe.generate_hash(length=6)
    return frappe.get_doc(
        {
            "doctype": "Route Template",
            "template_name": label,
            "route_type": "Pickup",
            "stops": [{"stop_name": "_T-RA Stop"}],
        }
    ).insert(ignore_permissions=True).name


def _shift():
    return frappe.get_doc(
        {
            "doctype": "Work Shift",
            "shift_name": "_T-RA Shift " + frappe.generate_hash(length=6),
            "start_time": "07:00:00",
            "end_time": "16:00:00",
            "applicable_days": [{"day_of_week": day} for day in
                                ("Sunday", "Monday", "Tuesday", "Wednesday", "Thursday",
                                 "Friday", "Saturday")],
        }
    ).insert(ignore_permissions=True).name


def _vehicle():
    return frappe.get_doc(
        {
            "doctype": "Salis Vehicle",
            "plate_number": "_T-RA " + frappe.generate_hash(length=6),
            "status": "Active",
        }
    ).insert(ignore_permissions=True).name


def _driver():
    employee = frappe.get_doc(
        {
            "doctype": "Employee",
            "first_name": "_T-RA Driver " + frappe.generate_hash(length=6),
            "date_of_birth": "1990-01-01",
            "date_of_joining": "2020-01-01",
            "gender": "Male",
            "company": default_company(),
        }
    ).insert(ignore_permissions=True).name
    return frappe.get_doc(
        {
            "doctype": "Salis Driver",
            "employee": employee,
            "full_name": "_T-RA Driver",
        }
    ).insert(ignore_permissions=True).name


def _supervisor():
    email = "_t_ra_" + frappe.generate_hash(length=6) + "@example.com"
    doc = frappe.get_doc(
        {
            "doctype": "User",
            "email": email,
            "first_name": "_T-RA Supervisor",
            "send_welcome_email": 0,
        }
    )
    doc.insert(ignore_permissions=True)
    doc.add_roles("Fleet Supervisor")
    return email


def _assignment(**overrides):
    fields = {
        "doctype": "Route Assignment",
        "route_template": _template(),
        "work_shift": _shift(),
        "project": make_project("_T-RA Project"),
        "driver": _driver(),
        "vehicle": _vehicle(),
        "route_supervisor": _supervisor(),
        "starts_on": today(),
        "enabled": 1,
        "status": "Pending",
    }
    fields.update(overrides)
    return frappe.get_doc(fields)


class TestRouteAssignmentWindow(FrappeTestCase):
    def test_an_end_before_the_start_is_refused(self):
        with self.assertRaisesRegex(frappe.ValidationError, "Ends On cannot be earlier"):
            _assignment(ends_on=add_days(today(), -1)).insert(ignore_permissions=True)

    def test_an_end_after_the_start_is_accepted(self):
        doc = _assignment(ends_on=add_days(today(), 10)).insert(ignore_permissions=True)
        self.assertEqual(str(doc.ends_on), add_days(today(), 10))

    def test_an_open_ended_assignment_is_accepted(self):
        doc = _assignment().insert(ignore_permissions=True)
        self.assertFalse(doc.ends_on)


class TestRouteAssignmentName(FrappeTestCase):
    def test_the_name_joins_the_template_the_shift_and_the_project(self):
        template, shift, project = _template(), _shift(), make_project("_T-RA Project")
        doc = _assignment(route_template=template, work_shift=shift, project=project).insert(
            ignore_permissions=True
        )
        self.assertEqual(
            doc.assignment_name,
            " · ".join(
                (
                    frappe.db.get_value("Route Template", template, "template_name"),
                    frappe.db.get_value("Work Shift", shift, "shift_name"),
                    frappe.db.get_value("Project", project, "project_name"),
                )
            ),
        )


class TestRouteAssignmentApprovalGate(FrappeTestCase):
    def test_submitting_a_pending_assignment_is_refused(self):
        doc = _assignment().insert(ignore_permissions=True)
        with self.assertRaisesRegex(frappe.ValidationError, "Approve workflow action"):
            doc.submit()

    def test_an_assignment_missing_a_driver_cannot_be_submitted(self):
        doc = _assignment(driver=None).insert(ignore_permissions=True)
        doc.status = "Approved"
        with self.assertRaisesRegex(frappe.ValidationError, "Default Driver"):
            doc.submit()

    def test_an_assignment_missing_a_supervisor_cannot_be_submitted(self):
        doc = _assignment(route_supervisor=None).insert(ignore_permissions=True)
        doc.status = "Approved"
        with self.assertRaisesRegex(frappe.ValidationError, "Route Supervisor"):
            doc.submit()

    def test_approving_stamps_the_approver_and_the_moment(self):
        doc = _assignment().insert(ignore_permissions=True)
        apply_workflow(doc, "Approve")
        self.assertEqual(doc.approved_by, frappe.session.user)
        self.assertTrue(doc.approved_on)


class TestRouteAssignmentGeneratesTrips(FrappeTestCase):
    def test_submitting_an_approved_assignment_plans_its_trips(self):
        doc = _assignment().insert(ignore_permissions=True)
        apply_workflow(doc, "Approve")
        self.assertTrue(
            frappe.db.exists("Dispatch Trip", {"route_assignment": doc.name, "status": "Planned"})
        )

    def test_cancelling_removes_the_planned_trips_it_had_created(self):
        doc = _assignment().insert(ignore_permissions=True)
        apply_workflow(doc, "Approve")
        doc.cancel()
        self.assertFalse(
            frappe.db.exists("Dispatch Trip", {"route_assignment": doc.name, "docstatus": 0})
        )
        self.assertFalse(frappe.db.get_value("Route Assignment", doc.name, "generated_through"))

    def test_a_disabled_assignment_plans_nothing(self):
        doc = _assignment(enabled=0).insert(ignore_permissions=True)
        apply_workflow(doc, "Approve")
        self.assertFalse(frappe.db.exists("Dispatch Trip", {"route_assignment": doc.name}))
