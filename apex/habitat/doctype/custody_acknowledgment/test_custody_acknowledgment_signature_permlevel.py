# Copyright (c) 2026, AFMCO and contributors
"""`signature` moved to permlevel 1 on Custody Acknowledgment.

The field_sensitivity model calls a captured signature an ABSOLUTE level-1 category —
biometric-adjacent, the raw material for forgery. This record is the holder's own receipt
confirmation, so the mark on it belongs to the worker, not to the estate; before this change
every role holding read on the acknowledgment read it, Internal Auditor included.

Level-1 rows go to System Manager, Accommodation Manager and Resident Supervisor — the same
custody-desk set as Custody Issue, because the same desk verifies the acknowledgment against
the handover. Internal Auditor deliberately gets none; that omission is the change.

WHY THE RESIDENT'S OWN WEB FORM DOES NOT BREAK
----------------------------------------------
This is the one DocType in this pass whose signature is written by the SUBJECT rather than
by a member of staff: the My Custody Acknowledgment Web Form, submitted by the worker over
the portal. That is exactly the shape that would break — a portal user holds no level-1 row
and could never be given one — except that Frappe's Web Form does not take the permission
path at all. `accept()` inserts with `doc.insert(ignore_permissions=True, ...)`
(frappe/website/doctype/web_form/web_form.py:663) and re-saves the same way after attaching
the signature data-URI as a File (:691), and `validate_higher_perm_levels` returns
immediately on that flag (frappe/model/document.py:785). No level is consulted, so nothing is
blanked. `test_the_portal_write_path_is_not_subject_to_the_level` pins that property here
rather than trusting it, because the whole portal flow depends on it.

The staff create path still needs the write rows: the three desk roles hold `create` on this
DocType and can record the fallback signature from the Desk, where the permission path IS
taken and a role without a level-1 write row would have it emptied on insert
(frappe/model/base_document.py:1277-1279 — a NEW document resolves an unreachable level from
`frappe.new_doc`, the DEFAULT, not the stored row).

WHAT THIS DOES NOT PROTECT
--------------------------
`permlevel` is not enforced under `frappe.get_all`, which returns early on
`ignore_permissions` (frappe/model/db_query.py:683-684) — how every Script Report here reads.
Checked in the same pass: NO report in the app reads Custody Acknowledgment at all, and no
report tree anywhere selects a signature fieldname. So nothing bypasses the level today.

Run under bench:
  bench --site <site> run-tests --module apex.habitat.doctype.custody_acknowledgment.test_custody_acknowledgment_signature_permlevel
"""

from __future__ import annotations

import json
from pathlib import Path

import frappe
from frappe.tests.utils import FrappeTestCase

_ACK_JSON = Path(__file__).resolve().parent / "custody_acknowledgment.json"

# Both roles sit in habitat.permissions.HOUSING_UNSCOPED_ROLES, so
# `building_scoped_has_permission` defers for both (permissions.py:451-452). A
# building-scoped role would be blocked by the SCOPE before the level was ever consulted,
# and the pair below would prove nothing about levels.
DESK_ROLE = "Accommodation Manager"
AUDIT_ROLE = "Internal Auditor"
DESK_ROLES = {"System Manager", "Accommodation Manager", "Resident Supervisor"}

_SIGNATURE = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUg=="

test_ignore = ["Building", "Custody Article", "Custody Issue", "Employee", "Role", "User"]


