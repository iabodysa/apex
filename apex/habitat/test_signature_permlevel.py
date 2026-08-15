# Copyright (c) 2026, AFMCO and contributors
"""Every captured signature in Habitat sits at permlevel 1, and the same four clauses hold
for all of them.

SUBJECT: the field-sensitivity policy itself, not one DocType. The policy calls a captured
signature an ABSOLUTE level-1 category — biometric-adjacent, the raw material for forgery,
sensitive wherever it appears and whoever it belongs to. Four Habitat records capture one:

  Custody Issue                      `signature`             the recipient's, at the kiosk
  Custody Acknowledgment             `signature`             the holder's own receipt
  Facility Asset Custody Assignment  `supervisor_signature`  the supervisor accepting assets
  Housing Assignment                 `terms_signature`       the resident's, at the desk

This module replaces four near-identical suites (one per DocType, ~1,290 lines, 17 methods)
that differed only in the DocType name, the fieldname, the level-0 witness field and the
fixture. They asserted the SAME four clauses in the same order with the same comments, so a
change to the policy had to be made in four places and a DocType added to the policy was
covered by nobody. The subjects are a TABLE here and every clause runs against all four under
`subTest`, so each subject is still graded and reported independently — adding the fifth
signature is one row.

Each distinct value the four files carried is kept, and where they disagreed the STRICTER of
the two is now applied to all four:

* `reqd` was asserted false only by the Custody Acknowledgment and Facility Asset suites.
  The hazard is general — a `reqd` field raised to level 1 breaks CREATE outright for any
  role without a level-1 write row: the value is blanked at document.py:306 and the mandatory
  check then fails on the empty field at :417 — so it is now asserted for all four.
* the auditor's `export` was asserted by three of the four. Housing Assignment genuinely
  ships no `export` on that row, so it stays a per-subject value rather than being levelled
  up into a false assertion.
* the level-0 witness differs in KIND. Two subjects witness with a Date, which needs the
  `getdate` handling below; two witness with a Link, which does not. Both kinds are kept.

WHY THE ROWS CARRY WRITE AND NOT ONLY READ
------------------------------------------
Every one of these signatures is set on the CREATE path — `issue_custody`
(habitat/api/custody_kiosk.py:350,352), `quick_check_in` (habitat/api/front_desk.py:660,664),
or the Desk form — and on a NEW document `reset_values_if_no_permlevel_access` takes its
reference from `frappe.new_doc(self.doctype)` rather than from the stored row
(frappe/model/base_document.py:1277-1279). A role without a level-1 WRITE row therefore has
the signature silently EMPTIED on insert: no exception, and the `*_accepted_on` /
`all_assets_verified` field beside it still stamped. Read-only rows would have turned a
privacy fix into a data-loss bug, which is what
`test_the_create_path_keeps_the_signature_only_for_a_role_holding_the_write_row` is for.

WHAT THIS DOES NOT PROTECT
--------------------------
`permlevel` is not enforced under `frappe.get_all`, which returns early on
`ignore_permissions` (frappe/model/db_query.py:683-684) — how every Script Report here reads.
Checked across all four subjects: no report tree in the app selects any signature fieldname.
So the level is the whole control today, and a future report adding the column would bypass
it silently.

Run under bench:
  bench --site <site> run-tests --module apex.habitat.test_signature_permlevel
"""

from __future__ import annotations

import json
from pathlib import Path

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate

import apex
from apex.tests.factories import (
    make_bed,
    make_building,
    make_company,
    make_employee,
    make_project,
    make_room,
    make_submitted_custody_issue,
)

_HABITAT = Path(apex.__file__).resolve().parent / "habitat" / "doctype"

# Both roles sit in habitat.permissions.HOUSING_UNSCOPED_ROLES, so
# `building_scoped_has_permission` defers for both (permissions.py:451-452). A
# building-scoped role would be blocked by the SCOPE before the level was ever consulted,
# and the pairs below would prove nothing about levels.
DESK_ROLE = "Accommodation Manager"
AUDIT_ROLE = "Internal Auditor"
DESK_ROLES = {"System Manager", "Accommodation Manager", "Resident Supervisor"}

