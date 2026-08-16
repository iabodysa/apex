# Copyright (c) 2026, AFMCO and contributors
"""the acknowledgement gate and the label above it must name the same people.

THE DEFECT. ``accounting_acknowledged_by`` shipped labelled "Acknowledged By (Finance)"
while ``Finance Manager`` held no write on the DocType, and ``_validate_intercompany_gates``
refuses to submit an Intercompany Permanent movement whose ``accounting_acknowledged`` is
unset. So an enforced gate advertised a role that could not reach it, and in practice it
was closed by whoever held System Manager.

WHAT SHIPPED. Both halves were fixed. The label lost its parenthetical, matching its two
sibling Link-to-User fields in the same section, AND the narrow permission shape was built:
the two acknowledgement fields moved BEHIND permlevel 1 and Finance Manager gained a
permlevel-1 read+write row beside its permlevel-0 read row.

WHY FINANCE MANAGER NEEDS BOTH ROWS. Document access resolves from permlevel-0 rows ONLY,
while field access is a separate computation that unions every permlevel the user's roles
hold. A permlevel-1 row alone would leave Finance Manager unable to OPEN the record it is
meant to acknowledge, so the permlevel-0 ``read`` is what lets them reach the form and the
permlevel-1 ``write`` is what lets them tick the flag on it.

WHY THIS ASKS THE FRAMEWORK RATHER THAN THE FILE. The previous version proved the submit
gate exists by grepping the controller's source text for a string, and proved the gate was
WIRED by grepping hooks.py for the dotted path -- neither ran the document lifecycle, so
neither could tell a real submit refusal from a string that merely still appears somewhere.
It graded permissions and labels the same way, reading the shipped JSON rather than asking
`frappe.has_permission` / `frappe.get_meta`. This version drives a real Facility Asset
Movement through insert and submit, and asks the framework's own permission and metadata
APIs the same questions a real caller meets. The behaviour of the sign-off endpoint itself
-- who may give it, who may not, and that it names the giver -- stays graded in
`test_accounting_sign_off.py` beside this file; this file grades the submit-time gate above
it and the schema shape around it.
"""

from __future__ import annotations

import frappe
from frappe.model import get_permitted_fields
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from apex.tests._helpers import _user

DOCTYPE = "Facility Asset Movement"
ACK_FLAG = "accounting_acknowledged"
ACK_USER = "accounting_acknowledged_by"
ACCOUNTING_ROLE = "Finance Manager"

ORIGIN_COMPANY = "_Test Company"
DESTINATION_COMPANY = "_Test Company 1"

DOCUMENT_WRITERS = ("System Manager", "Accommodation Manager", "Resident Supervisor")
SUBMITTERS = ("System Manager", "Accommodation Manager")


def _h(n=12):
    return frappe.generate_hash(length=n).upper()


