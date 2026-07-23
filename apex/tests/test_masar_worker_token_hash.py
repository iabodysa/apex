# Copyright (c) 2026, AFMCO and contributors
"""P-104 — the Masar Worker Token is hashed AT REST.

The raw personal token must never be stored in clear: a direct read of the
``tabMasar Worker Token`` row must expose ZERO usable secret. The row keeps only a
SHA-256 hash (what the resolver matches) plus a site-key-encrypted recoverable copy
(``token_enc``) so the desk can re-share the SAME link without rotating.

These invariants are proven against the live controller, resolver, and the P-104
migration:
  * a freshly minted token's row holds the HASH (not the raw) — plaintext absent;
  * the raw link still resolves to exactly its worker (contract preserved);
  * the encrypted copy round-trips back to the raw (re-share works);
  * the migration hashes a pre-existing plaintext row in place, the same link keeps
    resolving afterwards, and it is idempotent (never double-hashes).
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils.password import decrypt

from apex.apex_core.doctype.masar_worker_token.masar_worker_token import (
    _hash_token,
    issue_worker_link,
)
from apex.salis.api import masar


class TestMasarWorkerTokenHashedAtRest(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")

    def _company(self):
        return (
            frappe.defaults.get_global_default("company")
            or frappe.get_all("Company", limit=1)[0].name
        )

    def _make_employee(self, suffix):
        tag = f"{self._testMethodName}-{suffix}"
        return (
            frappe.get_doc(
                {
                    "doctype": "Employee",
                    "first_name": f"Masar Hash {tag}",
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

    # [#qnpby5]

    def test_minted_row_stores_the_hash_not_the_raw_token(self):
        """A minted token exposes the RAW value once (via the controller), but the
        stored ``token`` column is its SHA-256 hash — the plaintext is absent from the
        row, so a direct DB read leaks no usable secret."""
        emp = self._make_employee("mint")
        doc = frappe.get_doc(
            {
                "doctype": "Masar Worker Token",
                "party_type": "Employee",
                "party": emp,
                "employee": emp,
                "enabled": 1,
            }
        ).insert(ignore_permissions=True)

        raw = doc._plaintext_token
        self.assertTrue(raw, "the raw token must be available once, right after mint")

        stored = frappe.db.get_value("Masar Worker Token", doc.name, "token")
        # [#5l3onr]
        self.assertNotEqual(stored, raw, "the raw token must never be stored in clear")
        self.assertEqual(stored, _hash_token(raw), "the row must store the SHA-256 hash")
        self.assertEqual(len(stored), 64, "a SHA-256 hex digest is 64 chars")

    def test_raw_link_still_resolves_after_hashing(self):
        """The anti-leak contract is preserved: the raw token (the value baked into
        the worker's /masar link) resolves to exactly its own Employee even though the
        row stores only the hash."""
        emp = self._make_employee("resolve")
        doc = frappe.get_doc(
            {
                "doctype": "Masar Worker Token",
                "party_type": "Employee",
                "party": emp,
                "employee": emp,
                "enabled": 1,
            }
        ).insert(ignore_permissions=True)
        raw = doc._plaintext_token

        self.assertEqual(masar._resolve_worker(raw), emp)
        # [#pjomex]
        self.assertEqual(masar.get_worker_context(token=raw)["employee"], emp)
        # [#lvscif]
        with self.assertRaises(frappe.PermissionError):
            masar._resolve_worker(doc.token)

    def test_encrypted_copy_round_trips_to_the_raw_token(self):
        """``token_enc`` is a recoverable (site-key) copy so the desk can re-share the
        SAME link without rotating; it decrypts back to the raw, and it is NOT the raw
        in clear (a DB read of it is useless without the site key)."""
        emp = self._make_employee("enc")
        doc = frappe.get_doc(
            {
                "doctype": "Masar Worker Token",
                "party_type": "Employee",
                "party": emp,
                "employee": emp,
                "enabled": 1,
            }
        ).insert(ignore_permissions=True)
        raw = doc._plaintext_token

        enc = frappe.db.get_value("Masar Worker Token", doc.name, "token_enc")
        self.assertTrue(enc, "an encrypted recoverable copy must be stored")
        self.assertNotEqual(enc, raw, "the encrypted copy must not equal the raw token")
        self.assertEqual(decrypt(enc), raw, "the encrypted copy must round-trip to the raw")

    def test_issue_worker_link_shows_raw_but_stores_hash(self):
        """The desk issuer returns the RAW token/link (shown once) while the row it
        wrote stores only the hash — the show-once, hash-at-rest guarantee end to end."""
        emp = self._make_employee("issue")
        res = issue_worker_link(employee=emp)
        raw = res["token"]
        self.assertIn(raw, res["link"], "the returned link must carry the raw token")
        self.assertEqual(masar._resolve_worker(raw), emp, "the issued link must resolve")

        stored = frappe.db.get_value("Masar Worker Token", {"employee": emp}, "token")
        self.assertEqual(stored, _hash_token(raw), "the row must store only the hash")
        self.assertNotEqual(stored, raw)

    # [#ean2an]

    def test_migration_hashes_a_plaintext_row_and_link_survives(self):
        """The P-104 migration: a pre-existing row carrying a PLAINTEXT token (forced
        in below the controller, as a legacy row would be) is hashed in place, gets an
        encrypted recoverable copy, and the SAME link keeps resolving afterwards —
        proving no currently distributed link is invalidated."""
        from apex.patches.v1_x.backfill_masar_token_expiry import (
            execute as backfill_expiry,
        )
        from apex.patches.v1_x.hash_masar_worker_tokens import execute

        emp = self._make_employee("migrate")
        raw = frappe.generate_hash(length=48)
        # [#smvzqb]
        frappe.get_doc(
            {
                "doctype": "Masar Worker Token",
                "name": emp,
                "holder_type": "Worker",
                "party_type": "Employee",
                "party": emp,
                "employee": emp,
                "enabled": 1,
                "token": raw,
            }
        ).db_insert()
        # [#6amc17]
        self.assertEqual(frappe.db.get_value("Masar Worker Token", emp, "token"), raw)

        backfill_expiry()
        execute()

        stored = frappe.db.get_value("Masar Worker Token", emp, "token")
        self.assertEqual(stored, _hash_token(raw), "the plaintext must be replaced by its hash")
        self.assertNotEqual(stored, raw, "no plaintext token may remain in the row")
        self.assertTrue(
            frappe.db.get_value("Masar Worker Token", emp, "token_enc"),
            "the migration must stash an encrypted recoverable copy",
        )
        self.assertGreater(
            frappe.utils.get_datetime(
                frappe.db.get_value("Masar Worker Token", emp, "expires_on")
            ),
            frappe.utils.now_datetime(),
            "the earlier expiry backfill must make the migrated token usable",
        )
        # [#liazqs]
        self.assertEqual(masar._resolve_worker(raw), emp)

    def test_migration_is_idempotent(self):
        """Re-running the migration never double-hashes an already-hashed row (its raw
        is, correctly, unrecoverable) — the stored hash is stable across runs."""
        from apex.patches.v1_x.hash_masar_worker_tokens import execute

        emp = self._make_employee("idem")
        raw = frappe.generate_hash(length=48)
        frappe.get_doc(
            {
                "doctype": "Masar Worker Token",
                "name": emp,
                "party_type": "Employee",
                "party": emp,
                "employee": emp,
                "enabled": 1,
                "token": raw,
            }
        ).db_insert()

        execute()
        after_first = frappe.db.get_value("Masar Worker Token", emp, "token")
        execute()
        after_second = frappe.db.get_value("Masar Worker Token", emp, "token")
        self.assertEqual(after_first, _hash_token(raw))
        self.assertEqual(after_first, after_second, "a second run must not re-hash the hash")
