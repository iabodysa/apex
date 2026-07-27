# Copyright (c) 2026, AFMCO and contributors
"""The stored worker credential is readable by System Manager alone.

Owner decision, 2026-07-27. Of the seven roles holding this DocType, the housing role
was the ONLY peer carrying a permlevel-1 read row on ``token`` / ``token_enc``. No
written reason for that row was ever found -- not in a controller docstring, not in a
colocated test, not in the field descriptions -- so it was withdrawn. Its permlevel-0
row is untouched: the housing role still keeps, creates and maintains the record, it
just stops receiving the two credential columns.

A permlevel-1 row is NOT a duplicate of the permlevel-0 row for the same role.
``is_perm_applicable`` keeps only permlevel-0 rows (frappe/permissions.py:283-284), so
the two rows answer different questions and removing one must not disturb the other.
``test_the_level_zero_row_survived`` proves that off the shipped JSON.

WHERE THE STRIP ACTUALLY LIVES, because it is not where people look
------------------------------------------------------------------
``frappe.get_doc`` does NOT conceal anything. The concealment is
``apply_fieldlevel_read_permissions`` (frappe/model/document.py:754-781), called only
on the API paths -- ``frappe.client.get`` (frappe/client.py:110),
``frappe/desk/form/load.py:53`` and the REST handlers. Asserting on a raw in-process
document would therefore prove nothing at all, so every read verdict below goes
through ``frappe.client.get``.

WHY ``assertIsNone`` IS CORRECT HERE AND WOULD BE WRONG ELSEWHERE
-----------------------------------------------------------------
The strip ``delattr``s the attribute (document.py:771), but ``as_dict`` then rebuilds
EVERY column from the meta and coerces the missing value by FIELDTYPE
(frappe/model/base_document.py:394-406). ``token`` is Data and ``token_enc`` is Small
Text, so both survive as ``None`` -- and ``token`` additionally lands in the
unique-and-empty branch that sets ``None`` explicitly (base_document.py:409-412).

Had either field been Currency or Float it would arrive as ``0.0`` via ``flt()``, and
an Int as ``0`` via ``cint()`` -- never ``None``. ``assertIsNone`` would then pass
vacuously never, and fail on a perfectly concealed field. Anyone changing the
fieldtype of these two columns must change the assertion with it.

Run under bench:
  bench --site <site> run-tests --module apex.apex_core.doctype.masar_worker_token.test_masar_worker_token_credential_permlevel
"""

from __future__ import annotations

import json
from pathlib import Path

import frappe
from frappe.tests.utils import FrappeTestCase

_TOKEN_JSON = Path(__file__).resolve().parent / "masar_worker_token.json"

HOUSING_ROLE = "Accommodation Manager"
PRIVILEGED_ROLE = "System Manager"
CREDENTIAL_FIELDS = ("token", "token_enc")