class TestCustodyAcknowledgmentSignaturePermlevel(FrappeTestCase):
    """Site-bound. Fixtures per METHOD: rollback is rows-only."""

    def setUp(self):
        # Process state — no rollback restores it. Cleanup registered before the mutation.
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

    def _submitted_issue(self):
        issue = frappe.get_doc(
            {
                "doctype": "Custody Issue",
                "naming_series": "CUST-ISS-.YYYY.-.####",
                "issue_date": "2026-06-01",
                "building": "QA-BLDG",
                "items": [{"doctype": "Custody Issue Item", "article": "QA-ART", "qty": 1}],
            }
        )
        issue.insert(ignore_permissions=True, ignore_links=True)
        issue.submit()
        return issue

    def _signed_ack(self):
        issue = self._submitted_issue()
        ack = frappe.get_doc(
            {
                "doctype": "Custody Acknowledgment",
                "custody_issue": issue.name,
                "confirmation_method": "Signature",
                "signature": _SIGNATURE,
            }
        )
        # Administrator + ignore_permissions: the level gate returns early for both
        # (document.py:785,789), so the fixture holds a real signature whatever the rows
        # say. Every assertion below is about reading it back as someone else.
        ack.insert(ignore_permissions=True, ignore_links=True)
        return ack

    def test_the_auditor_cannot_read_the_signature_and_the_desk_role_can(self):
        """THE PAIR. Both verdicts in one method so they cannot drift, compared as VERDICTS
        ALONE — comparing (role, value, verdict) tuples would pass on the differing role
        literals even with the permlevel removed entirely.

        Read through `frappe.client.get`, where the strip lives (frappe/client.py:110); an
        in-process `frappe.get_doc` does not strip.
        """
        ack = self._signed_ack()
        auditor = self._user_with_role(AUDIT_ROLE)
        desk = self._user_with_role(DESK_ROLE)

        frappe.set_user(desk)
        self.assertIn(
            1,
            frappe.get_doc("Custody Acknowledgment", ack.name).get_permlevel_access("read"),
            f"{DESK_ROLE} lost its permlevel-1 read row",
        )
        frappe.set_user(auditor)
        self.assertNotIn(
            1,
            frappe.get_doc("Custody Acknowledgment", ack.name).get_permlevel_access("read"),
            f"{AUDIT_ROLE} reaches permlevel 1",
        )

        # Verdict A — CONCEALED. assertFalse, not assertIsNone: the strip deletes the
        # attribute (document.py:771) but `as_dict` rebuilds every column and coerces it by
        # fieldtype (base_document.py:402), so the returned value depends on the fieldtype
        # rather than on whether the strip worked.
        frappe.set_user(auditor)
        audited = frappe.client.get("Custody Acknowledgment", ack.name)
        self.assertFalse(
            audited.get("signature"), f"{AUDIT_ROLE} can still read the holder's signature"
        )
        self.assertEqual(
            audited.get("custody_issue"),
            ack.custody_issue,
            "level-0 acknowledgment facts must survive the strip — the auditor still audits",
        )

        # Verdict B — VISIBLE.
        frappe.set_user(desk)
        at_desk = frappe.client.get("Custody Acknowledgment", ack.name)
        self.assertEqual(
            at_desk.get("signature"),
            _SIGNATURE,
            f"{DESK_ROLE} lost the signature it has to verify against the handover",
        )

        audit_verdict = "visible" if audited.get("signature") else "concealed"
        desk_verdict = "visible" if at_desk.get("signature") else "concealed"
        self.assertNotEqual(
            audit_verdict,
            desk_verdict,
            f"both roles produced the same verdict ({audit_verdict}) — the pair collapsed: "
            "either the permlevel stopped being enforced for anyone, or it is now enforced "
            f"against {DESK_ROLE} too",
        )

    def test_the_portal_write_path_is_not_subject_to_the_level(self):
        """The regression that would have been invisible until a worker complained.

        The subject signs this record themselves, over the Web Form, and a portal user can
        never hold a level-1 row. The flow survives only because `web_form.accept` inserts
        with `ignore_permissions=True` (web_form.py:663) and `validate_higher_perm_levels`
        returns immediately on that flag (document.py:785). This asserts that property on
        the real DocType, as a user holding NO level-1 row — if a future change made the
        level apply to an ignore_permissions insert, every portal acknowledgment would file
        with an empty signature and this is what would say so.
        """
        issue = self._submitted_issue()
        auditor = self._user_with_role(AUDIT_ROLE)

        frappe.set_user(auditor)
        ack = frappe.get_doc(
            {
                "doctype": "Custody Acknowledgment",
                "custody_issue": issue.name,
                "confirmation_method": "Signature",
                "signature": _SIGNATURE,
            }
        )
        ack.insert(ignore_permissions=True, ignore_links=True)

        self.assertEqual(
            frappe.db.get_value("Custody Acknowledgment", ack.name, "signature"),
            _SIGNATURE,
            "an ignore_permissions insert blanked the signature — the Web Form path the "
            "portal depends on is now subject to the permlevel, and every worker's "
            "acknowledgment would file empty",
        )

    def test_a_desk_create_without_the_level_one_row_loses_the_signature(self):
        """The other half, and why the desk rows carry WRITE and not only read.

        The three desk roles hold `create` here and can record the fallback signature from
        the Desk, where the permission path IS taken. On a NEW document an unreachable
        level resolves from `frappe.new_doc` — the DEFAULT (base_document.py:1277-1279) — so
        a role without the row has it emptied. Exercised through
        `validate_higher_perm_levels`, the exact call `insert` makes (document.py:306).
        """
        issue = self._submitted_issue()
        desk = self._user_with_role(DESK_ROLE)
        auditor = self._user_with_role(AUDIT_ROLE)

        def surviving_signature(as_user):
            frappe.set_user(as_user)
            fresh = frappe.get_doc(
                {
                    "doctype": "Custody Acknowledgment",
                    "custody_issue": issue.name,
                    "confirmation_method": "Signature",
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

        kept = surviving_signature(desk)
        blanked = surviving_signature(auditor)

        self.assertEqual(
            kept, _SIGNATURE, f"{DESK_ROLE} lost the signature on the Desk create path"
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

    def test_the_signature_is_level_one_with_rows_for_the_desk_roles_only(self):
        """The shipped JSON, checked rather than trusted.

        Rows are counted on the (role, permlevel) PAIR, never the role alone: a level-1 row
        is not a duplicate of that role's level-0 row — `is_perm_applicable` keeps only
        permlevel-0 rows (frappe/permissions.py:284) — so deduplicating on role would strip
        exactly the access this change depends on.
        """
        shipped = json.loads(_ACK_JSON.read_text(encoding="utf-8"))
        rows = shipped["permissions"]

        high = {p["role"] for p in rows if int(p.get("permlevel") or 0) == 1}
        self.assertEqual(
            high,
            DESK_ROLES,
            "the permlevel-1 role set changed. Adding a role hands it every holder's "
            "signature; removing one blanks the fallback signature that role records.",
        )
        self.assertNotIn(AUDIT_ROLE, high, f"{AUDIT_ROLE} must not reach the signature")
        for role in sorted(high):
            row = [p for p in rows if p["role"] == role and int(p.get("permlevel") or 0) == 1]
            self.assertEqual(len(row), 1, f"{role}: expected exactly one permlevel-1 row")
            # Asserted explicitly, never by omission: an absent DocPerm flag ships as 0
            # rather than as its default, so a row written by omission grants nothing.
            self.assertEqual(row[0].get("read"), 1, f"{role}: permlevel-1 read missing")
            self.assertEqual(
                row[0].get("write"), 1, f"{role}: permlevel-1 write missing"
            )

        signature = [f for f in shipped["fields"] if f["fieldname"] == "signature"][0]
        self.assertEqual(signature.get("permlevel"), 1, "signature is not at permlevel 1")
        # The field must stay optional. A `reqd` field raised to level 1 breaks CREATE for
        # any role without a level-1 write row: the value is blanked first
        # (document.py:306) and the mandatory check then fails on the empty field
        # (document.py:417). This one is a fallback, so it is not required — and must not
        # become required without revisiting the row set.
        self.assertFalse(
            signature.get("reqd"),
            "the signature became mandatory at level 1 — create now dies for any role "
            "without a level-1 write row",
        )
        described = (signature.get("description") or "").lower()
        # Checked for MEANING, not for the token `permlevel`: this is the tooltip a holder
        # reads on the portal form, and user-facing text carries no system jargon.
        self.assertIn("sign", described, "the tooltip no longer says what the field is")
        self.assertTrue(
            {"because", "so", "since"} & set(described.split()),
            "the tooltip states the restriction but never says WHY it is restricted",
        )
        # This one is read by a WORKER on the portal, in Arabic, so system jargon is worst
        # of all here. Say WHO keeps the field and WHY, never HOW it is enforced.
        for jargon in ("permlevel", "level 1", "level 0", "docperm"):
            self.assertNotIn(
                jargon, described, f"the tooltip leaks the system term {jargon!r} to a worker"
            )

    def test_the_auditors_level_zero_authority_was_not_collateral_damage(self):
        """The explicit non-change: one field narrowed, not a role's authority."""
        shipped = json.loads(_ACK_JSON.read_text(encoding="utf-8"))
        auditor = [
            p
            for p in shipped["permissions"]
            if p["role"] == AUDIT_ROLE and int(p.get("permlevel") or 0) == 0
        ]
        self.assertEqual(len(auditor), 1, "the auditor's level-0 row was moved or duplicated")
        self.assertEqual(auditor[0].get("read"), 1, "the auditor's read was revoked")
        self.assertEqual(auditor[0].get("export"), 1, "the auditor's export was revoked")
        self.assertEqual(auditor[0].get("report"), 1, "the auditor's report access was revoked")
