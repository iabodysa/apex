# Copyright (c) 2026, AFMCO and contributors
"""`terms_signature` moved to permlevel 1, and what that actually changed.

The field_sensitivity model calls a captured signature an ABSOLUTE level-1 category: it is
biometric-adjacent and the raw material for forgery, so it is sensitive wherever it appears,
person master or not. This DocType was the urgent one. A-216 granted Internal Auditor a
level-0 read on Housing Assignment for estate-wide audit, and Housing Assignment shipped no
level-1 section, so that grant handed the auditor every resident's captured mark along with
the placement facts it was actually for. Raising the field is what separates the two.

WHICH ROLES GOT A LEVEL-1 ROW, AND WHY IT IS NOT "EVERYONE WHO CAN WRITE"
-------------------------------------------------------------------------
System Manager, Accommodation Manager and Resident Supervisor — exactly the three roles on
the Arrivals Desk page (arrivals_desk.json), which is the only surface that captures this
signature. Internal Auditor deliberately gets NO level-1 row; that omission IS the fix.

The row set is not cosmetic, and it is not the usual permlevel reasoning either. The desk
captures the signature on the CREATE path: `quick_check_in` builds the whole assignment in
one `frappe.get_doc({... "terms_signature": ...})` and calls
`doc.insert(ignore_permissions=False)` (habitat/api/front_desk.py:660,664). On a NEW document
`reset_values_if_no_permlevel_access` takes its reference from `frappe.new_doc(self.doctype)`
rather than the stored row (frappe/model/base_document.py:1277-1279), so a field the caller
holds no level-1 row for is set to the field DEFAULT — empty. Not refused, not raised:
silently emptied, and `terms_accepted_on` beside it (level 0) would still be stamped, leaving
a record that claims the terms were signed and holds no signature. Give the desk roles the
row or the feature quietly stops working; `test_the_create_path_keeps_the_signature_for_a_desk_role`
is the guard on that.

WHAT THIS DOES NOT PROTECT
--------------------------
`permlevel` is a document- and desk-layer control only. It is NOT enforced under
`frappe.get_all`, which returns early on `ignore_permissions` (frappe/model/db_query.py:683-684),
and every Script Report in this app reads that way. Checked in the same pass: no report over
Housing Assignment selects `terms_signature` — the reports that read this DocType
(active_resident_register, accommodation_occupancy_summary, idle_resident_detection,
checkout_pending_clearance) select placement and occupancy columns only, and a repo-wide
search for a signature fieldname across every report tree returns nothing. So the level is
the whole control here today, and a future report that adds the column would bypass it
without tripping any of this.

Run under bench:
  bench --site <site> run-tests --module apex.habitat.doctype.housing_assignment.test_housing_assignment_signature_permlevel
"""

from __future__ import annotations

import json
from pathlib import Path

import frappe
from frappe.tests.utils import FrappeTestCase

_ASSIGNMENT_JSON = Path(__file__).resolve().parent / "housing_assignment.json"

DESK_ROLE = "Accommodation Manager"
AUDIT_ROLE = "Internal Auditor"
DESK_ROLES = {"System Manager", "Accommodation Manager", "Resident Supervisor"}

_SIGNATURE = "data:image/png;base64,iVBORw0KGgo="


