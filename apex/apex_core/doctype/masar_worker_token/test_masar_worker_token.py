# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.doctype.masar_worker_token.masar_worker_token import (
    get_or_create_for_employee,
)
from apex.tests.factories import make_employee


class TestMasarWorkerTokenDriverBinding(FrappeTestCase):
    def test_a_driver_token_without_a_driver_is_refused(self):
        doc = frappe.get_doc({"doctype": "Masar Worker Token", "holder_type": "Driver"})
        with self.assertRaises(frappe.PermissionError):
            doc.insert(ignore_permissions=True)


class TestMasarWorkerTokenTemporaryWorkerReject(FrappeTestCase):
    def test_a_worker_token_cannot_be_issued_to_a_temporary_worker(self):
        temp_worker = frappe.get_doc(
            {
                "doctype": "Temporary Worker",
                "worker_name": "_T-Masar Temp Worker",
                "passport_number": frappe.generate_hash(length=10),
                "arrival_date": frappe.utils.today(),
            }
        ).insert(ignore_permissions=True)
        doc = frappe.get_doc(
            {
                "doctype": "Masar Worker Token",
                "holder_type": "Worker",
                "party_type": "Temporary Worker",
                "party": temp_worker.name,
            }
        )
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True)


class TestMasarWorkerTokenIssuance(FrappeTestCase):
    def test_creating_a_worker_token_mints_an_enabled_credential(self):
        employee = make_employee("_T-Masar Worker Employee")
        doc = get_or_create_for_employee(employee.name)
        self.assertTrue(doc.enabled)
        self.assertTrue(doc.token)


class TestMasarWorkerTokenSubjectBindingImmutability(FrappeTestCase):
    def test_the_employee_field_cannot_change_after_issuance(self):
        employee_a = make_employee("_T-Masar Immutable Employee A")
        employee_b = make_employee("_T-Masar Immutable Employee B")
        doc = get_or_create_for_employee(employee_a.name)
        doc.employee = employee_b.name
        doc.party = employee_b.name
        with self.assertRaises(frappe.ValidationError):
            doc.save(ignore_permissions=True)
