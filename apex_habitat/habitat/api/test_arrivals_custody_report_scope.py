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

from apex_habitat.habitat.api.arrivals_desk import search_arrivals_workers
from apex_habitat.habitat.api.custody_kiosk import get_party_custody
from apex_habitat.habitat.api.safety_checklist import (
    get_due_cadences,
    get_tasks_for_cadence,
)


def _h(n=6):
    return frappe.generate_hash(length=n).upper()


class _as_user:
    """Run a block as ``user`` then restore the session user."""

    def __init__(self, user):
        self.user = user

    def __enter__(self):
        self._prev = frappe.session.user
        frappe.set_user(self.user)
        return self

    def __exit__(self, *exc):
        frappe.set_user(self._prev)
        return False


class TestArrivalsCustodyReportScope(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Two estates; a Resident Supervisor scoped (User Permission) to ONLY b1,
        # and an oversight Accommodation Manager who must stay unrestricted.
        cls.b1 = cls._building()
        cls.b2 = cls._building()
        cls.scoped = cls._user("Resident Supervisor", building=cls.b1)
        cls.oversight = cls._user("Accommodation Manager")
        cls.lonely = cls._user("Resident Supervisor")  # role but NO User Permission

    # ---- fixtures ---------------------------------------------------------
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
    def _user(cls, role, building=None):
        email = "rpt-{0}@example.com".format(_h()).lower()
        frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": "Rpt",
                "send_welcome_email": 0,
                "roles": [{"role": role}],
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
                "passport_number": "P" + _h(8),
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
        # docstatus was faked to 1 via db.set_value; reset it before delete_doc
        # (force=True does not bypass the submitted-record delete guard).
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

    def setUp(self):
        self.addCleanup(frappe.set_user, "Administrator")

    # ---- T-686: search_arrivals_workers ----------------------------------
    def test_search_workers_scoped_to_own_building(self):
        # One active Temporary Worker per estate; the scoped supervisor's search
        # must surface only b1's worker, never b2's.
        tw1 = self._temp_worker(self.b1)
        tw2 = self._temp_worker(self.b2)
        with _as_user(self.scoped):
            parties = {r["party"] for r in search_arrivals_workers()}
        self.assertIn(tw1, parties, "scoped supervisor sees their own estate's worker")
        self.assertNotIn(
            tw2, parties, "scoped supervisor must NOT see another estate's worker"
        )

    def test_search_workers_oversight_sees_all(self):
        tw1 = self._temp_worker(self.b1)
        tw2 = self._temp_worker(self.b2)
        with _as_user(self.oversight):
            parties = {r["party"] for r in search_arrivals_workers()}
        self.assertIn(tw1, parties)
        self.assertIn(tw2, parties, "oversight role is unrestricted across estates")

    def test_search_workers_lonely_scoped_user_sees_none(self):
        # A scoped role with NO User Permission building must get nothing.
        self._temp_worker(self.b1)
        self._temp_worker(self.b2)
        with _as_user(self.lonely):
            self.assertEqual(search_arrivals_workers(), [])

    # ---- T-687: get_party_custody ----------------------------------------
    def test_party_custody_scoped_excludes_other_estate(self):
        # The SAME party holds custody booked against b1 and against b2; the scoped
        # supervisor must see only the b1 issue's line, never b2's.
        tw = self._temp_worker(self.b1)
        issue1 = self._open_custody_issue(self.b1, "Temporary Worker", tw)
        issue2 = self._open_custody_issue(self.b2, "Temporary Worker", tw)
        with _as_user(self.scoped):
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
        with _as_user(self.oversight):
            issues = {
                ln["custody_issue"]
                for ln in get_party_custody("Temporary Worker", tw)["lines"]
            }
        self.assertIn(issue1, issues)
        self.assertIn(issue2, issues, "oversight role sees custody across estates")

    def test_party_custody_lonely_scoped_user_sees_none(self):
        tw = self._temp_worker(self.b1)
        self._open_custody_issue(self.b1, "Temporary Worker", tw)
        with _as_user(self.lonely):
            self.assertEqual(get_party_custody("Temporary Worker", tw)["lines"], [])

    # ---- T-692: get_tasks_for_cadence / get_due_cadences -----------------
    def test_tasks_for_cadence_denies_off_scope_building(self):
        self._daily_task()
        with _as_user(self.scoped):
            # Own building: allowed.
            out = get_tasks_for_cadence(self.b1, "Daily")
            self.assertEqual(out["building"], self.b1)
            # Off-scope building: denied via the building-read gate.
            with self.assertRaises(frappe.PermissionError):
                get_tasks_for_cadence(self.b2, "Daily")

    def test_due_cadences_denies_off_scope_building(self):
        self._daily_task()
        with _as_user(self.scoped):
            out = get_due_cadences(self.b1)
            self.assertEqual(out["building"], self.b1)
            with self.assertRaises(frappe.PermissionError):
                get_due_cadences(self.b2)

    def test_safety_reads_unrestricted_for_oversight(self):
        self._daily_task()
        with _as_user(self.oversight):
            # Oversight may build a checklist for ANY estate.
            self.assertEqual(get_tasks_for_cadence(self.b2, "Daily")["building"], self.b2)
            self.assertEqual(get_due_cadences(self.b2)["building"], self.b2)
