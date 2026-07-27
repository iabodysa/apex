# Copyright (c) 2026, AFMCO and contributors
"""Building (tenant) row-scoping for the report-side desk/kiosk read endpoints.

Script-report-style reads run on ``frappe.get_all`` (which forces
``ignore_permissions``), so the building row-scoping the desk LIST gets via
``permission_query_conditions`` is bypassed in these endpoints. Each must
re-apply the scope itself so a building-scoped supervisor sees ONLY their
estate's rows, while an oversight role (Accommodation Manager, in
``HOUSING_UNSCOPED_ROLES``) stays unrestricted.

Covered (all as a Resident Supervisor scoped to ONE building via User
Permission):
  * ``arrivals_desk.search_arrivals_workers`` — Temporary Worker candidates and
    the housed-exclusion set are confined to the user's building.
  * ``arrivals_desk.search_arrivals_workers`` again, for the EMPLOYEE branch.
    Temporary Worker is scoped on its own ``building`` field, but Employee carries
    no building at all — its estate is the building of its live Housing
    Assignment — so that branch needs its own out-of-estate exclusion and its own
    proof. The Employee cases use a second fixture user holding HR User ALONGSIDE
    Resident Supervisor: the branch sits behind a type-level
    ``has_permission("Employee", "read")``, so without that role it is never
    entered and an Employee assertion would pass against unscoped code.
  * ``custody_kiosk.get_party_custody`` — open Custody Issues are confined to the
    user's building, so another estate's custody is never surfaced.
  * ``safety_checklist.get_tasks_for_cadence`` / ``get_due_cadences`` — gated on
    read of the target building, so a scoped-off building is denied up-front.

Rows are inserted with ``ignore_permissions/links/mandatory`` and, where a
submitted/closed state is needed, the docstatus/status is set directly via
``frappe.db.set_value`` (the synthetic-row pattern) so no controller side-effect
(ledger posting, party-link mirroring) is exercised — these tests pin the read
SCOPE, not the write controllers.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.api.arrivals_desk import search_arrivals_workers
from apex.habitat.api.custody_kiosk import get_party_custody
from apex.habitat.api.safety_checklist import (
    get_due_cadences,
    get_tasks_for_cadence,
)
from apex.tests._helpers import as_user


def _h(n=12):
    return frappe.generate_hash(length=n).upper()


class TestArrivalsCustodyReportScope(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # [#ge40ld]
        cls.b1 = cls._building()
        cls.b2 = cls._building()
        cls.scoped = cls._user(["Resident Supervisor"], building=cls.b1)
        cls.oversight = cls._user(["Accommodation Manager"])
        cls.lonely = cls._user(["Resident Supervisor"])  # [#s3pi7t]
        # HR User is what opens the Employee branch of the search; see the module
        # docstring. Kept separate from cls.scoped so the Temporary Worker cases
        # keep exercising a supervisor who cannot read Employee at all.
        cls.scoped_hr = cls._user(
            ["Resident Supervisor", "HR User"], building=cls.b1
        )
        cls.oversight_hr = cls._user(["Accommodation Manager", "HR User"])

    # [#ir0iwd]
    @classmethod
    def _building(cls):
        doc = frappe.get_doc(
            {"doctype": "Building", "building_name": "RPT-" + _h()}
        )
        doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        cls.addClassCleanup(
            frappe.delete_doc,
            "Building",
            doc.name,
            force=True,
            ignore_permissions=True,
        )
        return doc.name

    @classmethod
    def _user(cls, roles, building=None):
        email = "rpt-{0}@example.com".format(_h()).lower()
        frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": "Rpt",
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

    @classmethod
    def _temp_worker(cls, building):
        doc = frappe.get_doc(
            {
                "doctype": "Temporary Worker",
                "worker_name": "TW-" + _h(),
                "passport_number": "P" + _h(12),
                "building": building,
                "status": "Active",
            }
        )
        doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        cls.addClassCleanup(
            frappe.delete_doc,
            "Temporary Worker",
            doc.name,
            force=True,
            ignore_permissions=True,
        )
        return doc.name

    @classmethod
    def _open_custody_issue(cls, building, party_type, party):
        """A submitted, still-open Custody Issue with one held article line.

        Inserted as a draft, then docstatus/status flipped via db.set_value (the
        synthetic-row pattern): the read endpoint only inspects building /
        party_type / party / status / docstatus + the item rows, so no controller
        posting is needed (and we avoid the ledger/party-link side effects).
        """
        article = cls._article()
        doc = frappe.get_doc(
            {
                "doctype": "Custody Issue",
                "issue_date": frappe.utils.today(),
                "building": building,
                "party_type": party_type,
                "party": party,
                "items": [
                    {"doctype": "Custody Issue Item", "article": article, "qty": 2}
                ],
            }
        )
        doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        frappe.db.set_value(
            "Custody Issue", doc.name, {"docstatus": 1, "status": "Issued"}
        )
        # [#1i4y73]
        cls.addClassCleanup(
            lambda n=doc.name: (
                frappe.db.set_value("Custody Issue", n, "docstatus", 0),
                frappe.delete_doc("Custody Issue", n, force=True, ignore_permissions=True),
            )
        )
        return doc.name

    @classmethod
    def _article(cls):
        doc = frappe.get_doc(
            {
                "doctype": "Custody Article",
                "article_name": "ART-" + _h(),
                "unit_of_measure": "Nos",
            }
        )
        doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        cls.addClassCleanup(
            frappe.delete_doc,
            "Custody Article",
            doc.name,
            force=True,
            ignore_permissions=True,
        )
        return doc.name

    @classmethod
    def _daily_task(cls):
        doc = frappe.get_doc(
            {
                "doctype": "Safety Task Catalog",
                "task_code": "RPT-" + _h(),
                "task_title": "Report Scope Task",
                "department": "Fire Safety",
                "frequency": "Daily",
                "priority": "High",
                "applicable_to_all_buildings": 1,
                "is_active": 1,
            }
        )
        doc.insert(ignore_permissions=True)
        cls.addClassCleanup(
            frappe.delete_doc,
            "Safety Task Catalog",
            doc.name,
            force=True,
            ignore_permissions=True,
        )
        return doc.name

    def _employee(self):
        """An Active Employee, returned with the token that finds it in the search.

        The search matches on ``employee_name``, and ERPNext's Employee.validate
        REBUILDS ``employee_name`` from first/middle/last name — so the unique token
        has to be planted in ``first_name`` to survive the insert. Returned so each
        case can pass it as ``txt`` and pin the search to its own fixture instead of
        relying on the endpoint's unfiltered 15-row page.
        """
        token = _h()
        doc = frappe.get_doc(
            {
                "doctype": "Employee",
                "first_name": "RptScope" + token,
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
        return doc.name, token

    def _house(self, employee, building):
        """A submitted, still-open Housing Assignment placing ``employee`` in
        ``building`` — the only thing that gives an Employee an estate."""
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
        # [#1i4y73]
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

    # [#9rlcxk]
    def test_search_workers_scoped_to_own_building(self):
        # [#m2plrf]
        tw1 = self._temp_worker(self.b1)
        tw2 = self._temp_worker(self.b2)
        with as_user(self.scoped):
            parties = {r["party"] for r in search_arrivals_workers()}
        self.assertIn(tw1, parties, "scoped supervisor sees their own estate's worker")
        self.assertNotIn(
            tw2, parties, "scoped supervisor must NOT see another estate's worker"
        )

    def test_search_workers_oversight_sees_all(self):
        tw1 = self._temp_worker(self.b1)
        tw2 = self._temp_worker(self.b2)
        with as_user(self.oversight):
            parties = {r["party"] for r in search_arrivals_workers()}
        self.assertIn(tw1, parties)
        self.assertIn(tw2, parties, "oversight role is unrestricted across estates")

    def test_search_workers_lonely_scoped_user_sees_none(self):
        # [#ih2knq]
        self._temp_worker(self.b1)
        self._temp_worker(self.b2)
        with as_user(self.lonely):
            self.assertEqual(search_arrivals_workers(), [])

    def test_search_workers_excludes_employee_housed_in_other_estate(self):
        """The Employee-branch leak: an Employee housed in b2 must not be offered
        to a b1-scoped supervisor.

        The housed-exclusion set is built from a b1-restricted query, so a b2-housed
        Employee is absent from it — and the Employee search itself has no building
        of its own to filter on. Before the out-of-estate exclusion this call
        returned that Employee estate-wide.
        """
        emp, token = self._employee()
        self._house(emp, self.b2)
        with as_user(self.scoped_hr):
            parties = {r["party"] for r in search_arrivals_workers(txt=token)}
        self.assertNotIn(
            emp,
            parties,
            "scoped supervisor must NOT see an Employee housed in another estate",
        )

    def test_search_workers_keeps_unhoused_employee(self):
        """The exclusion is out-of-estate, not blanket: an Employee with no live
        assignment is the intake case the desk exists for and must stay offered."""
        emp, token = self._employee()
        with as_user(self.scoped_hr):
            parties = {r["party"] for r in search_arrivals_workers(txt=token)}
        self.assertIn(
            emp, parties, "a not-yet-housed arrival must remain searchable"
        )

    def test_search_workers_excludes_employee_already_housed_here(self):
        """The pre-existing housed-exclusion still holds: an Employee already in the
        caller's OWN estate is not offered for a fresh check-in either."""
        emp, token = self._employee()
        self._house(emp, self.b1)
        with as_user(self.scoped_hr):
            parties = {r["party"] for r in search_arrivals_workers(txt=token)}
        self.assertNotIn(
            emp, parties, "an Employee already housed here is not a check-in candidate"
        )

    def test_search_workers_oversight_keeps_unhoused_employee(self):
        """An unscoped oversight role computes no out-of-estate set at all; the
        Employee branch stays estate-wide for them."""
        emp, token = self._employee()
        with as_user(self.oversight_hr):
            parties = {r["party"] for r in search_arrivals_workers(txt=token)}
        self.assertIn(emp, parties, "oversight role is unrestricted across estates")

    # [#b8m2oe]
    def test_party_custody_scoped_excludes_other_estate(self):
        # [#r6rbq1]
        tw = self._temp_worker(self.b1)
        issue1 = self._open_custody_issue(self.b1, "Temporary Worker", tw)
        issue2 = self._open_custody_issue(self.b2, "Temporary Worker", tw)
        with as_user(self.scoped):
            lines = get_party_custody("Temporary Worker", tw)["lines"]
        issues = {ln["custody_issue"] for ln in lines}
        self.assertIn(issue1, issues, "scoped supervisor sees their estate's custody")
        self.assertNotIn(
            issue2, issues, "scoped supervisor must NOT see another estate's custody"
        )
        for ln in lines:
            self.assertEqual(
                ln["building"], self.b1, "every surfaced line is in-scope"
            )

    def test_party_custody_oversight_sees_both_estates(self):
        tw = self._temp_worker(self.b1)
        issue1 = self._open_custody_issue(self.b1, "Temporary Worker", tw)
        issue2 = self._open_custody_issue(self.b2, "Temporary Worker", tw)
        with as_user(self.oversight):
            issues = {
                ln["custody_issue"]
                for ln in get_party_custody("Temporary Worker", tw)["lines"]
            }
        self.assertIn(issue1, issues)
        self.assertIn(issue2, issues, "oversight role sees custody across estates")

    def test_party_custody_lonely_scoped_user_sees_none(self):
        tw = self._temp_worker(self.b1)
        self._open_custody_issue(self.b1, "Temporary Worker", tw)
        with as_user(self.lonely):
            self.assertEqual(get_party_custody("Temporary Worker", tw)["lines"], [])

    # [#r1ur8e]
    def test_tasks_for_cadence_denies_off_scope_building(self):
        self._daily_task()
        with as_user(self.scoped):
            # [#rnrexq]
            out = get_tasks_for_cadence(self.b1, "Daily")
            self.assertEqual(out["building"], self.b1)
            # [#2m6lw1]
            with self.assertRaises(frappe.PermissionError):
                get_tasks_for_cadence(self.b2, "Daily")

    def test_due_cadences_denies_off_scope_building(self):
        self._daily_task()
        with as_user(self.scoped):
            out = get_due_cadences(self.b1)
            self.assertEqual(out["building"], self.b1)
            with self.assertRaises(frappe.PermissionError):
                get_due_cadences(self.b2)

    def test_safety_reads_unrestricted_for_oversight(self):
        self._daily_task()
        with as_user(self.oversight):
            # [#slk3a7]
            self.assertEqual(get_tasks_for_cadence(self.b2, "Daily")["building"], self.b2)
            self.assertEqual(get_due_cadences(self.b2)["building"], self.b2)