class _MovementFixture(FrappeTestCase):
    """Shared builder for a genuine intercompany movement, kept out of
    ``TestTheSubmitGateIsReal`` so the fixture cost is paid once per test method
    rather than duplicated by hand in each one."""

    def setUp(self):
        frappe.set_user("Administrator")
        self.site = (
            frappe.get_doc({"doctype": "Site", "site_name": "FAMA " + _h()})
            .insert(ignore_permissions=True)
            .name
        )
        self.addCleanup(frappe.delete_doc, "Site", self.site, force=True, ignore_permissions=True)
        self.origin = self._building()
        self.destination = self._building()
        self.asset = self._asset(self.origin)

    def _building(self):
        doc = frappe.get_doc(
            {
                "doctype": "Building",
                "building_name": "FAMA " + _h(),
                "site": self.site,
                "status": "Active",
                "total_capacity": 2,
            }
        )
        doc.insert(ignore_permissions=True, ignore_mandatory=True)
        self.addCleanup(frappe.delete_doc, "Building", doc.name, force=True, ignore_permissions=True)
        return doc.name

    def _asset(self, building):
        doc = frappe.get_doc(
            {
                "doctype": "Facility Asset",
                "asset_name": "FAMA " + _h(),
                "asset_category": "Other",
                "building": building,
                "responsible_supervisor": "Administrator",
            }
        )
        doc.insert(ignore_permissions=True, ignore_mandatory=True)
        self.addCleanup(
            frappe.delete_doc, "Facility Asset", doc.name, force=True, ignore_permissions=True
        )
        return doc.name

    def _unsubmitted_permanent_transfer(self):
        """An intercompany movement whose category is flipped to Permanent AFTER
        insert, by a raw db write. ``validate`` re-runs the same gate on every save,
        not only on submit, so inserting it directly AS Permanent throws immediately
        and there would be nothing left standing to submit -- the fixture has to reach
        docstatus 0 with the gate's real condition true, and a raw write is the only
        path there."""
        doc = frappe.get_doc(
            {
                "doctype": DOCTYPE,
                "movement_date": today(),
                "movement_category": "Intercompany Temporary",
                "facility_asset": self.asset,
                "from_building": self.origin,
                "to_building": self.destination,
                # is_intercompany is DERIVED from the two companies differing, never set
                # by the caller, so the fixture has to make the movement genuinely
                # intercompany or the gate under test never triggers.
                "from_company": ORIGIN_COMPANY,
                "to_company": DESTINATION_COMPANY,
                "release_approved_by": "Administrator",
                "receiving_confirmed_by": "Administrator",
            }
        )
        doc.insert(ignore_permissions=True, ignore_mandatory=True)
        self.addCleanup(self._drop, doc.name)
        self.assertTrue(
            doc.is_intercompany,
            "the fixture must be a real intercompany movement, or it proves nothing",
        )
        frappe.db.set_value(
            DOCTYPE, doc.name, "movement_category", "Intercompany Permanent",
            update_modified=False,
        )
        doc.reload()
        self.assertFalse(doc.accounting_acknowledged, "the fixture must start unacknowledged")
        return doc

    def _drop(self, name):
        frappe.set_user("Administrator")
        frappe.db.set_value(DOCTYPE, name, "docstatus", 0, update_modified=False)
        frappe.delete_doc(DOCTYPE, name, force=True, ignore_permissions=True)


class TestTheSubmitGateIsReal(_MovementFixture):
    """The premise, driven through a real insert-then-submit rather than assumed from
    source text: this is an enforced gate, so the label naming who can pass it is a
    claim about behaviour, not decoration."""

    def test_an_unacknowledged_permanent_transfer_is_refused_on_submit(self):
        doc = self._unsubmitted_permanent_transfer()

        with self.assertRaises(frappe.ValidationError):
            doc.submit()

        doc.reload()
        self.assertEqual(doc.docstatus, 0, "the refused submit must not have gone through")

    def test_the_same_transfer_submits_once_the_flag_is_set(self):
        """Guard-of-the-guard: the gate must be satisfiable. Without this, the refusal
        above could be any bug in the fixture -- a missing mandatory field, a broken
        insert -- rather than the acknowledgement check specifically."""
        doc = self._unsubmitted_permanent_transfer()
        frappe.db.set_value(
            DOCTYPE, doc.name,
            {"accounting_acknowledged": 1, "accounting_acknowledged_by": "Administrator"},
            update_modified=False,
        )
        doc.reload()

        doc.submit()

        doc.reload()
        self.assertEqual(doc.docstatus, 1)


