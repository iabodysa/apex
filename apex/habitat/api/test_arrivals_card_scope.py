# Copyright (c) 2026, AFMCO and contributors
"""Per-doc BUILDING scope for the arrivals-desk identity / PII reads.

``get_arrival_card`` and ``get_arrival_slip`` take a CLIENT-SUPPLIED party
docname. A type-level ``has_permission("Temporary Worker"/"Employee", "read")``
only proves the caller may read the doctype at all — it does NOT confine them to
their own estate. Without a per-doc building gate a scoped supervisor (or any
low-role holder with a type-level read) could harvest another building's worker
identity, and for a Temporary Worker the permlevel-1 ``passport_number`` /
``iqama_number`` (confidential government IDs).

These pin the gate added in ``arrivals_desk._assert_party_in_scope``:
  * a Resident Supervisor scoped (User Permission) to b1 is DENIED a b2 worker's
    card AND slip (no name, no passport, no Iqama leaks) — ``PermissionError``;
  * the same supervisor is ALLOWED their own building's worker;
  * an oversight Accommodation Manager (HOUSING_UNSCOPED_ROLES) is unrestricted.

Rows are inserted with ``ignore_permissions/links/mandatory`` so no controller
side-effect (ledger posting, party-link mirroring) is exercised — these pin the
read SCOPE, not the write controllers.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.api.arrivals_desk import (
    _assert_party_in_scope,
    get_arrival_card,
    get_arrival_slip,
)


def _h(n=12):
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


class TestArrivalsCardScope(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.b1 = cls._building()
        cls.b2 = cls._building()
        cls.scoped = cls._user("Resident Supervisor", building=cls.b1)
        cls.oversight = cls._user("Accommodation Manager")
        # A Temporary Worker in each estate, each carrying a passport + Iqama.
        cls.tw1 = cls._temp_worker(cls.b1)
        cls.tw2 = cls._temp_worker(cls.b2)

    # ---- fixtures ---------------------------------------------------------
    @classmethod
    def _building(cls):
        doc = frappe.get_doc(
            {"doctype": "Building", "building_name": "CARD-" + _h()}
        )
        doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        cls.addClassCleanup(
            frappe.delete_doc, "Building", doc.name, force=True, ignore_permissions=True
        )
        return doc.name

    @classmethod
    def _user(cls, role, building=None):
        roles = [role] if isinstance(role, str) else list(role)
        email = "card-{0}@example.com".format(_h()).lower()
        frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": "Card",
                "send_welcome_email": 0,
                "roles": [{"role": r} for r in roles],
            }
        ).insert(ignore_permissions=True)
        cls.addClassCleanup(frappe.delete_doc, "User", email, force=True, ignore_permissions=True)
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
                frappe.delete_doc, "User Permission", up.name, force=True, ignore_permissions=True
            )
        return email

    @classmethod
    def _employee(cls):
        doc = frappe.get_doc(
            {
                "doctype": "Employee",
                "employee_name": "Emp " + _h(),
                "first_name": "Emp",
                "status": "Active",
            }
        )
        doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        cls.addClassCleanup(
            frappe.delete_doc, "Employee", doc.name, force=True, ignore_permissions=True
        )
        return doc.name

    @classmethod
    def _house(cls, employee, building):
        """A submitted, still-open Accommodation Assignment placing ``employee`` in
        ``building`` (synthetic-row: docstatus flipped via db.set_value)."""
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
        # ignore_validate: bypass the assignment controller (project / cost-center
        # write-gates). These tests pin the READ scope of the arrivals desk, not the
        # assignment write controller — the row only needs party/building/docstatus.
        doc.flags.ignore_validate = True
        doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        frappe.db.set_value("Housing Assignment", doc.name, "docstatus", 1)
        cls.addClassCleanup(
            lambda n=doc.name: (
                frappe.db.set_value("Housing Assignment", n, "docstatus", 0),
                frappe.delete_doc("Housing Assignment", n, force=True, ignore_permissions=True),
            )
        )
        return doc.name

    @classmethod
    def _temp_worker(cls, building):
        doc = frappe.get_doc(
            {
                "doctype": "Temporary Worker",
                "worker_name": "TW-" + _h(),
                "passport_number": "PASS" + _h(12),
                "iqama_number": "IQ" + _h(12),
                "building": building,
                "status": "Active",
            }
        )
        doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        cls.addClassCleanup(
            frappe.delete_doc, "Temporary Worker", doc.name, force=True, ignore_permissions=True
        )
        return doc.name

    def setUp(self):
        self.addCleanup(frappe.set_user, "Administrator")

    # ---- R2: get_arrival_card --------------------------------------------
    def test_card_scoped_user_allowed_own_building(self):
        with _as_user(self.scoped):
            card = get_arrival_card(party_type="Temporary Worker", party=self.tw1)
        # The scope gate (which reads tw.building) passed -> no PermissionError -> the
        # in-scope worker's card is returned. current_building derives from a LIVE
        # Accommodation Assignment (none here), so it is correctly None — the gate, not
        # the assignment join, is what this test pins.
        self.assertEqual(card["party"], self.tw1)
        self.assertEqual(card["worker_name"], frappe.db.get_value(
            "Temporary Worker", self.tw1, "worker_name"))

    def test_card_scoped_user_denied_other_building(self):
        """A b1-scoped supervisor cannot read a b2 worker's card at all."""
        with _as_user(self.scoped):
            with self.assertRaises(frappe.PermissionError):
                get_arrival_card(party_type="Temporary Worker", party=self.tw2)

    def test_card_oversight_unrestricted(self):
        with _as_user(self.oversight):
            self.assertEqual(
                get_arrival_card(party_type="Temporary Worker", party=self.tw2)["party"], self.tw2
            )

    # ---- R2 Employee path: housed-elsewhere denied, intake allowed -------
    # The Employee branch of the building scope is exercised against
    # _assert_party_in_scope directly: the desk's pre-existing
    # has_permission("Employee") gate (HRMS-owned, orthogonal to this fix) denies a
    # building-scoped non-HR user a TYPE-LEVEL Employee read regardless of building, so
    # routing through get_arrival_card would conflate the two gates. These pin the
    # PER-BUILDING confinement that this fix adds: housed-elsewhere denied, unhoused
    # intake allowed, housed-own allowed.
    def test_employee_housed_other_building_denied(self):
        """An Employee actively housed in b2 must be denied by the scope gate."""
        emp = self._employee()
        self._house(emp, self.b2)
        with _as_user(self.scoped):
            with self.assertRaises(frappe.PermissionError):
                _assert_party_in_scope("Employee", emp)

    def test_employee_unhoused_allowed_for_intake(self):
        """An unhoused Employee (intake) passes the scope gate so the check-in lookup
        is never broken — that path exposes only name + photo, never PII."""
        emp = self._employee()
        with _as_user(self.scoped):
            _assert_party_in_scope("Employee", emp)  # must NOT raise

    def test_employee_housed_own_building_allowed(self):
        emp = self._employee()
        self._house(emp, self.b1)
        with _as_user(self.scoped):
            _assert_party_in_scope("Employee", emp)  # must NOT raise

    def test_card_full_stack_housed_other_building_denied(self):
        """Full-stack belt-and-suspenders: get_arrival_card for an out-of-estate
        Employee raises (whether from the HRMS type gate or the building scope gate,
        the out-of-scope card is never returned)."""
        emp = self._employee()
        self._house(emp, self.b2)
        with _as_user(self.scoped):
            with self.assertRaises(frappe.PermissionError):
                get_arrival_card(party_type="Employee", party=emp)

    # ---- R7: front-desk check-in card mirrors the same building scope ----
    def test_front_desk_card_housed_other_building_denied(self):
        """R7: front_desk.get_employee_card (name+photo) now applies the same building
        scope — an employee housed in another estate is denied to a scoped user (the
        scope gate fires regardless of the orthogonal HRMS type-level Employee read)."""
        from apex.habitat.api.front_desk import get_employee_card

        emp = self._employee()
        self._house(emp, self.b2)
        with _as_user(self.scoped):
            with self.assertRaises(frappe.PermissionError):
                get_employee_card(emp)

    def test_front_desk_card_unhoused_intake_not_blocked_by_scope(self):
        """R7: the unhoused intake lookup the check-in dialog needs is NOT regressed —
        the building scope gate allows an employee with no live assignment. (The
        orthogonal HRMS type-level Employee read is a separate, pre-existing gate.)"""
        emp = self._employee()
        with _as_user(self.scoped):
            _assert_party_in_scope("Employee", emp)  # scope gate must not raise

    # ---- R1: get_arrival_slip (passport + Iqama PII) ---------------------
    def test_slip_scoped_user_denied_other_building_pii(self):
        """The headline: a b1-scoped user must NOT receive b2's passport / Iqama.

        Asserts the call raises PermissionError (not that the PII is merely absent)
        — the gate fires before any get_value on the permlevel-1 fields.
        """
        with _as_user(self.scoped):
            with self.assertRaises(frappe.PermissionError):
                get_arrival_slip(party_type="Temporary Worker", party=self.tw2)

    def test_slip_scoped_user_allowed_own_building(self):
        with _as_user(self.scoped):
            out = get_arrival_slip(party_type="Temporary Worker", party=self.tw1)
        # The slip renders for the in-scope worker (PII for the OWN estate is allowed).
        self.assertIn("html", out)

    def test_slip_pii_never_leaks_to_off_scope_user(self):
        """Belt-and-suspenders: capture the rendered HTML on denial path and prove
        the foreign passport / Iqama string never appears."""
        passport, iqama = frappe.db.get_value(
            "Temporary Worker", self.tw2, ["passport_number", "iqama_number"]
        )
        with _as_user(self.scoped):
            try:
                out = get_arrival_slip(party_type="Temporary Worker", party=self.tw2)
                html = out.get("html", "")
            except frappe.PermissionError:
                html = ""
        self.assertNotIn(passport, html, "off-scope passport must never reach the caller")
        self.assertNotIn(iqama, html, "off-scope Iqama must never reach the caller")
