# Copyright (c) 2026, AFMCO and contributors
"""`supervisor_signature` moved to permlevel 1.

The field_sensitivity model calls a captured signature an ABSOLUTE level-1 category —
biometric-adjacent, the raw material for forgery, sensitive wherever it appears and whoever
it belongs to. Here it belongs to the supervisor accepting custody of the facility assets
rather than to a resident, which changes who is harmed by a forgery but not whether the mark
is sensitive.

Level-1 rows go to System Manager, Accommodation Manager and Resident Supervisor — the three
roles that hold `create` and `submit` on this handover. Internal Auditor deliberately gets
none; that omission is the change. The auditor's interest in a custody handover is which
assets moved, on what date, verified by whom — all of it level 0 and all of it untouched.

WHY THE ROWS CARRY WRITE
------------------------
Unlike the other custody records in this pass there is no kiosk or portal here: the handover
is filed on the Desk form by those same three roles, which IS the permission path. On a NEW
document an unreachable level resolves from `frappe.new_doc(self.doctype)` — the field
DEFAULT, not the stored row (frappe/model/base_document.py:1277-1279) — so a role filing the
handover without a level-1 WRITE row would have the signature silently emptied on insert,
with no exception and `all_assets_verified` still ticked beside it. Read-only rows would have
turned a privacy fix into a data-loss bug.

The field is deliberately NOT `reqd`. A required field raised to level 1 breaks create
outright for any role lacking the write row: the value is blanked at document.py:306 and the
mandatory check then fails on the empty field at :417. This one is optional, so the failure
mode is silent loss rather than a hard stop — worse to notice, which is why the create-path
test below exists.

WHAT THIS DOES NOT PROTECT
--------------------------
`permlevel` is not enforced under `frappe.get_all`, which returns early on
`ignore_permissions` (frappe/model/db_query.py:683-684) — how every Script Report here reads.
Checked in the same pass: NO report in the app reads this DocType at all, and no report tree
anywhere selects a signature fieldname. So nothing bypasses the level today.

Run under bench:
  bench --site <site> run-tests --module apex.habitat.doctype.facility_asset_custody_assignment.test_facility_asset_custody_assignment_signature_permlevel
"""

from __future__ import annotations

import json
from pathlib import Path

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate

_FACA_JSON = Path(__file__).resolve().parent / "facility_asset_custody_assignment.json"

# Both roles sit in habitat.permissions.HOUSING_UNSCOPED_ROLES, so
# `building_scoped_has_permission` defers for both (permissions.py:451-452). A
# building-scoped role would be blocked by the SCOPE before the level was consulted, and the
# pair below would prove nothing about levels.
DESK_ROLE = "Accommodation Manager"
AUDIT_ROLE = "Internal Auditor"
DESK_ROLES = {"System Manager", "Accommodation Manager", "Resident Supervisor"}

_SIGNATURE = "data:image/png;base64,iVBORw0KGgo="

test_ignore = ["Building", "Employee", "Role", "User"]


