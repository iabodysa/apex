# Copyright (c) 2026, afmcoltd
"""P-104 — the Masar Worker Token is hashed AT REST.

The raw personal token must never be stored in clear: a direct read of the
``tabMasar Worker Token`` row must expose ZERO usable secret. The row keeps only a SHA-256
hash (what the resolver matches) plus a site-key-encrypted recoverable copy (``token_enc``)
so the desk can re-share the SAME link without rotating.

These invariants are proven against the live controller and resolver:
  * a freshly minted token's row holds the HASH (not the raw) — plaintext absent;
  * the raw link still resolves to exactly its worker (contract preserved);
  * the encrypted copy round-trips back to the raw (re-share works);
  * the desk issuer shows the raw once while the row it wrote stores only the hash.

Nothing here builds a worker. ``test_dependencies = ["Employee"]`` stands ERPNext's own
Employee fixtures up once per run — the previous form of this file minted a fresh Employee
per test method (four Employees, and a Company lookup for each) to hang one token on.

ONE TOKEN PER EMPLOYEE IS THE MODEL, so the fixture employee cannot carry two at once:
``autoname`` names the row after the party and ``employee`` is unique. ``FrappeTestCase``
rolls back per CLASS, not per test, so each case hands its token back with ``addCleanup``
instead of relying on a rollback that has not happened yet.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils.password import decrypt

from apex.apex_core.doctype.masar_worker_token.masar_worker_token import (
    _hash_token,
    issue_worker_link,
)
from apex.salis.api import masar

test_dependencies = ["Employee"]


class TestMasarWorkerTokenHashedAtRest(FrappeTestCase):
    def setUp(self):
        self.employee = frappe.db.get_value("Employee", {"first_name": "_Test Employee"})
        self.addCleanup(frappe.set_user, "Administrator")

    def _mint(self):
        """Insert a worker token for the fixture employee and hand the row back after."""
        doc = frappe.get_doc(
            {
                "doctype": "Masar Worker Token",
                "party_type": "Employee",
                "party": self.employee,
                "employee": self.employee,
                "enabled": 1,
            }
        ).insert(ignore_permissions=True)
        self.addCleanup(
            frappe.delete_doc,
            "Masar Worker Token",
            doc.name,
            force=True,
            ignore_permissions=True,
        )
        return doc

    def test_minted_row_stores_the_hash_not_the_raw_token(self):
        """A minted token exposes the RAW value once (via the controller), but the stored
        ``token`` column is its SHA-256 hash — the plaintext is absent from the row, so a
        direct DB read leaks no usable secret."""
        doc = self._mint()
        raw = doc._plaintext_token
        self.assertTrue(raw, "the raw token must be available once, right after mint")

        stored = frappe.db.get_value("Masar Worker Token", doc.name, "token")
        self.assertNotEqual(stored, raw, "the raw token must never be stored in clear")
        self.assertEqual(stored, _hash_token(raw), "the row must store the SHA-256 hash")
        self.assertEqual(len(stored), 64, "a SHA-256 hex digest is 64 chars")

    def test_raw_link_still_resolves_after_hashing(self):
        """The anti-leak contract is preserved: the raw token (the value baked into the
        worker's /masar link) resolves to exactly its own Employee even though the row
        stores only the hash."""
        doc = self._mint()
        raw = doc._plaintext_token

        self.assertEqual(masar._resolve_worker(raw), self.employee)
        self.assertEqual(masar.get_worker_context(token=raw)["employee"], self.employee)
        with self.assertRaises(frappe.PermissionError):
            masar._resolve_worker(doc.token)

    def test_encrypted_copy_round_trips_to_the_raw_token(self):
        """``token_enc`` is a recoverable (site-key) copy so the desk can re-share the SAME
        link without rotating; it decrypts back to the raw, and it is NOT the raw in clear
        (a DB read of it is useless without the site key)."""
        doc = self._mint()
        raw = doc._plaintext_token

        enc = frappe.db.get_value("Masar Worker Token", doc.name, "token_enc")
        self.assertTrue(enc, "an encrypted recoverable copy must be stored")
        self.assertNotEqual(enc, raw, "the encrypted copy must not equal the raw token")
        self.assertEqual(decrypt(enc), raw, "the encrypted copy must round-trip to the raw")

    def test_issue_worker_link_shows_raw_but_stores_hash(self):
        """The desk issuer returns the RAW token/link (shown once) while the row it wrote
        stores only the hash — the show-once, hash-at-rest guarantee end to end."""
        res = issue_worker_link(employee=self.employee)
        self.addCleanup(
            frappe.delete_doc,
            "Masar Worker Token",
            self.employee,
            force=True,
            ignore_permissions=True,
        )
        raw = res["token"]
        self.assertIn(raw, res["link"], "the returned link must carry the raw token")
        self.assertEqual(masar._resolve_worker(raw), self.employee, "the issued link must resolve")

        stored = frappe.db.get_value(
            "Masar Worker Token", {"employee": self.employee}, "token"
        )
        self.assertEqual(stored, _hash_token(raw), "the row must store only the hash")
        self.assertNotEqual(stored, raw)
