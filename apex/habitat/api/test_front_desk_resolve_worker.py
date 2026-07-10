# Copyright (c) 2026, AFMCO and contributors
"""resolve_worker(identifier) tests: the read-only Front Desk fast-identify
endpoint that turns a scanned Iqama or Masar token into one worker and flags an
already-housed one. Each case provisions its own worker/token/bed with unique
hashes so it passes on a fresh CI site. Assignments are forced to docstatus=1 via
db.set_value (the same direct provisioning the sibling arrivals/dashboard tests
use) so the active-bed flag is genuinely exercised without the bed-lock gate."""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.api.front_desk import resolve_worker


def _h(n=8):
    return frappe.generate_hash(length=n).upper()


class TestResolveWorker(FrappeTestCase):
    def setUp(self):
        self.building = "BLDG-" + _h(6)
        self._cleanup = []
        self._assignments = []

        self.iqama = _h(10)
        self.tw = frappe.get_doc({
            "doctype": "Temporary Worker",
            "worker_name": "TW-" + _h(6),
            "passport_number": "P" + _h(8),
            "iqama_number": self.iqama,
        })
        self.tw.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        self._cleanup.append(("Temporary Worker", self.tw.name))

    def _employee(self):
        """A minimal Employee — Masar tokens may only bind to an Employee."""
        doc = frappe.get_doc({
            "doctype": "Employee",
            "first_name": "EMP-" + _h(6),
            "naming_series": "HR-EMP-",
        })
        doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        self._cleanup.append(("Employee", doc.name))
        return doc

    def _token_for(self, employee):
        """Issue a Masar token to an Employee (the controller mints the value)."""
        tok = frappe.get_doc({
            "doctype": "Masar Worker Token",
            "party_type": "Employee",
            "party": employee,
            "enabled": 1,
        })
        tok.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        self._cleanup.append(("Masar Worker Token", tok.name))
        return tok

    def _bed(self):
        doc = frappe.get_doc({
            "doctype": "Bed",
            "bed_code": "BED-" + _h(6),
            "building": self.building,
            "status": "Available",
        })
        doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        self._cleanup.append(("Bed", doc.name))
        return doc.name

    def _house(self, party_type, party, employee=None):
        """A submitted, not-checked-out Accommodation Assignment for the party."""
        doc = frappe.get_doc({
            "doctype": "Housing Assignment",
            "naming_series": "ACC-ASGN-.YYYY.-.####",
            "party_type": party_type,
            "party": party,
            "employee": employee,
            "building": self.building,
            "bed": self._bed(),
        })
        doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        frappe.db.set_value(
            "Housing Assignment", doc.name,
            {"docstatus": 1, "check_in_date": "2026-06-20"}, update_modified=False,
        )
        self._assignments.append(doc.name)
        return doc.name

    def tearDown(self):
        for name in self._assignments:
            frappe.db.set_value("Housing Assignment", name, "docstatus", 0,
                                update_modified=False)
            frappe.delete_doc("Housing Assignment", name, force=True,
                              ignore_permissions=True)
        for dt, name in reversed(self._cleanup):
            frappe.delete_doc(dt, name, force=True, ignore_permissions=True)

    def test_resolves_temporary_worker_by_iqama(self):
        r = resolve_worker(self.iqama)
        self.assertTrue(r["found"])
        self.assertEqual(r["party_type"], "Temporary Worker")
        self.assertEqual(r["party"], self.tw.name)
        self.assertEqual(r["employee_name"], self.tw.worker_name)
        # Not yet housed.
        self.assertFalse(r["has_active_assignment"])

    def test_flags_already_housed_worker(self):
        self._house("Temporary Worker", self.tw.name)
        r = resolve_worker(self.iqama)
        self.assertTrue(r["found"])
        self.assertTrue(r["has_active_assignment"], "a worker holding a live bed is flagged")

    def test_resolves_masar_token(self):
        emp = self._employee()
        tok = self._token_for(emp.name)
        r = resolve_worker(tok.token)
        self.assertTrue(r["found"])
        self.assertEqual(r["party_type"], "Employee")
        self.assertEqual(r["party"], emp.name)
        self.assertEqual(r["employee"], emp.name)

    def test_token_flags_housed_employee(self):
        emp = self._employee()
        tok = self._token_for(emp.name)
        self._house("Employee", emp.name, employee=emp.name)
        r = resolve_worker(tok.token)
        self.assertTrue(r["has_active_assignment"], "an Employee holding a live bed is flagged")

    def test_disabled_token_does_not_resolve(self):
        emp = self._employee()
        tok = self._token_for(emp.name)
        frappe.db.set_value("Masar Worker Token", tok.name, "enabled", 0)
        # A disabled token must not resolve; it also isn't a valid Iqama, so unknown.
        self.assertFalse(resolve_worker(tok.token)["found"])

    def test_unknown_identifier_returns_not_found(self):
        r = resolve_worker("NOPE-" + _h())
        self.assertFalse(r["found"])
        self.assertIn("message", r)

    def test_blank_identifier_returns_not_found(self):
        self.assertFalse(resolve_worker("   ")["found"])
        self.assertFalse(resolve_worker("")["found"])
