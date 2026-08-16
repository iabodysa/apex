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

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.doctype.masar_worker_token.masar_worker_token import (
    _hash_token,
)
from apex.habitat.api.arrivals_desk import (
    _assert_party_in_scope,
    get_arrival_card,
    get_arrival_slip,
    send_masar_link_message,
)
from apex.salis.api import masar, messaging_gateway
from apex.tests._helpers import as_user


def _h(n=12):
    return frappe.generate_hash(length=n).upper()


class TestArrivalsCardScope(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.b1 = cls._building()
        cls.b2 = cls._building()
        cls.scoped = cls._user("Resident Supervisor", building=cls.b1)
        cls.oversight = cls._user("Accommodation Manager")
        cls.tw1 = cls._temp_worker(cls.b1)
        cls.tw2 = cls._temp_worker(cls.b2)

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
    def _employee(cls, phone=None):
        doc = frappe.get_doc(
            {
                "doctype": "Employee",
                "employee_name": "Emp " + _h(),
                "first_name": "Emp",
                "status": "Active",
                "gender": "Male",
                "date_of_birth": "1990-01-01",
                "date_of_joining": "2020-01-01",
                "cell_number": phone,
            }
        )
        doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        cls.addClassCleanup(
            frappe.delete_doc, "Employee", doc.name, force=True, ignore_permissions=True
        )
        return doc.name

    @classmethod
    def _worker_token(cls, employee):
        doc = frappe.get_doc(
            {
                "doctype": "Masar Worker Token",
                "holder_type": "Worker",
                "party_type": "Employee",
                "party": employee,
                "employee": employee,
                "enabled": 1,
            }
        ).insert(ignore_permissions=True)
        cls.addClassCleanup(
            frappe.delete_doc,
            "Masar Worker Token",
            doc.name,
            force=True,
            ignore_permissions=True,
        )
        return doc

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

    def test_card_scoped_user_allowed_own_building(self):
        with as_user(self.scoped):
            card = get_arrival_card(party_type="Temporary Worker", party=self.tw1)
        self.assertEqual(card["party"], self.tw1)
        self.assertEqual(card["worker_name"], frappe.db.get_value(
            "Temporary Worker", self.tw1, "worker_name"))

    def test_card_scoped_user_denied_other_building(self):
        """A b1-scoped supervisor cannot read a b2 worker's card at all."""
        with as_user(self.scoped):
            with self.assertRaises(frappe.PermissionError):
                get_arrival_card(party_type="Temporary Worker", party=self.tw2)

    def test_card_oversight_unrestricted(self):
        with as_user(self.oversight):
            self.assertEqual(
                get_arrival_card(party_type="Temporary Worker", party=self.tw2)["party"], self.tw2
            )

    def test_employee_housed_other_building_denied(self):
        """An Employee actively housed in b2 must be denied by the scope gate."""
        emp = self._employee()
        self._house(emp, self.b2)
        with as_user(self.scoped):
            with self.assertRaises(frappe.PermissionError):
                _assert_party_in_scope("Employee", emp)

    def test_employee_unhoused_allowed_for_intake(self):
        """An unhoused Employee (intake) passes the scope gate for both the general
        check-in lookup AND the R7 front_desk.get_employee_card intake path — that
        path exposes only name + photo, never PII, and must never be regressed by
        the same gate that later denies a cross-building read."""
        emp = self._employee()
        with as_user(self.scoped):
            self.assertIsNone(
                _assert_party_in_scope("Employee", emp),
                "an unhoused employee must pass the scope gate for intake",
            )

    def test_employee_housed_own_building_allowed(self):
        emp = self._employee()
        self._house(emp, self.b1)
        with as_user(self.scoped):
            _assert_party_in_scope("Employee", emp)

    def test_card_full_stack_housed_other_building_denied(self):
        """Full-stack belt-and-suspenders: get_arrival_card for an out-of-estate
        Employee raises (whether from the HRMS type gate or the building scope gate,
        the out-of-scope card is never returned)."""
        emp = self._employee()
        self._house(emp, self.b2)
        with as_user(self.scoped):
            with self.assertRaises(frappe.PermissionError):
                get_arrival_card(party_type="Employee", party=emp)

    def test_front_desk_card_housed_other_building_denied(self):
        """R7: front_desk.get_employee_card (name+photo) now applies the same building
        scope — an employee housed in another estate is denied to a scoped user (the
        scope gate fires regardless of the orthogonal HRMS type-level Employee read)."""
        from apex.habitat.api.front_desk import get_employee_card

        emp = self._employee()
        self._house(emp, self.b2)
        with as_user(self.scoped):
            with self.assertRaises(frappe.PermissionError):
                get_employee_card(emp)

    def test_slip_scoped_user_denied_other_building_pii(self):
        """The headline: a b1-scoped user must NOT receive b2's passport / Iqama.

        Asserts the call raises PermissionError (not that the PII is merely absent)
        — the gate fires before any get_value on the permlevel-1 fields.
        """
        with as_user(self.scoped):
            with self.assertRaises(frappe.PermissionError):
                get_arrival_slip(party_type="Temporary Worker", party=self.tw2)

    def test_slip_scoped_user_allowed_own_building(self):
        with as_user(self.scoped):
            out = get_arrival_slip(party_type="Temporary Worker", party=self.tw1)
        self.assertIn("html", out)

    def test_slip_pii_never_leaks_to_off_scope_user(self):
        """Belt-and-suspenders: capture the rendered HTML on denial path and prove
        the foreign passport / Iqama string never appears."""
        passport, iqama = frappe.db.get_value(
            "Temporary Worker", self.tw2, ["passport_number", "iqama_number"]
        )
        with as_user(self.scoped):
            try:
                out = get_arrival_slip(party_type="Temporary Worker", party=self.tw2)
                html = out.get("html", "")
            except frappe.PermissionError:
                html = ""
        self.assertNotIn(passport, html, "off-scope passport must never reach the caller")
        self.assertNotIn(iqama, html, "off-scope Iqama must never reach the caller")

    def test_send_link_denies_foreign_building_employee(self):
        employee = self._employee(phone="+966511111111")
        self._house(employee, self.b2)
        self._worker_token(employee)

        with as_user(self.scoped), self.assertRaises(frappe.PermissionError):
            send_masar_link_message(employee)

    def test_send_link_rejects_attacker_selected_phone(self):
        employee = self._employee(phone="+966511111111")
        self._house(employee, self.b1)
        self._worker_token(employee)

        with as_user(self.scoped), self.assertRaises(
            frappe.PermissionError
        ) as error:
            send_masar_link_message(employee, phone="+966500000000")

        self.assertIn("phone", str(error.exception).lower())

    def test_scoped_arrival_slip_rotates_worker_credential(self):
        employee = self._employee(phone="+966 51-111-1111")
        self._house(employee, self.b1)
        token = self._worker_token(employee)
        previous_raw = token._plaintext_token
        has_permission = frappe.has_permission

        def allow_employee_read(doctype=None, ptype="read", *args, **kwargs):
            if doctype == "Employee" and ptype == "read":
                return True
            return has_permission(doctype, ptype, *args, **kwargs)

        with patch(
            "frappe.has_permission", side_effect=allow_employee_read
        ):
            with as_user(self.scoped):
                slip = get_arrival_slip(
                    party_type="Employee", party=employee
                )

        persisted_hash = frappe.db.get_value(
            "Masar Worker Token", token.name, "token"
        )
        self.assertIn("data:image/svg+xml;base64", slip["html"])
        self.assertNotEqual(persisted_hash, _hash_token(previous_raw))
        with self.assertRaises(frappe.PermissionError):
            masar._resolve_worker(previous_raw)

    def test_scoped_send_rotates_and_queues_only_stored_phone(self):
        employee = self._employee(phone="+966 51-111-1111")
        self._house(employee, self.b1)
        token = self._worker_token(employee)
        previous_raw = token._plaintext_token

        with patch(
            "apex.salis.api.messaging_gateway.enqueue_message",
            return_value={"queued": True},
        ) as enqueue_message, patch(
            "apex.salis.api.messaging_gateway.is_configured",
            return_value=True,
        ):
            with as_user(self.scoped):
                result = send_masar_link_message(employee)

        self.assertTrue(result["queued"])
        self.assertEqual(enqueue_message.call_args.args[0], "+966511111111")
        self.assertNotEqual(
            frappe.db.get_value(
                "Masar Worker Token", token.name, "token"
            ),
            _hash_token(previous_raw),
        )
        with self.assertRaises(frappe.PermissionError):
            masar._resolve_worker(previous_raw)

    def test_scoped_send_unconfigured_gateway_preserves_credential(self):
        employee = self._employee(phone="+966 51-111-1111")
        self._house(employee, self.b1)
        token = self._worker_token(employee)
        previous_raw = token._plaintext_token

        with patch(
            "apex.salis.api.messaging_gateway.is_configured",
            return_value=False,
        ), patch(
            "apex.salis.api.messaging_gateway.enqueue_message"
        ) as enqueue_message:
            with as_user(self.scoped):
                result = send_masar_link_message(employee)

        self.assertFalse(result["queued"])
        self.assertEqual(result["reason"], "not_configured")
        enqueue_message.assert_not_called()
        self.assertEqual(
            frappe.db.get_value("Masar Worker Token", token.name, "token"),
            _hash_token(previous_raw),
        )
        self.assertEqual(masar._resolve_worker(previous_raw), employee)

    def test_scoped_send_missing_stored_phone_preserves_credential(self):
        employee = self._employee()
        self._house(employee, self.b1)
        token = self._worker_token(employee)
        previous_raw = token._plaintext_token

        with patch(
            "apex.salis.api.messaging_gateway.is_configured",
            return_value=True,
        ), patch(
            "apex.salis.api.messaging_gateway.enqueue_message"
        ) as enqueue_message:
            with as_user(self.scoped):
                result = send_masar_link_message(employee)

        self.assertFalse(result["queued"])
        self.assertEqual(result["reason"], "no_phone")
        enqueue_message.assert_not_called()
        self.assertEqual(
            frappe.db.get_value("Masar Worker Token", token.name, "token"),
            _hash_token(previous_raw),
        )
        self.assertEqual(masar._resolve_worker(previous_raw), employee)

    def test_scoped_send_enqueue_rejection_rolls_back_rotation(self):
        employee = self._employee(phone="+966 51-111-1111")
        self._house(employee, self.b1)
        token = self._worker_token(employee)
        previous_raw = token._plaintext_token

        with patch(
            "apex.salis.api.messaging_gateway.is_configured",
            return_value=True,
        ), patch(
            "apex.salis.api.messaging_gateway.enqueue_message",
            return_value={"queued": False, "reason": "gateway_error"},
        ):
            with as_user(self.scoped):
                result = send_masar_link_message(employee)

        self.assertFalse(result["queued"])
        self.assertEqual(result["reason"], "gateway_error")
        self.assertEqual(
            frappe.db.get_value("Masar Worker Token", token.name, "token"),
            _hash_token(previous_raw),
        )
        self.assertEqual(masar._resolve_worker(previous_raw), employee)

    def test_messaging_enqueue_runs_only_after_database_commit(self):
        with patch.object(
            messaging_gateway, "is_configured", return_value=True
        ), patch("frappe.enqueue") as enqueue:
            result = messaging_gateway.enqueue_message(
                "+966511111111", "Personal portal link"
            )

        self.assertTrue(result["queued"])
        self.assertTrue(enqueue.call_args.kwargs["enqueue_after_commit"])
