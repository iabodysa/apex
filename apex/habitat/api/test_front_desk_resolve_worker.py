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
from apex.tests._helpers import as_user


def _h(n=12):
    return frappe.generate_hash(length=n).upper()


class TestResolveWorker(FrappeTestCase):
    def setUp(self):
        self.building = "BLDG-" + _h(12)
        self._cleanup = []
        self._assignments = []

        self.iqama = _h(12)
        self.tw = frappe.get_doc({
            "doctype": "Temporary Worker",
            "worker_name": "TW-" + _h(12),
            "passport_number": "P" + _h(12),
            "iqama_number": self.iqama,
        })
        self.tw.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        self._cleanup.append(("Temporary Worker", self.tw.name))

    def _employee(self):
        """A minimal Employee — Masar tokens may only bind to an Employee."""
        doc = frappe.get_doc({
            "doctype": "Employee",
            "first_name": "EMP-" + _h(12),
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
            "bed_code": "BED-" + _h(12),
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
        # [#rmrjzj]
        self.assertFalse(r["has_active_assignment"])

    def test_flags_already_housed_worker(self):
        self._house("Temporary Worker", self.tw.name)
        r = resolve_worker(self.iqama)
        self.assertTrue(r["found"])
        self.assertTrue(r["has_active_assignment"], "a worker holding a live bed is flagged")

    def test_resolves_masar_token(self):
        emp = self._employee()
        tok = self._token_for(emp.name)
        r = resolve_worker(tok._plaintext_token)
        self.assertTrue(r["found"])
        self.assertEqual(r["party_type"], "Employee")
        self.assertEqual(r["party"], emp.name)
        self.assertEqual(r["employee"], emp.name)

    def test_token_flags_housed_employee(self):
        emp = self._employee()
        tok = self._token_for(emp.name)
        self._house("Employee", emp.name, employee=emp.name)
        r = resolve_worker(tok._plaintext_token)
        self.assertTrue(r["has_active_assignment"], "an Employee holding a live bed is flagged")

    def test_disabled_token_does_not_resolve(self):
        emp = self._employee()
        tok = self._token_for(emp.name)
        frappe.db.set_value("Masar Worker Token", tok.name, "enabled", 0)
        # [#i6750x]
        self.assertFalse(resolve_worker(tok._plaintext_token)["found"])

    def test_unknown_identifier_returns_not_found(self):
        r = resolve_worker("NOPE-" + _h())
        self.assertFalse(r["found"])
        self.assertIn("message", r)

    def test_blank_identifier_returns_not_found(self):
        self.assertFalse(resolve_worker("   ")["found"])
        self.assertFalse(resolve_worker("")["found"])


class TestResolveWorkerBuildingScope(FrappeTestCase):
    """Per-doc BUILDING scope for the scanned-identifier lookup.

    ``resolve_worker`` takes a CLIENT-SUPPLIED identifier and answers with worker
    identity. Every lookup it makes is a ``frappe.db.get_value``, which never
    consults ``permission_query_conditions`` — so before the gate a supervisor
    scoped to b1 could scan (or simply type) an out-of-estate Iqama or Masar token
    and be handed that worker's name, photo and housing state.

    The test user deliberately holds HR User ALONGSIDE Resident Supervisor: the
    endpoint opens with a type-level ``has_permission("Employee", "read")``, and
    without that role the call would raise on the type gate and prove nothing
    about the building gate. Rows are inserted with
    ``ignore_permissions/links/mandatory`` and docstatus is flipped via
    ``db.set_value`` — these pin the read SCOPE, not the write controllers.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.b1 = cls._building()
        cls.b2 = cls._building()
        cls.scoped = cls._user(["Resident Supervisor", "HR User"], building=cls.b1)
        cls.oversight = cls._user(["Accommodation Manager", "HR User"])

    @classmethod
    def _building(cls):
        doc = frappe.get_doc({"doctype": "Building", "building_name": "RSV-" + _h()})
        doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        cls.addClassCleanup(
            frappe.delete_doc, "Building", doc.name, force=True, ignore_permissions=True
        )
        return doc.name

    @classmethod
    def _user(cls, roles, building=None):
        email = "rsv-{0}@example.com".format(_h()).lower()
        frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": "Rsv",
                "send_welcome_email": 0,
                "roles": [{"role": r} for r in roles],
            }
        ).insert(ignore_permissions=True)
        cls.addClassCleanup(
            frappe.delete_doc, "User", email, force=True, ignore_permissions=True
        )
        if building:
            up = frappe.get_doc(
                {
                    "doctype": "User Permission",
                    "user": email,
                    "allow": "Building",
                    "for_value": building,
                }
            )
            up.insert(ignore_permissions=True)
            cls.addClassCleanup(
                frappe.delete_doc,
                "User Permission",
                up.name,
                force=True,
                ignore_permissions=True,
            )
        return email

    def _temp_worker(self, building):
        """A Temporary Worker whose estate is ``building``, carrying an Iqama."""
        iqama = "IQ" + _h()
        doc = frappe.get_doc(
            {
                "doctype": "Temporary Worker",
                "worker_name": "TW-" + _h(),
                "passport_number": "P" + _h(),
                "iqama_number": iqama,
                "building": building,
                "status": "Active",
            }
        )
        doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        self.addCleanup(
            frappe.delete_doc,
            "Temporary Worker",
            doc.name,
            force=True,
            ignore_permissions=True,
        )
        return doc.name, iqama

    def _employee(self):
        doc = frappe.get_doc(
            {
                "doctype": "Employee",
                "employee_name": "Emp " + _h(),
                "first_name": "Emp",
                "status": "Active",
                "gender": "Male",
                "date_of_birth": "1990-01-01",
                "date_of_joining": "2020-01-01",
            }
        )
        doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        self.addCleanup(
            frappe.delete_doc, "Employee", doc.name, force=True, ignore_permissions=True
        )
        return doc.name

    def _token_for(self, employee):
        tok = frappe.get_doc(
            {
                "doctype": "Masar Worker Token",
                "party_type": "Employee",
                "party": employee,
                "employee": employee,
                "enabled": 1,
            }
        )
        tok.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        self.addCleanup(
            frappe.delete_doc,
            "Masar Worker Token",
            tok.name,
            force=True,
            ignore_permissions=True,
        )
        return tok

    def _house(self, employee, building):
        """A submitted, still-open assignment placing ``employee`` in ``building``."""
        doc = frappe.get_doc(
            {
                "doctype": "Housing Assignment",
                "party_type": "Employee",
                "party": employee,
                "employee": employee,
                "building": building,
                "check_in_date": frappe.utils.today(),
            }
        )
        doc.flags.ignore_validate = True
        doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        frappe.db.set_value("Housing Assignment", doc.name, "docstatus", 1)
        self.addCleanup(
            lambda n=doc.name: (
                frappe.db.set_value("Housing Assignment", n, "docstatus", 0),
                frappe.delete_doc(
                    "Housing Assignment", n, force=True, ignore_permissions=True
                ),
            )
        )
        return doc.name

    def setUp(self):
        self.addCleanup(frappe.set_user, "Administrator")

    def test_iqama_of_other_building_worker_denied(self):
        """A b1-scoped supervisor scanning a b2 worker's Iqama is refused."""
        _tw, iqama = self._temp_worker(self.b2)
        with as_user(self.scoped):
            with self.assertRaises(frappe.PermissionError):
                resolve_worker(iqama)

    def test_masar_token_of_other_building_worker_denied(self):
        """Same refusal through the token path: the Employee is housed in b2."""
        emp = self._employee()
        tok = self._token_for(emp)
        self._house(emp, self.b2)
        with as_user(self.scoped):
            with self.assertRaises(frappe.PermissionError):
                resolve_worker(tok._plaintext_token)

    def test_iqama_of_own_building_worker_still_resolves(self):
        """The gate is a scope gate, not a blanket denial — b1 still resolves."""
        tw, iqama = self._temp_worker(self.b1)
        with as_user(self.scoped):
            result = resolve_worker(iqama)
        self.assertTrue(result["found"])
        self.assertEqual(result["party"], tw)

    def test_unhoused_employee_token_not_blocked_by_scope(self):
        """An Employee with no live assignment is the intake case the check-in
        dialog depends on; the building gate must not break it."""
        emp = self._employee()
        tok = self._token_for(emp)
        with as_user(self.scoped):
            result = resolve_worker(tok._plaintext_token)
        self.assertTrue(result["found"])
        self.assertEqual(result["party"], emp)

    def test_oversight_role_resolves_across_estates(self):
        """An unscoped oversight role keeps estate-wide reach."""
        tw, iqama = self._temp_worker(self.b2)
        with as_user(self.oversight):
            result = resolve_worker(iqama)
        self.assertTrue(result["found"])
        self.assertEqual(result["party"], tw)