class TestFacilityAssetCustodySignaturePermlevel(FrappeTestCase):
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

    def _handover(self, **extra):
        return frappe.get_doc(
            {
                "doctype": "Facility Asset Custody Assignment",
                "naming_series": "FAC-CUST-.YYYY.-.#####",
                "supervisor": "Administrator",
                "building": "QA-BLDG",
                "handover_date": "2026-06-01",
                "all_assets_verified": 1,
                **extra,
            }
        )

    def _signed_handover(self):
        doc = self._handover(supervisor_signature=_SIGNATURE)
        # Administrator + ignore_permissions: the level gate returns early for both
        # (document.py:785,789), so the fixture holds a real signature whatever the rows
        # say. Every assertion below is about reading it back as someone else.
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.addCleanup(
            frappe.delete_doc,
            "Facility Asset Custody Assignment",
            doc.name,
            force=True,
            ignore_permissions=True,
        )
        return doc

    def test_the_auditor_cannot_read_the_signature_and_the_desk_role_can(self):
        """THE PAIR. Both verdicts in one method so they cannot drift, compared as VERDICTS
        ALONE — comparing (role, value, verdict) tuples would pass on the differing role
        literals even with the permlevel removed entirely.

        Read through `frappe.client.get`, where the strip lives (frappe/client.py:110); an
        in-process `frappe.get_doc` does not strip.
        """
        doc = self._signed_handover()
        auditor = self._user_with_role(AUDIT_ROLE)
        desk = self._user_with_role(DESK_ROLE)

        frappe.set_user(desk)
        self.assertIn(
            1,
            frappe.get_doc(
                "Facility Asset Custody Assignment", doc.name
            ).get_permlevel_access("read"),
            f"{DESK_ROLE} lost its permlevel-1 read row",
        )
        frappe.set_user(auditor)
        self.assertNotIn(
            1,
            frappe.get_doc(
                "Facility Asset Custody Assignment", doc.name
            ).get_permlevel_access("read"),
            f"{AUDIT_ROLE} reaches permlevel 1",
        )

        # Verdict A — CONCEALED. assertFalse, not assertIsNone: the strip deletes the
        # attribute (document.py:771) but `as_dict` rebuilds every column and coerces it by
        # fieldtype (base_document.py:402), so the returned value depends on the fieldtype
        # rather than on whether the strip worked.
        frappe.set_user(auditor)
        audited = frappe.client.get("Facility Asset Custody Assignment", doc.name)
        self.assertFalse(
            audited.get("supervisor_signature"),
            f"{AUDIT_ROLE} can still read the supervisor's signature",
        )
        # Presence first: `getdate(None)` returns TODAY (frappe/utils/data.py:91-92), so a
        # stripped date would still compare as a real one and the clause below would go
        # vacuous the day this fixture is reseeded with `today()`.
        self.assertTrue(
            audited.get("handover_date"),
            "the strip removed a level-0 date — it is supposed to be surgical",
        )
        # Both sides through `getdate`: the round-tripped copy is a `datetime.date` while the
        # fixture still holds the string it was seeded with, so a raw comparison fails on
        # TYPE even when the value survived intact.
        self.assertEqual(
            getdate(audited.get("handover_date")),
            getdate(doc.handover_date),
            "level-0 handover facts must survive the strip — the auditor still audits",
        )

        # Verdict B — VISIBLE.
        frappe.set_user(desk)
        at_desk = frappe.client.get("Facility Asset Custody Assignment", doc.name)
        self.assertEqual(
            at_desk.get("supervisor_signature"),
            _SIGNATURE,
            f"{DESK_ROLE} lost the sign-off it files and has to produce on dispute",
        )

        audit_verdict = "visible" if audited.get("supervisor_signature") else "concealed"
        desk_verdict = "visible" if at_desk.get("supervisor_signature") else "concealed"
        self.assertNotEqual(
            audit_verdict,
            desk_verdict,
            f"both roles produced the same verdict ({audit_verdict}) — the pair collapsed: "
            "either the permlevel stopped being enforced for anyone, or it is now enforced "
            f"against {DESK_ROLE} too",
        )

    def test_the_desk_create_path_keeps_the_signature(self):
        """The regression this move could plausibly have caused, and why the rows carry
        WRITE. On a NEW document an unreachable level resolves from `frappe.new_doc` — the
        DEFAULT, not the stored row (base_document.py:1277-1279). Exercised through
        `validate_higher_perm_levels`, the exact call `insert` makes (document.py:306), so
        the outcome is about the permlevel and not about unrelated link permissions.
        """
        desk = self._user_with_role(DESK_ROLE)
        auditor = self._user_with_role(AUDIT_ROLE)

        def surviving_signature(as_user):
            frappe.set_user(as_user)
            fresh = self._handover(supervisor_signature=_SIGNATURE)
            # `insert` sets this at document.py:295, eleven lines before it calls
            # validate_higher_perm_levels at :306, and `is_new()` reads exactly that flag
            # (base_document.py:465). Setting it here is what makes this the CREATE path:
            # without it the reset would resolve from `get_latest()` — a stored row that
            # does not exist yet — and the test would silently be about updates instead.
            fresh.set("__islocal", True)
            self.assertTrue(fresh.is_new(), "precondition: the create path needs a NEW doc")
            fresh.validate_higher_perm_levels()
            return fresh.supervisor_signature

        kept = surviving_signature(desk)
        blanked = surviving_signature(auditor)

        self.assertEqual(
            kept,
            _SIGNATURE,
            f"{DESK_ROLE} lost the signature on the CREATE path — handovers would file "
            "marked verified with no sign-off behind them",
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
        shipped = json.loads(_FACA_JSON.read_text(encoding="utf-8"))
        rows = shipped["permissions"]

        high = {p["role"] for p in rows if int(p.get("permlevel") or 0) == 1}
        self.assertEqual(
            high,
            DESK_ROLES,
            "the permlevel-1 role set changed. Adding a role hands it every supervisor's "
            "signature; removing one blanks the sign-off that role files.",
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
                f"{role}: permlevel-1 write missing — the Desk would blank the sign-off on "
                "every handover it files",
            )

        signature = [f for f in shipped["fields"] if f["fieldname"] == "supervisor_signature"][0]
        self.assertEqual(
            signature.get("permlevel"), 1, "supervisor_signature is not at permlevel 1"
        )
        self.assertFalse(
            signature.get("reqd"),
            "the sign-off became mandatory at level 1 — create now dies outright for any "
            "role without a level-1 write row",
        )
        described = (signature.get("description") or "").lower()
        # Checked for MEANING, not for the token `permlevel`: this is the tooltip a
        # supervisor reads on the form, and user-facing text carries no system jargon.
        self.assertIn("sign", described, "the tooltip no longer says what the field is")
        self.assertTrue(
            {"because", "so", "since"} & set(described.split()),
            "the tooltip states the restriction but never says WHY it is restricted",
        )
        # Say WHO keeps the field and WHY, never HOW it is enforced: this text reaches a
        # supervisor and the translators, and "level 1" means nothing to either.
        for jargon in ("permlevel", "level 1", "level 0", "docperm"):
            self.assertNotIn(
                jargon, described, f"the tooltip leaks the system term {jargon!r} to a supervisor"
            )

    def test_the_auditors_level_zero_authority_was_not_collateral_damage(self):
        """The explicit non-change: one field narrowed, not a role's authority."""
        shipped = json.loads(_FACA_JSON.read_text(encoding="utf-8"))
        auditor = [
            p
            for p in shipped["permissions"]
            if p["role"] == AUDIT_ROLE and int(p.get("permlevel") or 0) == 0
        ]
        self.assertEqual(len(auditor), 1, "the auditor's level-0 row was moved or duplicated")
        self.assertEqual(auditor[0].get("read"), 1, "the auditor's read was revoked")
        self.assertEqual(auditor[0].get("export"), 1, "the auditor's export was revoked")
        self.assertEqual(auditor[0].get("report"), 1, "the auditor's report access was revoked")
