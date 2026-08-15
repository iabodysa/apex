# Copyright (c) 2026, afmcoltd
"""The stored worker credential is readable by System Manager alone.

The housing role holds no permlevel-1 read on ``token`` / ``token_enc``, and that absence is
deliberate rather than an oversight: its permlevel-0 row stands, so the role still keeps,
creates and maintains the record — it simply never receives the two credential columns.

WHAT IT DOES NOT BUY: the record, not the credential. ``reshare_worker_link`` hands the RAW
token to every issuer role via ``authorize_issuance``, which reads role and scope and never
a permlevel -- deliberately, since re-sharing a link means handing it over. The colocated
re-share test proves it, so nobody reads the row below as more than it is.

A permlevel-1 row is NOT a duplicate of the permlevel-0 row for the same role.
``is_perm_applicable`` keeps only permlevel-0 rows, so the two rows answer different
questions and removing one must not disturb the other. ``test_the_level_zero_row_survived``
proves that off the shipped JSON.

WHERE THE STRIP ACTUALLY LIVES, because it is not where people look. ``frappe.get_doc``
does NOT conceal anything. The concealment is ``apply_fieldlevel_read_permissions``
(frappe/model/document.py), called only on the API paths -- ``frappe.client.get``,
``frappe/desk/form/load.py`` and the REST handlers. Asserting on a raw in-process document
would therefore prove nothing at all, so every read verdict below goes through
``frappe.client.get``.

WHY ``assertIsNone`` IS CORRECT HERE AND WOULD BE WRONG ELSEWHERE. The strip ``delattr``s
the attribute, but ``as_dict`` then rebuilds EVERY column from the meta and coerces the
missing value by FIELDTYPE. ``token`` is Data and ``token_enc`` is Small Text, so both
survive as ``None`` -- and ``token`` additionally lands in the unique-and-empty branch that
sets ``None`` explicitly. Had either field been Currency or Float it would arrive as
``0.0`` via ``flt()``, and an Int as ``0`` via ``cint()`` -- never ``None``.
``assertIsNone`` would then pass vacuously never, and fail on a perfectly concealed field.
Anyone changing the fieldtype of these two columns must change the assertion with it.

FIXTURES. The credential subject is ERPNext's ``_Test Employee``, named by
``test_dependencies``, and the two identities come from the shared ``_user`` get-or-create.
What is built here is the credential row itself, which IS the subject: ``employee`` is
unique on this DocType and the rollback is per CLASS, so each method deletes the row it
minted rather than waiting for a rollback that has not happened yet.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import frappe
from frappe.tests.utils import FrappeTestCase

import apex
from apex.apex_core.doctype.masar_worker_token import masar_worker_token
from apex.apex_core.utils.portal_token_security import hash_token
from apex.tests._helpers import _user

test_dependencies = ["Employee"]

_TOKEN_JSON = (
    Path(apex.__file__).resolve().parent
    / "apex_core"
    / "doctype"
    / "masar_worker_token"
    / "masar_worker_token.json"
)

HOUSING_ROLE = "Accommodation Manager"
PRIVILEGED_ROLE = "System Manager"
CREDENTIAL_FIELDS = ("token", "token_enc")


class TestMasarWorkerTokenCredentialPermlevel(FrappeTestCase):
    """Site-bound. ``frappe.session.user`` is process state that no rollback restores."""

    def setUp(self):
        # Registered BEFORE anything mutates the session, so a mid-test failure still hands
        # the next test an Administrator session.
        self.addCleanup(frappe.set_user, "Administrator")
        frappe.set_user("Administrator")
        self.employee = frappe.db.get_value("Employee", {"first_name": "_Test Employee"})

    def _token(self):
        """An issued credential row. ``before_insert`` always mints, so the row carries a
        real hash and a real ciphertext -- there is nothing to conceal otherwise."""
        name = (
            frappe.get_doc({"doctype": "Masar Worker Token", "employee": self.employee})
            .insert(ignore_permissions=True)
            .name
        )
        self.addCleanup(
            frappe.delete_doc, "Masar Worker Token", name, force=True, ignore_permissions=True
        )
        return name

    def test_housing_role_gets_none_where_system_manager_gets_the_credential(self):
        """THE PAIR. Both verdicts in ONE method so they can never drift apart.

        Split across two methods, a bug that concealed the credential from EVERYBODY would
        satisfy the refusal half and read as correct. The final assertion states the
        difference outright: same document, same two columns, two roles, two outcomes.
        """
        name = self._token()
        housing = _user("cred_housing@example.com", HOUSING_ROLE)
        privileged = _user("cred_privileged@example.com", PRIVILEGED_ROLE)

        # Verdict A -- the withdrawn role receives nothing.
        frappe.set_user(housing)
        stripped = frappe.client.get("Masar Worker Token", name)
        for fieldname in CREDENTIAL_FIELDS:
            self.assertIsNone(
                stripped.get(fieldname), f"{HOUSING_ROLE} can still read {fieldname}"
            )
        self.assertEqual(
            stripped.get("employee"),
            frappe.db.get_value("Masar Worker Token", name, "employee"),
            "a level-0 field was stripped too -- the removal took the whole record",
        )

        # Verdict B -- the retained role still receives the credential. Note this runs as a
        # REAL System Manager, never Administrator: the strip returns early for
        # Administrator and the verdict would be vacuous.
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
        """The shipped JSON, checked rather than trusted. ``frappe.get_meta`` answers off
        the DATABASE, so a green meta assertion on an un-migrated site would grade the old
        row; this one grades the file that migrate will import."""
        shipped = json.loads(_TOKEN_JSON.read_text(encoding="utf-8"))
        high = {p["role"] for p in shipped["permissions"] if int(p.get("permlevel") or 0) == 1}
        self.assertEqual(
            high,
            {PRIVILEGED_ROLE},
            "the permlevel-1 role set changed -- only System Manager may hold level 1",
        )
        for fieldname in CREDENTIAL_FIELDS:
            field = [f for f in shipped["fields"] if f["fieldname"] == fieldname][0]
            self.assertEqual(
                field.get("permlevel"),
                1,
                f"{fieldname} left permlevel 1 -- the row removal now conceals nothing",
            )

    def test_the_reshare_path_still_hands_the_raw_token_to_a_role_without_level_one(self):
        """WHAT THE PERMLEVEL DOES NOT BUY, proven rather than asserted in prose.

        The row above withholds the stored hash and ciphertext from the housing role. It
        does NOT withhold the credential: ``reshare_worker_link`` returns a link carrying
        the RAW token, because ``authorize_issuance`` gates that path on role and scope and
        never reads a permlevel. Anyone tempted to read the permlevel row as full credential
        protection should fail here first.

        The token itself is never logged or asserted on directly -- only its hash is
        compared, and the stored hash is re-read AFTER the call so the verdict holds on both
        branches of ``recover_token`` (decrypt for an unscoped issuer, rotate for a scoped
        one).
        """
        name = self._token()
        housing = _user("cred_housing@example.com", HOUSING_ROLE)

        frappe.set_user(housing)
        link = masar_worker_token.reshare_worker_link(self.employee)
        self.assertIsNotNone(link, "the issuer got no link at all -- the path changed")

        raw = parse_qs(urlparse(link).query).get("w", [""])[0]
        self.assertTrue(raw, "the link carries no token parameter")
        self.assertEqual(
            hash_token(raw),
            frappe.db.get_value("Masar Worker Token", name, "token"),
            f"{HOUSING_ROLE} received something that is not the live credential",
        )

    def test_the_reshare_docstring_still_names_that_exposure(self):
        """The warning must survive a refactor, so assert it is there.

        A reader who arrives at the permlevel row and stops looking draws the wrong
        conclusion; the docstring on the re-share path is where they are told otherwise.
        Keyed on the two load-bearing words rather than a whole sentence, so rewording is
        free and DELETING the warning is not.
        """
        doc = (inspect.getdoc(masar_worker_token.reshare_worker_link) or "").lower()
        for phrase in ("raw token", "permlevel"):
            self.assertIn(
                phrase,
                doc,
                "reshare_worker_link stopped documenting that every issuer role still "
                f"obtains the raw token there (missing: {phrase!r})",
            )

    def test_the_level_zero_row_survived(self):
        """The explicit non-change. Only a field-level read was withdrawn, not the housing
        role's authority over the record."""
        rows = json.loads(_TOKEN_JSON.read_text(encoding="utf-8"))["permissions"]
        housing = [
            p for p in rows if p["role"] == HOUSING_ROLE and int(p.get("permlevel") or 0) == 0
        ]
        self.assertEqual(len(housing), 1, f"{HOUSING_ROLE} lost or gained a permlevel-0 row")
        for flag in ("read", "write", "create", "print", "report", "share"):
            self.assertEqual(
                housing[0].get(flag),
                1,
                f"{HOUSING_ROLE} permlevel-0 {flag} was collateral damage",
            )
