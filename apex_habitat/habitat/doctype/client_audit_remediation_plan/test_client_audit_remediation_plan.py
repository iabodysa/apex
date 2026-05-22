import frappe
import unittest
from frappe.tests.utils import FrappeTestCase


class TestClientAuditRemediationPlan(FrappeTestCase):

    def test_create_valid_plan(self):
        doc = frappe.get_doc({
            "doctype": "Client Audit Remediation Plan",
            "naming_series": "CARP-.YYYY.-.####",
            "client_project": "PROJ-QA",
            "audit_received_date": "2026-05-01",
            "remediation_deadline": "2026-07-01",
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertIsNotNone(doc.name)
        frappe.delete_doc("Client Audit Remediation Plan", doc.name, force=True, ignore_permissions=True)

    def test_missing_project_raises(self):
        doc = frappe.get_doc({
            "doctype": "Client Audit Remediation Plan",
            "naming_series": "CARP-.YYYY.-.####",
            "audit_received_date": "2026-05-01",
            "remediation_deadline": "2026-07-01",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_missing_deadline_raises(self):
        doc = frappe.get_doc({
            "doctype": "Client Audit Remediation Plan",
            "naming_series": "CARP-.YYYY.-.####",
            "client_project": "PROJ-QA",
            "audit_received_date": "2026-05-01",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)
