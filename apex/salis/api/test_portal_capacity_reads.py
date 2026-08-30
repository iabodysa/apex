# Copyright (c) 2026, afmcoltd

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.utils.portal_identity import DRIVER, WORKER, as_capacity
from apex.habitat.permissions import building_scoped_has_permission
from apex.salis.api.driver_portal import _attach_boarding_counts
from apex.salis.permissions import project_scope_query

_REQUEST = "TR-A610-CAPACITY-READ"
_TRIP = "DT-A610-CAPACITY-READ"
_EMPLOYEE = "HR-EMP-A610"


def _child(doctype, parent, parenttype, parentfield, **values):
    row = frappe.get_doc(
        {
            "doctype": doctype,
            "parent": parent,
            "parenttype": parenttype,
            "parentfield": parentfield,
            "idx": 1,
            **values,
        }
    )
    row.db_insert()
    return row


class TestAChildTableReadUnderAPortalCapacityReturnsItsRows(FrappeTestCase):
    def setUp(self):
        _child(
            "Transport Request Worker",
            _REQUEST,
            "Transport Request",
            "workers",
            employee=_EMPLOYEE,
        )
        _child(
            "Trip Boarding State",
            _TRIP,
            "Dispatch Trip",
            "boarding_state",
            employee=_EMPLOYEE,
            status="Pending",
        )

    def tearDown(self):
        frappe.db.delete("Transport Request Worker", {"parent": _REQUEST})
        frappe.db.delete("Trip Boarding State", {"parent": _TRIP})

    def test_the_worker_capacity_reads_its_request_workers_through_the_parent_grant(self):
        with as_capacity(WORKER, _EMPLOYEE):
            rows = frappe.get_list(
                "Transport Request Worker",
                filters={"parent": _REQUEST, "parenttype": "Transport Request"},
                fields=["employee"],
                parent_doctype="Transport Request",
            )
        self.assertEqual([r["employee"] for r in rows], [_EMPLOYEE])

    def test_the_same_read_without_a_parent_doctype_is_refused(self):
        with as_capacity(WORKER, _EMPLOYEE):
            with self.assertRaises(frappe.PermissionError):
                frappe.get_list(
                    "Transport Request Worker",
                    filters={"parent": _REQUEST, "parenttype": "Transport Request"},
                    fields=["employee"],
                )

    def test_worker_today_dispatch_trip_reads_its_worker_rows_under_the_capacity(self):
        with as_capacity(WORKER, _EMPLOYEE):
            rows = frappe.get_list(
                "Transport Request Worker",
                filters={"parenttype": "Transport Request", "employee": _EMPLOYEE},
                fields=["parent"],
                parent_doctype="Transport Request",
            )
        self.assertEqual([r["parent"] for r in rows], [_REQUEST])

    def test_the_driver_capacity_counts_the_trips_boarding_state_rows(self):
        trips = [{"name": _TRIP}]
        with as_capacity(DRIVER, "DRV-A610"):
            _attach_boarding_counts(trips, "DRV-A610")
        self.assertEqual(trips[0]["expected_count"], 1)


class TestThePortalCapacityListScopeIsBoundToItsSubject(FrappeTestCase):
    def test_the_driver_capacity_reads_only_the_trips_that_name_it(self):
        with as_capacity(DRIVER, "DRV-A610"):
            clause = project_scope_query(doctype="Dispatch Trip")
        self.assertEqual(clause, "`driver` = 'DRV-A610'")

    def test_the_driver_capacity_reads_nothing_on_a_doctype_with_no_driver_column(self):
        with as_capacity(DRIVER, "DRV-A610"):
            clause = project_scope_query(doctype="Fuel Claim")
        self.assertEqual(clause, "1=0")

    def test_the_worker_capacity_reads_only_the_requests_that_carry_it(self):
        with as_capacity(WORKER, _EMPLOYEE):
            clause = project_scope_query(doctype="Transport Request")
        self.assertIn("tabTransport Request Worker", clause)
        self.assertIn(frappe.db.escape(_EMPLOYEE), clause)
        self.assertNotEqual(clause, "1=0")

    def test_a_capacity_with_no_bound_subject_reads_nothing(self):
        with as_capacity(DRIVER, None):
            clause = project_scope_query(doctype="Dispatch Trip")
        self.assertEqual(clause, "1=0")

    def test_a_habitat_document_is_never_read_under_a_portal_capacity(self):
        doc = frappe.get_doc({"doctype": "Building", "name": "BLD-A610-CAPACITY"})
        with as_capacity(WORKER, _EMPLOYEE):
            self.assertIs(building_scoped_has_permission(doc, "read"), False)
