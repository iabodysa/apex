# Copyright (c) 2026, AFMCO and contributors
"""`signature` moved to permlevel 1 on Custody Issue.

The field_sensitivity model calls a captured signature an ABSOLUTE level-1 category —
biometric-adjacent, the raw material for forgery, sensitive wherever it appears. The
recipient signs at handover; before this change every role holding read on the issue read
that mark, including Internal Auditor, whose interest in a custody issue is the ITEMS and
the dates, not the worker's signature.

WHY THE THREE ROLES HOLD WRITE AND NOT ONLY READ
------------------------------------------------
System Manager, Accommodation Manager and Resident Supervisor are exactly the three roles on
the Custody Kiosk page (custody_kiosk.json), which is where the signature is taken.
`issue_custody` sets it on a brand-new document and calls
`doc.insert(ignore_permissions=False)` (habitat/api/custody_kiosk.py:350,352). On a NEW
document the framework resolves an unreachable level from `frappe.new_doc(self.doctype)`
rather than from the stored row (frappe/model/base_document.py:1277-1279), so a kiosk
operator without a level-1 WRITE row would have the signature silently emptied on insert —
no exception, and `acknowledged_on` beside it still stamped. Read-only rows would have
turned a privacy fix into a data-loss bug.

Internal Auditor deliberately holds no level-1 row. That omission is the change.

WHAT THIS DOES NOT PROTECT
--------------------------
`permlevel` is not enforced under `frappe.get_all`, which returns early on
`ignore_permissions` (frappe/model/db_query.py:683-684) — the way every Script Report here
reads. Checked in the same pass: the one report over this DocType,
`checkout_pending_clearance`, selects outstanding-item and clearance columns and never
selects `signature`; a repo-wide search finds no report tree selecting any signature field.
So the level is the whole control today, and a future report adding the column would bypass
it silently.

Run under bench:
  bench --site <site> run-tests --module apex.habitat.doctype.custody_issue.test_custody_issue_signature_permlevel
"""

from __future__ import annotations

import json
from pathlib import Path

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate

_CUSTODY_ISSUE_JSON = Path(__file__).resolve().parent / "custody_issue.json"

# Both roles are in habitat.permissions.HOUSING_UNSCOPED_ROLES, so
# `building_scoped_has_permission` defers for both (permissions.py:451-452). That is
# deliberate: a building-scoped role would be blocked by the SCOPE before the permlevel was
# ever consulted, and the pair below would prove nothing about levels.
KIOSK_ROLE = "Accommodation Manager"
AUDIT_ROLE = "Internal Auditor"
KIOSK_ROLES = {"System Manager", "Accommodation Manager", "Resident Supervisor"}

_SIGNATURE = "data:image/png;base64,iVBORw0KGgo="

test_ignore = ["Employee", "Role", "User"]


