# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from apex.tests._helpers import _grant_project, _user, as_user
from apex.tests.factories import make_project, make_vehicle


def _wash_request(**overrides):
    fields = {
        "doctype": "Wash Request",
        "vehicle": make_vehicle("_T-WR 0001"),
        "wash_type": "Exterior",
        "status": "Pending",
    }
    fields.update(overrides)
    return frappe.get_doc(fields)


class TestWashRequestFrameworkRefusals(FrappeTestCase):
    def test_a_request_with_no_vehicle_is_refused_by_the_framework(self):
        with self.assertRaises(frappe.MandatoryError):
            _wash_request(vehicle=None).insert(ignore_permissions=True)

    def test_a_wash_type_outside_the_select_options_is_refused_by_the_framework(self):
        with self.assertRaises(frappe.ValidationError):
            _wash_request(wash_type="Polish").insert(ignore_permissions=True)

    def test_a_status_outside_the_select_options_is_refused_by_the_framework(self):
        with self.assertRaises(frappe.ValidationError):
            _wash_request(status="Rejected").insert(ignore_permissions=True)


class TestWashRequestProjectScope(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.mine = make_project("_T-WR Scope Mine")
        cls.theirs = make_project("_T-WR Scope Theirs")
        cls.my_request = _wash_request(
            vehicle=make_vehicle("_T-WR 0010", project=cls.mine), wash_date=today()
        ).insert(ignore_permissions=True)
        cls.their_request = _wash_request(
            vehicle=make_vehicle("_T-WR 0011", project=cls.theirs)
        ).insert(ignore_permissions=True)
        cls.supervisor = _user("_t_wr_scope@example.com", "Fleet Supervisor")
        _grant_project(cls.supervisor, cls.mine)

    def test_a_supervisor_reads_a_request_for_a_vehicle_on_his_project(self):
        with as_user(self.supervisor):
            self.assertTrue(
                frappe.has_permission("Wash Request", "read", doc=self.my_request)
            )

    def test_a_supervisor_is_refused_a_request_for_a_vehicle_off_his_project(self):
        with as_user(self.supervisor):
            with self.assertRaises(frappe.PermissionError):
                frappe.has_permission(
                    "Wash Request", "read", doc=self.their_request, throw=True
                )

    def test_the_scope_filter_hides_the_off_project_request_from_the_list(self):
        with as_user(self.supervisor):
            names = [
                row.name
                for row in frappe.get_list(
                    "Wash Request", filters={"name": ["in", [
                        self.my_request.name, self.their_request.name]]}
                )
            ]
        self.assertIn(self.my_request.name, names)
        self.assertNotIn(self.their_request.name, names)