_SIGNATURE = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUg=="

test_ignore = ["Building", "Custody Article", "Custody Issue", "Employee", "Role", "User"]


def _h():
    # 12 wide on purpose: short random fixture names collide across a long suite run, and
    # the collision surfaces as an unrelated DuplicateEntryError.
    return frappe.generate_hash(length=12).upper()


class Subject:
    """One record that captures a signature, and everything the clauses need to grade it.

    ``context`` builds whatever the payload depends on and is called once per method per
    subject; ``payload`` is called repeatedly and must return a FRESH dict each time, because
    the create-path clause builds two documents from it as two different users.
    """

    def __init__(
        self,
        doctype,
        folder,
        signature_field,
        witness_field,
        witness_is_date,
        auditor_export,
        context,
        payload,
        insert_kwargs,
    ):
        self.doctype = doctype
        self.json_path = _HABITAT / folder / f"{folder}.json"
        self.signature_field = signature_field
        self.witness_field = witness_field
        self.witness_is_date = witness_is_date
        self.auditor_export = auditor_export
        self.context = context
        self.payload = payload
        self.insert_kwargs = insert_kwargs

    def __repr__(self):
        return self.doctype

    def shipped(self):
        return json.loads(self.json_path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- fixture builders


def _custody_issue_context(test):
    return None


def _custody_issue_payload(test, _ctx):
    return {
        "doctype": "Custody Issue",
        "naming_series": "CUST-ISS-.YYYY.-.####",
        "issue_date": "2026-06-01",
        "building": "QA-BLDG",
        "items": [{"doctype": "Custody Issue Item", "article": "QA-ART", "qty": 1}],
        "signature": _SIGNATURE,
    }


def _acknowledgment_context(test):
    # The acknowledgment hangs off a SUBMITTED issue; the shared factory owns that shape so
    # the acknowledgment's behaviour suite and this one cannot drift apart.
    return make_submitted_custody_issue().name


def _acknowledgment_payload(test, issue):
    return {
        "doctype": "Custody Acknowledgment",
        "custody_issue": issue,
        "confirmation_method": "Signature",
        "signature": _SIGNATURE,
    }


def _facility_asset_context(test):
    return None


def _facility_asset_payload(test, _ctx):
    return {
        "doctype": "Facility Asset Custody Assignment",
        "naming_series": "FAC-CUST-.YYYY.-.#####",
        "supervisor": "Administrator",
        "building": "QA-BLDG",
        "handover_date": "2026-06-01",
        "all_assets_verified": 1,
        "supervisor_signature": _SIGNATURE,
    }


def _housing_assignment_context(test):
    """A real, internally consistent building/room/bed/employee/project set, so the
    controller's validate() runs in full rather than on a skeleton.

    Built through the shared factory rather than by hand — the four suites this module
    replaces each carried their own copy of this chain. Every name is hashed because the
    factory helpers are get-or-CREATE on the name: a fixed name would hand the second
    method back the SAME bed, which the first method's assignment has already occupied.
    """
    company = frappe.db.get_value("Company", {}) or make_company().name
    cc = frappe.db.get_value(
        "Cost Center", {"is_group": 0, "company": company}
    ) or frappe.db.get_value("Cost Center", {"is_group": 0})
    site = frappe.get_doc(
        {"doctype": "Site", "site_name": _h() + _h()}
    ).insert(ignore_permissions=True).name
    building = make_building(
        "B " + _h(), company=company, site=site, total_capacity=4, default_cost_center=cc
    ).name
    room = make_room(
        building, "R" + _h(), bed_capacity=4, readiness_status="Ready"
    ).name
    bed = make_bed(room, "B" + _h(), building=building).name
    emp = make_employee("E " + _h(), company=company).name
    return frappe._dict(
        company=company,
        cc=cc,
        building=building,
        room=room,
        bed=bed,
        project=make_project("P " + _h()),
        emp=emp,
    )


def _housing_assignment_payload(test, fx):
    return {
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
        # Level 0, and the whole point: without the level-1 write row this stays stamped
        # while the signature beside it is emptied.
        "terms_accepted_on": frappe.utils.now(),
    }


SUBJECTS = (
    Subject(
        "Custody Issue",
        "custody_issue",
        signature_field="signature",
        witness_field="issue_date",
        witness_is_date=True,
        auditor_export=True,
        context=_custody_issue_context,
        payload=_custody_issue_payload,
        insert_kwargs={"ignore_permissions": True, "ignore_links": True},
    ),
    Subject(
        "Custody Acknowledgment",
        "custody_acknowledgment",
        signature_field="signature",
        witness_field="custody_issue",
        witness_is_date=False,
        auditor_export=True,
        context=_acknowledgment_context,
        payload=_acknowledgment_payload,
        insert_kwargs={"ignore_permissions": True, "ignore_links": True},
    ),
    Subject(
        "Facility Asset Custody Assignment",
        "facility_asset_custody_assignment",
        signature_field="supervisor_signature",
        witness_field="handover_date",
        witness_is_date=True,
        auditor_export=True,
        context=_facility_asset_context,
        payload=_facility_asset_payload,
        insert_kwargs={"ignore_permissions": True, "ignore_links": True},
    ),
    Subject(
        "Housing Assignment",
        "housing_assignment",
        signature_field="terms_signature",
        witness_field="bed",
        witness_is_date=False,
        # Housing Assignment genuinely ships no `export` on the auditor's level-0 row. Kept
        # as a per-subject value rather than levelled up into an assertion that would fail.
        auditor_export=False,
        context=_housing_assignment_context,
        payload=_housing_assignment_payload,
        insert_kwargs={"ignore_permissions": True},
    ),
)


class TestTheSignaturePermlevelPolicy(FrappeTestCase):
    """Site-bound. Fixtures per SUBJECT per METHOD: rollback is rows-only and fires once per
    CLASS (frappe/tests/utils.py:46), so a document shared across methods would carry the
    previous method's mutations."""

    def setUp(self):
        # frappe.session.user is process state — no rollback restores it. Register the
        # cleanup BEFORE anything changes it.
        self.addCleanup(frappe.set_user, "Administrator")
        frappe.set_user("Administrator")

    def _user_with_role(self, role):
        return frappe.get_doc(
            {
                "doctype": "User",
                "email": f"sigperm_{frappe.generate_hash(length=12)}@example.com",
                "first_name": role.split()[0],
                "roles": [{"role": role}],
            }
        ).insert(ignore_permissions=True).name

    def _signed(self, subject, ctx):
        """A stored record that really holds the signature.

        Administrator + ignore_permissions: the level gate returns early for both
        (document.py:785,789), so the fixture holds a real signature whatever the rows say.
        Every read assertion is about getting it back as someone else.
        """
        frappe.set_user("Administrator")
        doc = frappe.get_doc(subject.payload(self, ctx))
        doc.insert(**subject.insert_kwargs)
        self.addCleanup(
            frappe.delete_doc, subject.doctype, doc.name, force=True, ignore_permissions=True
        )
        return doc

    def _same(self, subject, a, b):
        """Compare a level-0 witness across the round trip.

        Dates go through `getdate` on BOTH sides: the round-tripped copy is a
        `datetime.date` while the fixture still holds the string it was seeded with, so a raw
        comparison fails on TYPE even when the value survived intact.
        """
        if subject.witness_is_date:
            return getdate(a) == getdate(b)
        return a == b

    # ---- clause 1: the pair — concealed from the auditor, visible to the desk ----

    def test_the_auditor_cannot_read_the_signature_and_the_desk_role_can(self):
        """THE PAIR, per subject. Both verdicts are produced in one subTest so they cannot
        drift, and compared as VERDICTS ALONE — comparing (role, value, verdict) tuples would
        pass on the differing role literals even with the permlevel removed entirely.

        Read through `frappe.client.get`, where the strip lives (frappe/client.py:110); an
        in-process `frappe.get_doc` does NOT strip, so asserting on the raw document would
        prove nothing about what the auditor actually receives.
        """
        for subject in SUBJECTS:
            with self.subTest(subject=subject.doctype):
                frappe.set_user("Administrator")
                ctx = subject.context(self)
                doc = self._signed(subject, ctx)
                auditor = self._user_with_role(AUDIT_ROLE)
                desk = self._user_with_role(DESK_ROLE)
                field = subject.signature_field

                # The access itself, before either read — otherwise the outcomes below say
                # nothing about permlevels.
                frappe.set_user(desk)
                self.assertIn(
                    1,
                    frappe.get_doc(subject.doctype, doc.name).get_permlevel_access("read"),
                    f"{subject.doctype}: {DESK_ROLE} lost its permlevel-1 read row",
                )
                frappe.set_user(auditor)
                self.assertNotIn(
                    1,
                    frappe.get_doc(subject.doctype, doc.name).get_permlevel_access("read"),
                    f"{subject.doctype}: {AUDIT_ROLE} reaches permlevel 1",
                )

                # Verdict A — CONCEALED. assertFalse, not assertIsNone: the strip deletes
                # the attribute (document.py:771) but `as_dict` rebuilds every column and
                # coerces it by fieldtype (base_document.py:402), so the returned value
                # depends on the fieldtype rather than on whether the strip worked.
                frappe.set_user(auditor)
                audited = frappe.client.get(subject.doctype, doc.name)
                self.assertFalse(
                    audited.get(field),
                    f"{subject.doctype}: {AUDIT_ROLE} can still read the captured signature",
                )
                # Presence first: `getdate(None)` returns TODAY (frappe/utils/data.py:91-92),
                # so a stripped date would still compare as a real one and the clause below
                # would go vacuous the day a fixture is reseeded with `today()`.
                self.assertTrue(
                    audited.get(subject.witness_field),
                    f"{subject.doctype}: the strip removed the level-0 witness "
                    f"{subject.witness_field} — it is supposed to be surgical",
                )
                self.assertTrue(
                    self._same(
                        subject,
                        audited.get(subject.witness_field),
                        doc.get(subject.witness_field),
                    ),
                    f"{subject.doctype}: level-0 facts must survive the strip — the auditor "
                    "still audits",
                )

                # Verdict B — VISIBLE.
                frappe.set_user(desk)
                at_desk = frappe.client.get(subject.doctype, doc.name)
                self.assertEqual(
                    at_desk.get(field),
                    _SIGNATURE,
                    f"{subject.doctype}: {DESK_ROLE} lost the signature it has to verify",
                )

                audit_verdict = "visible" if audited.get(field) else "concealed"
                desk_verdict = "visible" if at_desk.get(field) else "concealed"
                self.assertNotEqual(
                    audit_verdict,
                    desk_verdict,
                    f"{subject.doctype}: both roles produced the same verdict "
                    f"({audit_verdict}) — the pair collapsed: either the permlevel stopped "
                    f"being enforced for anyone, or it is now enforced against {DESK_ROLE} "
                    "too",
                )

    # ---- clause 2: the create path, and why the rows carry WRITE ----

    def test_the_create_path_keeps_the_signature_only_for_a_role_holding_the_write_row(self):
        """The regression this policy could plausibly have caused, per subject.

        On a NEW document the reference for an unreachable level is `frappe.new_doc` — the
        field DEFAULT, not the stored row (base_document.py:1277-1279) — so a caller without
        the row has the signature silently emptied on insert. Exercised through
        `validate_higher_perm_levels`, the exact call `insert` makes (document.py:306), so
        the outcome is about the permlevel and not about the unrelated link permissions a
        full insert needs.
        """
        for subject in SUBJECTS:
            with self.subTest(subject=subject.doctype):
                frappe.set_user("Administrator")
                ctx = subject.context(self)
                desk = self._user_with_role(DESK_ROLE)
                auditor = self._user_with_role(AUDIT_ROLE)

                def surviving_signature(as_user):
                    frappe.set_user(as_user)
                    fresh = frappe.get_doc(subject.payload(self, ctx))
                    # `insert` sets this at document.py:295, eleven lines before it calls
                    # validate_higher_perm_levels at :306, and `is_new()` reads exactly that
                    # flag (base_document.py:465). Setting it here is what makes this the
                    # CREATE path: without it the reset would resolve from `get_latest()` —
                    # a stored row that does not exist yet — and the clause would silently
                    # be about updates instead.
                    fresh.set("__islocal", True)
                    self.assertTrue(
                        fresh.is_new(), "precondition: the create path needs a NEW doc"
                    )
                    fresh.validate_higher_perm_levels()
                    return fresh.get(subject.signature_field)

                kept = surviving_signature(desk)
                blanked = surviving_signature(auditor)

                self.assertEqual(
                    kept,
                    _SIGNATURE,
                    f"{subject.doctype}: {DESK_ROLE} lost the signature on the CREATE path "
                    "— the record would file stamped signed with nothing behind it",
                )
                self.assertFalse(
                    blanked,
                    f"{subject.doctype}: a role with no permlevel-1 row kept a signature it "
                    "cannot reach on create",
                )
                kept_verdict = "kept" if kept else "blanked"
                blanked_verdict = "kept" if blanked else "blanked"
                self.assertNotEqual(
                    kept_verdict,
                    blanked_verdict,
                    f"{subject.doctype}: both roles produced the same verdict "
                    f"({kept_verdict}) — this pair no longer distinguishes a role holding "
                    "the level-1 write row from one that does not",
                )

    # ---- clause 3: the shipped JSON, checked rather than trusted ----

    def test_the_signature_is_level_one_with_rows_for_the_desk_roles_only(self):
        """Rows are counted on the (role, permlevel) PAIR, never the role alone: a level-1
        row is not a duplicate of that role's level-0 row — `is_perm_applicable` keeps only
        permlevel-0 rows (frappe/permissions.py:284) — so deduplicating on role would strip
        exactly the access this policy depends on.
        """
        for subject in SUBJECTS:
            with self.subTest(subject=subject.doctype):
                shipped = subject.shipped()
                rows = shipped["permissions"]

                high = {p["role"] for p in rows if int(p.get("permlevel") or 0) == 1}
                self.assertEqual(
                    high,
                    DESK_ROLES,
                    f"{subject.doctype}: the permlevel-1 role set changed. Adding a role "
                    "hands it every captured signature; removing one silently blanks the "
                    "signature that role captures.",
                )
                self.assertNotIn(
                    AUDIT_ROLE,
                    high,
                    f"{subject.doctype}: {AUDIT_ROLE} holds a permlevel-1 row — that hands "
                    "back the mark this policy exists to keep it from",
                )
                for role in sorted(high):
                    row = [
                        p
                        for p in rows
                        if p["role"] == role and int(p.get("permlevel") or 0) == 1
                    ]
                    self.assertEqual(
                        len(row),
                        1,
                        f"{subject.doctype}/{role}: expected exactly one permlevel-1 row",
                    )
                    # Asserted explicitly, never by omission: an absent DocPerm flag ships as
                    # 0 rather than as its default, so a row written by omission grants
                    # nothing.
                    self.assertEqual(
                        row[0].get("read"),
                        1,
                        f"{subject.doctype}/{role}: permlevel-1 read missing",
                    )
                    self.assertEqual(
                        row[0].get("write"),
                        1,
                        f"{subject.doctype}/{role}: permlevel-1 write missing — the capture "
                        "surface would blank the signature on every record it files",
                    )

                field = [
                    f
                    for f in shipped["fields"]
                    if f["fieldname"] == subject.signature_field
                ][0]
                self.assertEqual(
                    field.get("permlevel"),
                    1,
                    f"{subject.doctype}: {subject.signature_field} is not at permlevel 1",
                )
                # The field must stay optional. A `reqd` field raised to level 1 breaks
                # CREATE for any role without a level-1 write row: the value is blanked at
                # document.py:306 and the mandatory check then fails on the empty field at
                # :417. Every one of these is a capture, not a requirement.
                self.assertFalse(
                    field.get("reqd"),
                    f"{subject.doctype}: the signature became mandatory at level 1 — create "
                    "now dies outright for any role without a level-1 write row",
                )
                described = (field.get("description") or "").lower()
                # Checked for MEANING, not for the token `permlevel`: this is the tooltip a
                # clerk, kiosk operator or supervisor reads, and it goes to the translators
                # as well. Say WHO keeps the field and WHY, never HOW it is enforced.
                self.assertIn(
                    "signature",
                    described,
                    f"{subject.doctype}: the tooltip no longer says what the field is",
                )
                self.assertTrue(
                    {"because", "so", "since"} & set(described.split()),
                    f"{subject.doctype}: the tooltip states the restriction but never says "
                    "WHY it is restricted",
                )
                for jargon in ("permlevel", "level 1", "level 0", "docperm"):
                    self.assertNotIn(
                        jargon,
                        described,
                        f"{subject.doctype}: the tooltip leaks the system term {jargon!r} "
                        "to an operator",
                    )

    def test_the_auditors_level_zero_authority_was_not_collateral_damage(self):
        """The explicit non-change: one field narrowed on each record, not a role's
        authority. Internal Auditor was granted estate-wide read on these for a reason."""
        for subject in SUBJECTS:
            with self.subTest(subject=subject.doctype):
                rows = [
                    p
                    for p in subject.shipped()["permissions"]
                    if p["role"] == AUDIT_ROLE and int(p.get("permlevel") or 0) == 0
                ]
                self.assertEqual(
                    len(rows),
                    1,
                    f"{subject.doctype}: the auditor's level-0 row was moved or duplicated",
                )
                self.assertEqual(
                    rows[0].get("read"),
                    1,
                    f"{subject.doctype}: the auditor's estate-wide read was revoked",
                )
                self.assertEqual(
                    rows[0].get("report"),
                    1,
                    f"{subject.doctype}: the auditor's report access was revoked",
                )
                if subject.auditor_export:
                    self.assertEqual(
                        rows[0].get("export"),
                        1,
                        f"{subject.doctype}: the auditor's export was revoked",
                    )

    # ---- clause 5: the one subject with a portal writer, which no other subject has ----

    def test_the_portal_write_path_is_not_subject_to_the_level(self):
        """Custody Acknowledgment ONLY, and the regression that would have been invisible
        until a worker complained.

        This is the one subject whose signature is written by the SUBJECT rather than by a
        member of staff: the My Custody Acknowledgment Web Form, submitted by the worker over
        the portal. A portal user holds no level-1 row and could never be given one. The flow
        survives only because `web_form.accept` inserts with `ignore_permissions=True`
        (frappe/website/doctype/web_form/web_form.py:663) and re-saves the same way after
        attaching the signature data-URI as a File (:691), while
        `validate_higher_perm_levels` returns immediately on that flag (document.py:785).

        Pinned rather than trusted, as a user holding NO level-1 row: if a future change made
        the level apply to an ignore_permissions insert, every portal acknowledgment would
        file with an empty signature and this is what would say so.
        """
        subject = next(s for s in SUBJECTS if s.doctype == "Custody Acknowledgment")
        ctx = subject.context(self)
        auditor = self._user_with_role(AUDIT_ROLE)

        frappe.set_user(auditor)
        ack = frappe.get_doc(subject.payload(self, ctx))
        ack.insert(ignore_permissions=True, ignore_links=True)

        frappe.set_user("Administrator")
        self.assertEqual(
            frappe.db.get_value(subject.doctype, ack.name, subject.signature_field),
            _SIGNATURE,
            "an ignore_permissions insert blanked the signature — the Web Form path the "
            "portal depends on is now subject to the permlevel, and every worker's "
            "acknowledgment would file empty",
        )