class TestMasarWorkerTokenCredentialPermlevel(FrappeTestCase):
    """Site-bound. Fixtures are minted per METHOD: rollback covers rows only, and
    ``frappe.session.user`` is process state that no rollback restores."""

    def setUp(self):
        # Registered BEFORE anything mutates the session, so a mid-test failure still
        # hands the next test an Administrator session.
        self.addCleanup(frappe.set_user, "Administrator")
        frappe.set_user("Administrator")

    def _company(self):
        return (
            frappe.defaults.get_global_default("company")
            or frappe.get_all("Company", limit=1)[0].name
        )

    def _user_with_role(self, role):
        """A fresh System User holding exactly one role.

        The hash is 12 wide deliberately -- a short random fixture name collides over a
        long suite run and the collision surfaces as an unrelated DuplicateEntryError.
        """
        return (
            frappe.get_doc(
                {
                    "doctype": "User",
                    "email": f"cred_{frappe.generate_hash(length=12)}@example.com",
                    "first_name": role.split()[0],
                    "roles": [{"role": role}],
                }
            )
            .insert(ignore_permissions=True)
            .name
        )

    def _employee(self):
        return (
            frappe.get_doc(
                {
                    "doctype": "Employee",
                    "first_name": f"Credential Subject {frappe.generate_hash(length=12)}",
                    "company": self._company(),
                    "status": "Active",
                    "gender": "Male",
                    "date_of_birth": "1990-01-01",
                    "date_of_joining": "2020-01-01",
                }
            )
            .insert(ignore_permissions=True)
            .name
        )

    def _token(self):
        """An issued credential row. ``before_insert`` always mints, so the row carries
        a real hash and a real ciphertext -- there is nothing to conceal otherwise."""
        return (
            frappe.get_doc(
                {"doctype": "Masar Worker Token", "employee": self._employee()}
            )
            .insert(ignore_permissions=True)
            .name
        )

    def test_housing_role_gets_none_where_system_manager_gets_the_credential(self):
        """THE PAIR. Both verdicts in ONE method so they can never drift apart.

        Split across two methods, a bug that concealed the credential from EVERYBODY
        would satisfy the refusal half and read as correct. The final assertion states
        the difference outright: same document, same two columns, two roles, two
        outcomes.
        """
        name = self._token()
        housing = self._user_with_role(HOUSING_ROLE)
        privileged = self._user_with_role(PRIVILEGED_ROLE)

        # Verdict A -- the withdrawn role receives nothing.
        frappe.set_user(housing)
        stripped = frappe.client.get("Masar Worker Token", name)
        for fieldname in CREDENTIAL_FIELDS:
            self.assertIsNone(
                stripped.get(fieldname),
                f"{HOUSING_ROLE} can still read {fieldname}",
            )
        self.assertEqual(
            stripped.get("employee"),
            frappe.db.get_value("Masar Worker Token", name, "employee"),
            "a level-0 field was stripped too -- the removal took the whole record",
        )

        # Verdict B -- the retained role still receives the credential. Note this runs
        # as a REAL System Manager, never Administrator: the strip returns early for
        # Administrator (document.py:756-757) and the verdict would be vacuous.
        frappe.set_user(privileged)
        visible = frappe.client.get("Masar Worker Token", name)
        for fieldname in CREDENTIAL_FIELDS:
            self.assertIsNotNone(
                visible.get(fieldname),
                f"{PRIVILEGED_ROLE} lost {fieldname} -- level 1 is now unreachable by anyone",
            )
        self.assertEqual(
            visible.get("token"),
            frappe.db.get_value("Masar Worker Token", name, "token"),
            f"{PRIVILEGED_ROLE} received something other than the stored hash",
        )

        # The pair, stated: the two roles must not have produced the same answer.
        self.assertNotEqual(
            [stripped.get(f) for f in CREDENTIAL_FIELDS],
            [visible.get(f) for f in CREDENTIAL_FIELDS],
            "both roles read the same values -- the permlevel is not being enforced",
        )

    def test_only_system_manager_holds_a_permlevel_one_row(self):
        """The shipped JSON, checked rather than trusted. ``frappe.get_meta`` answers
        off the DATABASE, so a green meta assertion on an un-migrated site would grade
        the old row; this one grades the file that migrate will import."""
        rows = json.loads(_TOKEN_JSON.read_text(encoding="utf-8"))["permissions"]
        high = {p["role"] for p in rows if int(p.get("permlevel") or 0) == 1}
        self.assertEqual(
            high,
            {PRIVILEGED_ROLE},
            "the permlevel-1 role set changed -- only System Manager may hold level 1",
        )
        fields = json.loads(_TOKEN_JSON.read_text(encoding="utf-8"))["fields"]
        for fieldname in CREDENTIAL_FIELDS:
            field = [f for f in fields if f["fieldname"] == fieldname][0]
            self.assertEqual(
                field.get("permlevel"),
                1,
                f"{fieldname} left permlevel 1 -- the row removal now conceals nothing",
            )

    def test_the_level_zero_row_survived(self):
        """The explicit non-change. Only a field-level read was withdrawn, not the
        housing role's authority over the record."""
        rows = json.loads(_TOKEN_JSON.read_text(encoding="utf-8"))["permissions"]
        housing = [
            p
            for p in rows
            if p["role"] == HOUSING_ROLE and int(p.get("permlevel") or 0) == 0
        ]
        self.assertEqual(
            len(housing), 1, f"{HOUSING_ROLE} lost or gained a permlevel-0 row"
        )
        for flag in ("read", "write", "create", "print", "report", "share"):
            self.assertEqual(
                housing[0].get(flag),
                1,
                f"{HOUSING_ROLE} permlevel-0 {flag} was collateral damage",
            )