class TestPermissionsMatchTheGate(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.finance_only = _user("fam_perms_finance@example.com", ACCOUNTING_ROLE)
        cls.writers = {
            role: _user(f"fam_perms_{role.lower().replace(' ', '_')}@example.com", role)
            for role in DOCUMENT_WRITERS
        }

    def test_finance_manager_holds_document_read_and_the_field_write_and_nothing_else(self):
        """One permlevel-0 read to reach the form, one permlevel-1 read+write to tick the
        flag on it. Any further document right is a blanket grant no one decided."""
        self.assertTrue(frappe.has_permission(DOCTYPE, "read", user=self.finance_only))
        for denied in ("write", "create", "submit", "cancel", "amend", "delete"):
            with self.subTest(ptype=denied):
                self.assertFalse(
                    frappe.has_permission(DOCTYPE, denied, user=self.finance_only),
                    f"Finance Manager gained document-level {denied}",
                )
        writable = get_permitted_fields(DOCTYPE, user=self.finance_only, permission_type="write")
        for fieldname in (ACK_FLAG, ACK_USER):
            self.assertIn(fieldname, writable)

    def test_three_roles_hold_document_write_not_two(self):
        """The card said two. Resident Supervisor holds permlevel-0 write as well, and
        can therefore edit the movement without being able to submit it."""
        for role, user in self.writers.items():
            with self.subTest(role=role):
                self.assertTrue(frappe.has_permission(DOCTYPE, "write", user=user))
                self.assertEqual(
                    frappe.has_permission(DOCTYPE, "submit", user=user),
                    role in SUBMITTERS,
                    f"{role}'s submit right does not match the shipped shape",
                )

    def test_every_writer_of_the_gate_can_also_submit_or_hand_off(self):
        """The gate must stay satisfiable: at least one role can both edit the movement
        and submit it."""
        can_submit_and_write = [
            role
            for role in DOCUMENT_WRITERS
            if frappe.has_permission(DOCTYPE, "write", user=self.writers[role])
            and frappe.has_permission(DOCTYPE, "submit", user=self.writers[role])
        ]
        self.assertTrue(can_submit_and_write, "no writer of the movement can also submit it")

    def test_the_permlevel_one_grant_reaches_the_two_acknowledgement_fields_only(self):
        """A permlevel is a wall around a named set of fields. Widening that set
        silently hands Finance Manager write on whatever else was moved behind it."""
        bystander = _user("fam_perms_bystander@example.com", "Employee")
        baseline = set(
            get_permitted_fields(DOCTYPE, user=bystander, permission_type="write")
        )
        finance_writable = set(
            get_permitted_fields(DOCTYPE, user=self.finance_only, permission_type="write")
        )
        self.assertEqual(finance_writable - baseline, {ACK_FLAG, ACK_USER})

    def test_accounting_is_the_only_role_that_can_write_behind_the_wall(self):
        """A permlevel is a wall around a named set of fields. Any of the three document
        writers reaching the acknowledgement fields is a silent widening of who can close
        the control."""
        writable = get_permitted_fields(DOCTYPE, user=self.finance_only, permission_type="write")
        for fieldname in (ACK_FLAG, ACK_USER):
            self.assertIn(fieldname, writable, f"Finance Manager lost write on {fieldname}")

        for role, user in self.writers.items():
            with self.subTest(role=role):
                writable = get_permitted_fields(DOCTYPE, user=user, permission_type="write")
                for fieldname in (ACK_FLAG, ACK_USER):
                    self.assertNotIn(
                        fieldname, writable,
                        f"{role} can write {fieldname}; only Finance Manager may",
                    )


class TestLabelAndPermissionsAgree(FrappeTestCase):
    def test_the_label_no_longer_names_a_role(self):
        """The regression this file exists to prevent: any parenthetical naming an org
        function is a promise the DocPerm rows have to keep."""
        meta = frappe.get_meta(DOCTYPE)
        self.assertEqual(meta.get_field(ACK_USER).label, "Acknowledged By")

    def test_it_matches_its_two_sibling_user_links_in_the_same_section(self):
        meta = frappe.get_meta(DOCTYPE)
        for sibling in ("release_approved_by", "receiving_confirmed_by"):
            field = meta.get_field(sibling)
            self.assertNotIn("(", field.label)
            self.assertEqual(field.options, "User")
        self.assertEqual(meta.get_field(ACK_USER).options, "User")

    def test_both_acknowledgement_fields_sit_behind_permlevel_one_and_survive_submit(self):
        """Drop the permlevel and any permlevel-0 writer can close a control they are not
        entitled to close; drop allow_on_submit and nobody can close it at all on the
        submitted document it belongs to."""
        meta = frappe.get_meta(DOCTYPE)
        for fieldname in (ACK_FLAG, ACK_USER):
            with self.subTest(field=fieldname):
                field = meta.get_field(fieldname)
                self.assertEqual(field.permlevel, 1)
                self.assertTrue(field.allow_on_submit, "cannot be set after submit")