class TestHousingAssignmentSignaturePermlevel(FrappeTestCase):
    """Site-bound. Fixtures are minted per METHOD: rollback covers rows only, so a document
    shared across methods would carry the previous method's mutations."""

    def setUp(self):
        # frappe.session.user is process state — no rollback restores it. Register the
        # cleanup BEFORE anything changes it.
        self.addCleanup(frappe.set_user, "Administrator")
        frappe.set_user("Administrator")

    def _h(self):
        # 12 wide on purpose: short random fixture names collide across a long suite run,
        # and the collision surfaces as an unrelated DuplicateEntryError.
        return frappe.generate_hash(length=12).upper()

    def _user_with_role(self, role):
        return frappe.get_doc(
            {
                "doctype": "User",
                "email": f"a308_{frappe.generate_hash(length=12)}@example.com",
                "first_name": role.split()[0],
                "roles": [{"role": role}],
            }
        ).insert(ignore_permissions=True).name

    def _fixtures(self):
        """Same shape as test_housing_assignment._fixtures — a real, internally consistent
        building/room/bed/employee/project set, so the controller's validate() runs in full."""
        company = frappe.db.get_value("Company", {}) or frappe.get_doc(
            {
                "doctype": "Company",
                "company_name": "Test Co",
                "default_currency": "SAR",
                "country": "Saudi Arabia",
            }
        ).insert(ignore_permissions=True).name
        cc = frappe.db.get_value("Cost Center", {"is_group": 0, "company": company}) or frappe.db.get_value(
            "Cost Center", {"is_group": 0}
        )
        site = frappe.get_doc(
            {"doctype": "Site", "site_name": self._h() + self._h()}
        ).insert(ignore_permissions=True).name
        building = frappe.get_doc(
            {
                "doctype": "Building",
                "building_name": "B " + self._h(),
                "site": site,
                "total_capacity": 4,
                "company": company,
                "default_cost_center": cc,
            }
        ).insert(ignore_permissions=True).name
        room = frappe.get_doc(
            {
                "doctype": "Room",
                "naming_series": "ROOM-.####",
                "building": building,
                "room_number": "R" + self._h(),
                "bed_capacity": 4,
                "readiness_status": "Ready",
            }
        ).insert(ignore_permissions=True).name
        bed = frappe.get_doc(
            {
                "doctype": "Bed",
                "naming_series": "BED-.####",
                "room": room,
                "building": building,
                "bed_code": "B" + self._h(),
                "status": "Available",
            }
        ).insert(ignore_permissions=True).name
        project = frappe.get_doc(
            {"doctype": "Project", "project_name": "P " + self._h()}
        ).insert(ignore_permissions=True).name
        emp = frappe.get_doc(
            {
                "doctype": "Employee",
                "first_name": "E " + self._h(),
                "company": company,
                "gender": "Male",
                "date_of_birth": "1990-01-01",
                "date_of_joining": "2020-01-01",
            }
        ).insert(ignore_permissions=True).name
        return frappe._dict(
            company=company, cc=cc, building=building, room=room, bed=bed, project=project, emp=emp
        )

    def _signed_assignment(self, fx):
        doc = frappe.get_doc(
            {
                "doctype": "Housing Assignment",
                "naming_series": "ACC-ASGN-.YYYY.-.####",
                "employee": fx.emp,
                "project": fx.project,
                "building": fx.building,
                "room": fx.room,
                "bed": fx.bed,
                "cost_center": fx.cc,
                "check_in_date": "2026-06-01",
                "assignment_type": "New Assignment",
                "terms_signature": _SIGNATURE,
                "terms_accepted_on": frappe.utils.now(),
            }
        )
        # Administrator + ignore_permissions: the permlevel gate returns early for both
        # (frappe/model/document.py:785,789), so the fixture is guaranteed to hold a real
        # signature no matter what the level rows say. Every assertion below is about
        # READING it back as someone else.
        return doc.insert(ignore_permissions=True)

    def test_the_auditor_cannot_read_the_signature_and_the_desk_role_can(self):
        """THE PAIR. Both verdicts in one method so they cannot drift, and compared as
        VERDICTS ALONE at the end. An earlier shape in this repo compared
        (role, value, verdict) tuples, which can never be equal — the role names are
        different literals — so it passed even with the permlevel removed entirely.

        Asserted through `frappe.client.get`, because that is where the read strip lives
        (frappe/client.py:110). An in-process `frappe.get_doc` does NOT strip, so asserting
        on the raw document would prove nothing about what the auditor actually receives.
        """
        fx = self._fixtures()
        doc = self._signed_assignment(fx)
        auditor = self._user_with_role(AUDIT_ROLE)
        desk = self._user_with_role(DESK_ROLE)

        # The access itself, before either read: level 1 must be reachable for one and not
        # the other, or the two outcomes below say nothing about permlevels.
        frappe.set_user(desk)
        self.assertIn(
            1,
            frappe.get_doc("Housing Assignment", doc.name).get_permlevel_access("read"),
            f"{DESK_ROLE} lost its permlevel-1 read row",
        )
        frappe.set_user(auditor)
        self.assertNotIn(
            1,
            frappe.get_doc("Housing Assignment", doc.name).get_permlevel_access("read"),
            f"{AUDIT_ROLE} reaches permlevel 1 — the A-216 exposure is back",
        )

        # Verdict A — the auditor's copy is CONCEALED.
        frappe.set_user(auditor)
        audited = frappe.client.get("Housing Assignment", doc.name)
        # assertFalse, not assertIsNone: the strip deletes the attribute
        # (frappe/model/document.py:771) but `as_dict` rebuilds every column and coerces it
        # by fieldtype (frappe/model/base_document.py:402), so what comes back depends on
        # the fieldtype rather than on whether the strip worked.
        self.assertFalse(
            audited.get("terms_signature"),
            f"{AUDIT_ROLE} can still read the resident's captured signature",
        )
        self.assertEqual(
            audited.get("bed"),
            doc.bed,
            "level-0 placement facts must survive the strip — the auditor still audits",
        )

        # Verdict B — the desk role's copy is VISIBLE.
        frappe.set_user(desk)
        at_desk = frappe.client.get("Housing Assignment", doc.name)
        self.assertEqual(
            at_desk.get("terms_signature"),
            _SIGNATURE,
            f"{DESK_ROLE} lost the signature it captures and has to show back",
        )

        audit_verdict = "visible" if audited.get("terms_signature") else "concealed"
        desk_verdict = "visible" if at_desk.get("terms_signature") else "concealed"
        self.assertNotEqual(
            audit_verdict,
            desk_verdict,
            f"both roles produced the same verdict ({audit_verdict}) — the pair collapsed: "
            "either the permlevel stopped being enforced for anyone, or it is now enforced "
            f"against {DESK_ROLE} too",
        )

    def test_the_create_path_keeps_the_signature_for_a_desk_role(self):
        """The regression this move could plausibly have caused, and the reason the three
        desk roles hold level-1 WRITE and not merely read.

        `quick_check_in` sets `terms_signature` on a brand-new document and inserts it with
        `ignore_permissions=False` (front_desk.py:660,664). On a new document the reference
        for an unreachable level is `frappe.new_doc` — the DEFAULT, not the stored row
        (base_document.py:1277-1279) — so a caller without the row has the signature
        silently emptied on insert. This exercises `validate_higher_perm_levels` directly,
        which is the exact call `insert` makes (document.py:306), so the outcome is about
        the permlevel and not about the twenty unrelated link permissions an insert needs.
        """
        fx = self._fixtures()
        desk = self._user_with_role(DESK_ROLE)
        auditor = self._user_with_role(AUDIT_ROLE)

        def surviving_signature(as_user):
            frappe.set_user(as_user)
            fresh = frappe.get_doc(
                {
                    "doctype": "Housing Assignment",
                    "naming_series": "ACC-ASGN-.YYYY.-.####",
                    "employee": fx.emp,
                    "project": fx.project,
                    "building": fx.building,
                    "room": fx.room,
                    "bed": fx.bed,
                    "cost_center": fx.cc,
                    "check_in_date": "2026-06-01",
                    "assignment_type": "New Assignment",
                    "terms_signature": _SIGNATURE,
                }
            )
            self.assertTrue(fresh.is_new(), "precondition: the create path needs a NEW doc")
            fresh.validate_higher_perm_levels()
            return fresh.terms_signature

        kept = surviving_signature(desk)
        blanked = surviving_signature(auditor)

        self.assertEqual(
            kept,
            _SIGNATURE,
            f"{DESK_ROLE} lost the signature on the CREATE path — the desk would file "
            "assignments stamped 'terms accepted' with no signature behind them",
        )
        self.assertFalse(
            blanked,
            "a role with no permlevel-1 row kept a signature it cannot reach on create",
        )
        kept_verdict = "kept" if kept else "blanked"
        blanked_verdict = "kept" if blanked else "blanked"
        self.assertNotEqual(
            kept_verdict,
            blanked_verdict,
            f"both roles produced the same verdict ({kept_verdict}) — this pair no longer "
            "distinguishes a role that holds the level-1 write row from one that does not",
        )

    def test_the_signature_is_level_one_with_rows_for_the_desk_roles_only(self):
        """The shipped JSON, checked rather than trusted.

        A permlevel-1 row is NOT a duplicate of the same role's permlevel-0 row:
        `is_perm_applicable` keeps only permlevel-0 rows (frappe/permissions.py:284), so the
        two answer different questions and deduplicating on role alone would strip exactly
        the access this change depends on. Rows are therefore counted on the
        (role, permlevel) PAIR.
        """
        shipped = json.loads(_ASSIGNMENT_JSON.read_text(encoding="utf-8"))
        rows = shipped["permissions"]

        high = {p["role"] for p in rows if int(p.get("permlevel") or 0) == 1}
        self.assertEqual(
            high,
            DESK_ROLES,
            "the permlevel-1 role set changed. Adding a role here hands it every resident's "
            "captured signature; removing one silently blanks the signature that role "
            "captures at the desk.",
        )
        self.assertNotIn(
            AUDIT_ROLE,
            high,
            f"{AUDIT_ROLE} holds a permlevel-1 row — that is the exact A-216 exposure this "
            "change exists to close",
        )
        for role in sorted(high):
            row = [p for p in rows if p["role"] == role and int(p.get("permlevel") or 0) == 1]
            self.assertEqual(len(row), 1, f"{role}: expected exactly one permlevel-1 row")
            # Checked explicitly, never by omission: an absent DocPerm flag ships as 0
            # rather than as its default, so a row written by omission grants nothing.
            self.assertEqual(row[0].get("read"), 1, f"{role}: permlevel-1 read missing")
            self.assertEqual(
                row[0].get("write"),
                1,
                f"{role}: permlevel-1 write missing — the desk would blank the signature "
                "it captures, on every check-in",
            )

        signature = [f for f in shipped["fields"] if f["fieldname"] == "terms_signature"][0]
        self.assertEqual(signature.get("permlevel"), 1, "terms_signature is not at permlevel 1")
        described = (signature.get("description") or "").lower()
        # The description is checked for MEANING, not for the token `permlevel`: it is the
        # tooltip a front-desk clerk reads, and user-facing text carries no system jargon.
        self.assertIn("signature", described, "the tooltip no longer says what the field is")
        self.assertTrue(
            {"because", "so", "since"} & set(described.split()),
            "the tooltip states the restriction but never says WHY it is restricted",
        )

    def test_the_auditors_level_zero_authority_was_not_collateral_damage(self):
        """The explicit non-change. A-216 gave Internal Auditor estate-wide read on this
        record for a reason; this change narrows one field, not that grant."""
        shipped = json.loads(_ASSIGNMENT_JSON.read_text(encoding="utf-8"))
        auditor = [
            p
            for p in shipped["permissions"]
            if p["role"] == AUDIT_ROLE and int(p.get("permlevel") or 0) == 0
        ]
        self.assertEqual(len(auditor), 1, "the auditor's level-0 row was moved or duplicated")
        self.assertEqual(auditor[0].get("read"), 1, "the auditor's estate-wide read was revoked")
        self.assertEqual(auditor[0].get("report"), 1, "the auditor's report access was revoked")