class TestCustodyIssueSignaturePermlevel(FrappeTestCase):
    """Site-bound. Fixtures per METHOD: rollback is rows-only, so a shared document would
    carry the previous method's mutations."""

    def setUp(self):
        # Process state, restored by no rollback — register the cleanup before touching it.
        self.addCleanup(frappe.set_user, "Administrator")
        frappe.set_user("Administrator")

    def _user_with_role(self, role):
        # 12-wide hash: short fixture names collide across a long suite run and surface as
        # an unrelated DuplicateEntryError.
        return frappe.get_doc(
            {
                "doctype": "User",
                "email": f"a308_{frappe.generate_hash(length=12)}@example.com",
                "first_name": role.split()[0],
                "roles": [{"role": role}],
            }
        ).insert(ignore_permissions=True).name

    def _signed_issue(self):
        doc = frappe.get_doc(
            {
                "doctype": "Custody Issue",
                "naming_series": "CUST-ISS-.YYYY.-.####",
                "issue_date": "2026-06-01",
                "building": "QA-BLDG",
                "items": [{"doctype": "Custody Issue Item", "article": "QA-ART", "qty": 1}],
                "signature": _SIGNATURE,
            }
        )
        # Administrator + ignore_permissions: the permlevel gate returns early for both
        # (frappe/model/document.py:785,789), so the fixture holds a real signature whatever
        # the level rows say. Every assertion below is about reading it back as someone else.
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.addCleanup(
            frappe.delete_doc, "Custody Issue", doc.name, force=True, ignore_permissions=True
        )
        return doc

    def test_the_auditor_cannot_read_the_signature_and_the_kiosk_role_can(self):
        """THE PAIR. Both verdicts in one method so they cannot drift, compared as VERDICTS
        ALONE — comparing (role, value, verdict) tuples would pass on the differing role
        literals even with the permlevel removed entirely.

        Read through `frappe.client.get`, because that is where the strip lives
        (frappe/client.py:110); an in-process `frappe.get_doc` does not strip.
        """
        doc = self._signed_issue()
        auditor = self._user_with_role(AUDIT_ROLE)
        kiosk = self._user_with_role(KIOSK_ROLE)

        # The access itself, before either read — otherwise the outcomes below say nothing
        # about permlevels.
        frappe.set_user(kiosk)
        self.assertIn(
            1,
            frappe.get_doc("Custody Issue", doc.name).get_permlevel_access("read"),
            f"{KIOSK_ROLE} lost its permlevel-1 read row",
        )
        frappe.set_user(auditor)
        self.assertNotIn(
            1,
            frappe.get_doc("Custody Issue", doc.name).get_permlevel_access("read"),
            f"{AUDIT_ROLE} reaches permlevel 1",
        )

        # Verdict A — CONCEALED. assertFalse, not assertIsNone: the strip deletes the
        # attribute (document.py:771) but `as_dict` rebuilds every column and coerces it by
        # fieldtype (base_document.py:402), so what returns depends on the fieldtype rather
        # than on whether the strip worked.
        frappe.set_user(auditor)
        audited = frappe.client.get("Custody Issue", doc.name)
        self.assertFalse(
            audited.get("signature"), f"{AUDIT_ROLE} can still read the recipient's signature"
        )
        # Presence first: `getdate(None)` returns TODAY (frappe/utils/data.py:91-92), so a
        # stripped date would still compare as a real one and the clause below would go
        # vacuous the day this fixture is reseeded with `today()`.
        self.assertTrue(
            audited.get("issue_date"),
            "the strip removed a level-0 date — it is supposed to be surgical",
        )
        # Both sides through `getdate`: the round-tripped copy is a `datetime.date` while the
        # fixture still holds the string it was seeded with, so a raw comparison fails on
        # TYPE even when the value survived intact.
        self.assertEqual(
            getdate(audited.get("issue_date")),
            getdate(doc.issue_date),
            "level-0 custody facts must survive the strip — the auditor still audits",
        )

        # Verdict B — VISIBLE.
        frappe.set_user(kiosk)
        at_kiosk = frappe.client.get("Custody Issue", doc.name)
        self.assertEqual(
            at_kiosk.get("signature"),
            _SIGNATURE,
            f"{KIOSK_ROLE} lost the signature its own kiosk captured",
        )

        audit_verdict = "visible" if audited.get("signature") else "concealed"
        kiosk_verdict = "visible" if at_kiosk.get("signature") else "concealed"
        self.assertNotEqual(
            audit_verdict,
            kiosk_verdict,
            f"both roles produced the same verdict ({audit_verdict}) — the pair collapsed: "
            "either the permlevel stopped being enforced for anyone, or it is now enforced "
            f"against {KIOSK_ROLE} too",
        )

    def test_the_kiosk_create_path_keeps_the_signature(self):
        """The regression this move could plausibly have caused.

        `issue_custody` sets the signature on a new document and inserts it with
        `ignore_permissions=False`. On a new document the reference for an unreachable level
        is `frappe.new_doc` — the DEFAULT, not the stored row — so a caller with no level-1
        row has it silently emptied. This calls `validate_higher_perm_levels` directly, the
        exact call `insert` makes (document.py:306), so the outcome is about the permlevel
        and not about the unrelated link permissions a full insert needs.
        """
        kiosk = self._user_with_role(KIOSK_ROLE)
        auditor = self._user_with_role(AUDIT_ROLE)

        def surviving_signature(as_user):
            frappe.set_user(as_user)
            fresh = frappe.get_doc(
                {
                    "doctype": "Custody Issue",
                    "naming_series": "CUST-ISS-.YYYY.-.####",
                    "issue_date": "2026-06-01",
                    "building": "QA-BLDG",
                    "items": [{"doctype": "Custody Issue Item", "article": "QA-ART", "qty": 1}],
                    "signature": _SIGNATURE,
                }
            )
            # `insert` sets this at document.py:295, eleven lines before it calls
            # validate_higher_perm_levels at :306, and `is_new()` reads exactly that flag
            # (base_document.py:465). Setting it here is what makes this the CREATE path:
            # without it the reset would resolve from `get_latest()` — a stored row that
            # does not exist yet — and the test would silently be about updates instead.
            fresh.set("__islocal", True)
            self.assertTrue(fresh.is_new(), "precondition: the create path needs a NEW doc")
            fresh.validate_higher_perm_levels()
            return fresh.signature

        kept = surviving_signature(kiosk)
        blanked = surviving_signature(auditor)

        self.assertEqual(
            kept,
            _SIGNATURE,
            f"{KIOSK_ROLE} lost the signature on the CREATE path — the kiosk would file "
            "handovers stamped acknowledged with no signature behind them",
        )
        self.assertFalse(
            blanked, "a role with no permlevel-1 row kept a signature it cannot reach on create"
        )
        kept_verdict = "kept" if kept else "blanked"
        blanked_verdict = "kept" if blanked else "blanked"
        self.assertNotEqual(
            kept_verdict,
            blanked_verdict,
            f"both roles produced the same verdict ({kept_verdict}) — this pair no longer "
            "distinguishes a role holding the level-1 write row from one that does not",
        )

    def test_the_signature_is_level_one_with_rows_for_the_kiosk_roles_only(self):
        """The shipped JSON, checked rather than trusted.

        Rows are counted on the (role, permlevel) PAIR, never on the role alone: a level-1
        row is not a duplicate of that role's level-0 row — `is_perm_applicable` keeps only
        permlevel-0 rows (frappe/permissions.py:284) — so deduplicating on role would strip
        exactly the access this change depends on.
        """
        shipped = json.loads(_CUSTODY_ISSUE_JSON.read_text(encoding="utf-8"))
        rows = shipped["permissions"]

        high = {p["role"] for p in rows if int(p.get("permlevel") or 0) == 1}
        self.assertEqual(
            high,
            KIOSK_ROLES,
            "the permlevel-1 role set changed. Adding a role hands it every recipient's "
            "signature; removing one blanks the signature that role captures at the kiosk.",
        )
        self.assertNotIn(AUDIT_ROLE, high, f"{AUDIT_ROLE} must not reach the signature")
        for role in sorted(high):
            row = [p for p in rows if p["role"] == role and int(p.get("permlevel") or 0) == 1]
            self.assertEqual(len(row), 1, f"{role}: expected exactly one permlevel-1 row")
            # Asserted explicitly, never by omission: an absent DocPerm flag ships as 0
            # rather than as its default, so a row written by omission grants nothing.
            self.assertEqual(row[0].get("read"), 1, f"{role}: permlevel-1 read missing")
            self.assertEqual(
                row[0].get("write"),
                1,
                f"{role}: permlevel-1 write missing — the kiosk would blank the signature "
                "it captures, on every handover",
            )

        signature = [f for f in shipped["fields"] if f["fieldname"] == "signature"][0]
        self.assertEqual(signature.get("permlevel"), 1, "signature is not at permlevel 1")
        described = (signature.get("description") or "").lower()
        # Checked for MEANING, not for the token `permlevel`: this is the tooltip a kiosk
        # operator reads, and user-facing text carries no system jargon.
        self.assertIn("signature", described, "the tooltip no longer says what the field is")
        self.assertTrue(
            {"because", "so", "since"} & set(described.split()),
            "the tooltip states the restriction but never says WHY it is restricted",
        )
        # Say WHO keeps the field and WHY, never HOW it is enforced: this text reaches a
        # kiosk operator and the translators, and "level 1" means nothing to either.
        for jargon in ("permlevel", "level 1", "level 0", "docperm"):
            self.assertNotIn(
                jargon, described, f"the tooltip leaks the system term {jargon!r} to an operator"
            )

    def test_the_auditors_level_zero_authority_was_not_collateral_damage(self):
        """The explicit non-change: one field narrowed, not a role's authority."""
        shipped = json.loads(_CUSTODY_ISSUE_JSON.read_text(encoding="utf-8"))
        auditor = [
            p
            for p in shipped["permissions"]
            if p["role"] == AUDIT_ROLE and int(p.get("permlevel") or 0) == 0
        ]
        self.assertEqual(len(auditor), 1, "the auditor's level-0 row was moved or duplicated")
        self.assertEqual(auditor[0].get("read"), 1, "the auditor's read was revoked")
        self.assertEqual(auditor[0].get("export"), 1, "the auditor's export was revoked")
        self.assertEqual(auditor[0].get("report"), 1, "the auditor's report access was revoked")
