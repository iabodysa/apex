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
APIs the same questions a real caller meets.

``TestTheAccountingSignOffCanBeGiven`` below grades the sign-off endpoint itself -- who may
give it, who may not, and that it names the giver -- against its own fixture: a movement
built ALREADY SUBMITTED (docstatus forced to 1), because the endpoint only ever acts on a
submitted document. ``TestTheSubmitGateIsReal`` above it needs the opposite: a movement
built and left UNSUBMITTED, with its category flipped to Permanent by a raw write after
insert, so the submit-time gate itself still has something to refuse. The two fixtures
cannot share one `setUp` without one of them losing its subject, so
``TestTheAccountingSignOffCanBeGiven`` keeps its own.
"""

from __future__ import annotations

import frappe
from frappe.model import get_permitted_fields
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from apex.habitat.doctype.facility_asset_movement.facility_asset_movement import (
    acknowledge_intercompany_movement,
)
from apex.tests._helpers import _user
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch
from apex.habitat.doctype.facility_asset_movement import facility_asset_movement
import glob
import json
import os
import apex
from apex.habitat import permissions as P
from apex.tests._helpers import as_user
from apex.tests.factories import make_scoped_supervisor

DOCTYPE = "Facility Asset Movement"
ACK_FLAG = "accounting_acknowledged"
ACK_USER = "accounting_acknowledged_by"
ACCOUNTING_ROLE = "Finance Manager"

ORIGIN_COMPANY = "_Test Company"
DESTINATION_COMPANY = "_Test Company 1"

DOCUMENT_WRITERS = ("System Manager", "Accommodation Manager", "Resident Supervisor")
SUBMITTERS = ("System Manager", "Accommodation Manager")

# The pending-acknowledgement Number Card's own filter, reused by
# TestTheAccountingSignOffCanBeGiven to prove a sign-off is what clears it.
TILE_FILTERS = [
    ["is_intercompany", "=", 1],
    ["accounting_acknowledged", "=", 0],
    ["docstatus", "=", 1],
]


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


class TestTheAccountingSignOffCanBeGiven(FrappeTestCase):
    """The endpoint itself, driven against an ALREADY SUBMITTED intercompany movement —
    the opposite starting state from ``TestTheSubmitGateIsReal`` above, which needs its
    movement left unsubmitted so the submit-time gate still has something to refuse.
    That is why this class keeps its own fixture rather than reusing ``_MovementFixture``.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.accountant = cls._user([ACCOUNTING_ROLE])
        cls.preparer = cls._user(["Accommodation Manager"])
        # The accountant who ALSO submitted: the self-acknowledgement case has to be a
        # user who holds the role, or the role check would be what refuses it and the
        # test would prove the wrong thing.
        cls.accountant_preparer = cls._user([ACCOUNTING_ROLE, "Accommodation Manager"])

    @classmethod
    def _user(cls, roles):
        doc = frappe.get_doc(
            {
                "doctype": "User",
                "email": f"fam-{_h()}@example.com".lower(),
                "first_name": "_T Fixture",
                "send_welcome_email": 0,
                "roles": [{"role": r} for r in roles],
            }
        ).insert(ignore_permissions=True)
        cls.addClassCleanup(
            frappe.delete_doc, "User", doc.name, force=True, ignore_permissions=True
        )
        return doc.name

    def setUp(self):
        frappe.set_user("Administrator")
        self.site = frappe.get_doc(
            {"doctype": "Site", "site_name": "FAM " + _h()}
        ).insert(ignore_permissions=True).name
        self.addCleanup(
            frappe.delete_doc, "Site", self.site, force=True, ignore_permissions=True
        )
        self.origin = self._building()
        self.destination = self._building()
        self.asset = self._asset(self.origin)

    def _building(self):
        doc = frappe.get_doc(
            {
                "doctype": "Building",
                "building_name": "FAM " + _h(),
                "site": self.site,
                "status": "Active",
                "total_capacity": 2,
            }
        )
        doc.insert(ignore_permissions=True, ignore_mandatory=True)
        self.addCleanup(
            frappe.delete_doc, "Building", doc.name, force=True, ignore_permissions=True
        )
        return doc.name

    def _asset(self, building):
        doc = frappe.get_doc(
            {
                "doctype": "Facility Asset",
                "asset_name": "FAM " + _h(),
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

    def tearDown(self):
        frappe.set_user("Administrator")

    def _submitted_movement(self, owner=None, category="Intercompany Temporary"):
        doc = frappe.get_doc(
            {
                "doctype": DOCTYPE,
                "movement_date": today(),
                "movement_category": category,
                "facility_asset": self.asset,
                "from_building": self.origin,
                "to_building": self.destination,
                # is_intercompany is DERIVED from the two companies differing, never set
                # by the caller, so the fixture has to make the movement genuinely
                # intercompany rather than assert the flag.
                "from_company": ORIGIN_COMPANY,
                "to_company": DESTINATION_COMPANY,
                "release_approved_by": "Administrator",
                "receiving_confirmed_by": "Administrator",
            }
        )
        doc.insert(ignore_permissions=True, ignore_mandatory=True)
        self.assertTrue(
            doc.is_intercompany,
            "the fixture must be a real intercompany movement, or it proves nothing",
        )
        if owner:
            frappe.db.set_value(
                DOCTYPE, doc.name, "owner", owner, update_modified=False
            )
        frappe.db.set_value(
            DOCTYPE, doc.name, "docstatus", 1, update_modified=False
        )
        self.addCleanup(self._drop, doc.name)
        doc.reload()
        return doc

    def _drop(self, name):
        frappe.set_user("Administrator")
        frappe.db.set_value(DOCTYPE, name, "docstatus", 0, update_modified=False)
        frappe.delete_doc(DOCTYPE, name, force=True, ignore_permissions=True)

    def _tile_count(self):
        from frappe.client import get_count

        return int(get_count(DOCTYPE, filters=TILE_FILTERS))

    def test_accounting_can_sign_off_and_the_record_says_who(self):
        doc = self._submitted_movement(owner=self.preparer)
        before = self._tile_count()

        frappe.set_user(self.accountant)
        acknowledge_intercompany_movement(doc.name)

        doc.reload()
        self.assertTrue(doc.accounting_acknowledged)
        self.assertEqual(
            doc.accounting_acknowledged_by,
            self.accountant,
            "the sign-off must name the person who gave it",
        )
        frappe.set_user("Administrator")
        self.assertEqual(
            self._tile_count(), before - 1, "the pending tile did not come back down"
        )

    def test_a_caller_without_the_accounting_role_is_refused(self):
        doc = self._submitted_movement(owner=self.preparer)
        frappe.set_user(self.preparer)

        with self.assertRaises(frappe.PermissionError):
            acknowledge_intercompany_movement(doc.name)

        frappe.set_user("Administrator")
        doc.reload()
        self.assertFalse(doc.accounting_acknowledged)

    def test_the_submitter_cannot_acknowledge_their_own_movement(self):
        """The refusal that makes it a control. This caller HOLDS the accounting role, so
        only the self-check can be what refuses them."""
        doc = self._submitted_movement(owner=self.accountant_preparer)
        frappe.set_user(self.accountant_preparer)

        with self.assertRaises(frappe.PermissionError):
            acknowledge_intercompany_movement(doc.name)

        frappe.set_user("Administrator")
        doc.reload()
        self.assertFalse(doc.accounting_acknowledged)

    def test_a_second_call_does_not_change_who_signed(self):
        doc = self._submitted_movement(owner=self.preparer)
        frappe.set_user(self.accountant)
        acknowledge_intercompany_movement(doc.name)
        again = acknowledge_intercompany_movement(doc.name)

        self.assertEqual(
            again["acknowledged_by"],
            self.accountant,
            "a repeat call must not re-stamp the signature with a later caller",
        )

    def test_the_fields_are_reachable_after_submit_at_all(self):
        """The root of the defect, held on the schema rather than on behaviour: without
        allow_on_submit no path could set these on a submitted document, and without the
        permlevel any writer could."""
        meta = frappe.get_meta(DOCTYPE)
        for fieldname in ("accounting_acknowledged", "accounting_acknowledged_by"):
            field = meta.get_field(fieldname)
            with self.subTest(field=fieldname):
                self.assertTrue(field.allow_on_submit, "cannot be set after submit")
                self.assertEqual(field.permlevel, 1, "any writer could set it")

        writers = {
            p.role
            for p in meta.permissions
            if p.permlevel == 1 and p.write
        }
        self.assertEqual(
            writers, {ACCOUNTING_ROLE}, "permlevel-1 write must be Accounting alone"
        )

test_ignore = ['Additional Salary', 'Asset', 'Asset Movement', 'Company', 'Cost Center', 'Currency', 'Employee', 'Item', 'Payment Entry', 'Project', 'Purchase Invoice', 'Role', 'Salary Component', 'Supplier', 'User']


# --- merged from test_facility_asset_movement_acknowledgement_rules.py ---
ENDPOINT = "acknowledge_intercompany_movement"
def _raising_frappe(user="accountant@example.com") -> MagicMock:
    fake = MagicMock()
    fake.PermissionError = frappe.PermissionError
    fake.session = SimpleNamespace(user=user)

    def throw(message, exc=None, **_kwargs):
        raise (exc or frappe.ValidationError)(message)

    fake.throw.side_effect = throw
    return fake
def _movement(**overrides):
    movement = MagicMock()
    movement.name = "MOVE-1"
    movement.docstatus = 1
    movement.is_intercompany = 1
    movement.owner = "preparer@example.com"
    movement.accounting_acknowledged = 0
    movement.has_permlevel_access_to.return_value = True
    for key, value in overrides.items():
        setattr(movement, key, value)
    return movement
def _call(movement, user="accountant@example.com"):
    fake = _raising_frappe(user)
    fake.get_doc.return_value = movement
    endpoint = getattr(facility_asset_movement, ENDPOINT)
    with (
        patch.object(facility_asset_movement, "frappe", fake),
        patch.object(facility_asset_movement, "_", side_effect=lambda message: message),
    ):
        return getattr(endpoint, "__wrapped__", endpoint)("MOVE-1")
class TestEveryAcknowledgementRefusalIsExercised(TestCase):
    def test_an_unsubmitted_movement_is_refused(self):
        for docstatus in (0, 2):
            with self.subTest(docstatus=docstatus):
                movement = _movement(docstatus=docstatus)
                with self.assertRaises(frappe.ValidationError):
                    _call(movement)
                movement.db_set.assert_not_called()

    def test_a_same_company_movement_is_refused(self):
        movement = _movement(is_intercompany=0)
        with self.assertRaises(frappe.ValidationError):
            _call(movement)
        movement.db_set.assert_not_called()

    def test_the_submitter_cannot_sign_off_their_own_movement(self):
        movement = _movement(owner="preparer@example.com")
        with self.assertRaises(frappe.PermissionError):
            _call(movement, user="preparer@example.com")
        movement.db_set.assert_not_called()

    def test_a_permitted_accountant_signs_off_and_the_record_names_them(self):
        movement = _movement()
        result = _call(movement)

        movement.db_set.assert_called_once_with(
            {
                "accounting_acknowledged": 1,
                "accounting_acknowledged_by": "accountant@example.com",
            },
            update_modified=True,
        )
        self.assertEqual(result["acknowledged_by"], "accountant@example.com")

    def test_a_repeat_call_writes_nothing_further(self):
        movement = _movement(
            accounting_acknowledged=1, accounting_acknowledged_by="first@example.com"
        )
        result = _call(movement)

        movement.db_set.assert_not_called()
        self.assertEqual(result["acknowledged_by"], "first@example.com")
class TestTheSignOffIsReachableFromTheForm(TestCase):
    def test_the_form_script_calls_the_endpoint(self):
        script = (
            Path(__file__).with_name("facility_asset_movement.js").read_text(encoding="utf-8")
        )
        self.assertIn(
            ENDPOINT,
            script,
            "with no client caller the pending-acknowledgement queue can only count up",
        )
        self.assertIn(
            "add_custom_button",
            script,
            "the endpoint needs a control on the form, not just a name in a string",
        )
class TestFacilityAssetMovementAcknowledgement(TestCase):
    """Coarser-grained mock of the same endpoint: patches the two permission
    primitives directly on the module's real ``frappe`` object rather than
    replacing ``frappe`` wholesale, so a change to which permission call the
    endpoint makes shows up here independent of the outcome-level refusals above."""

    def test_acknowledgement_uses_document_and_field_permissions(self):
        movement = MagicMock()
        movement.name = "MOVE-1"
        movement.docstatus = 1
        movement.is_intercompany = 1
        movement.owner = "preparer@example.com"
        movement.accounting_acknowledged = 0
        movement.has_permlevel_access_to.return_value = True

        with (
            patch.object(facility_asset_movement.frappe, "get_doc", return_value=movement),
            patch.object(
                facility_asset_movement.frappe,
                "get_roles",
                return_value=["Finance Manager"],
            ),
            patch.object(
                facility_asset_movement.frappe,
                "session",
                SimpleNamespace(user="accountant@example.com"),
            ),
        ):
            facility_asset_movement.acknowledge_intercompany_movement("MOVE-1")

        movement.check_permission.assert_called_once_with("read")
        movement.has_permlevel_access_to.assert_called_once_with(
            "accounting_acknowledged",
            permission_type="write",
        )

    def test_acknowledgement_rejects_field_without_write_permission(self):
        movement = MagicMock()
        movement.name = "MOVE-1"
        movement.docstatus = 1
        movement.is_intercompany = 1
        movement.owner = "preparer@example.com"
        movement.accounting_acknowledged = 0
        movement.has_permlevel_access_to.return_value = False

        with (
            patch.object(facility_asset_movement.frappe, "get_doc", return_value=movement),
            patch.object(
                facility_asset_movement.frappe,
                "session",
                SimpleNamespace(user="accountant@example.com"),
            ),
            self.assertRaises(frappe.PermissionError),
        ):
            facility_asset_movement.acknowledge_intercompany_movement("MOVE-1")

        movement.db_set.assert_not_called()


# --- merged from test_facility_asset_movement_effects.py ---
_MOVEMENT_HOOKS = ("on_submit", "on_cancel")
class TestFacilityAssetMovementEffects(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        tag = self._testMethodName
        self.bldg_a = frappe.get_doc(
            {"doctype": "Building", "building_name": f"FAM-EFFECTS A {tag}"}
        ).insert(ignore_permissions=True).name
        self.bldg_b = frappe.get_doc(
            {"doctype": "Building", "building_name": f"FAM-EFFECTS B {tag}"}
        ).insert(ignore_permissions=True).name
        self.room_l0 = frappe.get_doc(
            {
                "doctype": "Room",
                "building": self.bldg_a,
                "room_number": f"FAM-EFFECTS L0 {tag}",
            }
        ).insert(ignore_permissions=True).name
        self.room_l1 = frappe.get_doc(
            {
                "doctype": "Room",
                "building": self.bldg_b,
                "room_number": f"FAM-EFFECTS L1 {tag}",
            }
        ).insert(ignore_permissions=True).name
        self.asset = frappe.get_doc(
            {
                "doctype": "Facility Asset",
                "asset_name": f"FAM-EFFECTS Asset {tag}",
                "asset_category": "CCTV Camera",
                "building": self.bldg_a,
                "location_in_building": self.room_l0,
                "responsible_supervisor": "Administrator",
            }
        ).insert(ignore_permissions=True).name

        seeded = frappe.db.get_value(
            "Facility Asset",
            self.asset,
            ["building", "location_in_building", "movement_count"],
            as_dict=True,
        )
        self.assertEqual(seeded.building, self.bldg_a, "seed asset must start at building A")
        self.assertEqual(seeded.location_in_building, self.room_l0, "seed asset must start at L0")
        self.assertEqual((seeded.movement_count or 0), 0, "seed asset must have no movements yet")

    def tearDown(self):
        frappe.set_user("Administrator")

    def _movement(self):
        return frappe.get_doc(
            {
                "doctype": "Facility Asset Movement",
                "movement_date": today(),
                "facility_asset": self.asset,
                "movement_category": "Same-Company Relocation",
                "from_building": self.bldg_a,
                "from_room": self.room_l0,
                "to_building": self.bldg_b,
                "to_room": self.room_l1,
            }
        ).insert(ignore_permissions=True)

    def test_submit_relocates_asset_and_bumps_audit(self):
        import apex.hooks as hooks

        wired = hooks.doc_events.get("Facility Asset Movement", {})
        for hook in _MOVEMENT_HOOKS:
            self.assertIn(hook, wired, f"Facility Asset Movement must wire {hook}")

        mv = self._movement()
        mv.submit()

        asset = frappe.db.get_value(
            "Facility Asset",
            self.asset,
            [
                "building",
                "location_in_building",
                "previous_building",
                "previous_location_in_building",
                "movement_count",
            ],
            as_dict=True,
        )
        self.assertEqual(asset.building, self.bldg_b, "submit must move the asset to building B")
        self.assertEqual(
            asset.location_in_building, self.room_l1, "submit must move the asset to L1"
        )
        self.assertEqual(
            asset.previous_building, self.bldg_a, "submit must snapshot the prior building A"
        )
        self.assertEqual(
            asset.previous_location_in_building,
            self.room_l0,
            "submit must snapshot the prior location L0",
        )
        self.assertEqual(asset.movement_count, 1, "submit must bump movement_count to 1")

    def test_cancel_reverts_asset_to_origin(self):
        mv = self._movement()
        mv.submit()
        mv.db_set("cancellation_reason", "Movement reversed in test")
        mv.reload()
        mv.cancel()

        asset = frappe.db.get_value(
            "Facility Asset",
            self.asset,
            ["building", "location_in_building", "movement_count"],
            as_dict=True,
        )
        self.assertEqual(asset.building, self.bldg_a, "cancel must revert the asset to building A")
        self.assertEqual(
            asset.location_in_building, self.room_l0, "cancel must revert the asset to L0"
        )
        self.assertEqual(asset.movement_count, 0, "cancel must decrement movement_count back to 0")

    # A delivered room that is not a Room record must survive the next movement, not be erased.

    FREE_TEXT_ROOM = "Storage Annex B"

    def test_movement_round_trip_preserves_a_room_that_is_not_a_room_record(self):
        """An asset parked in a free-text room survives submit + cancel.

        Facility Asset Delivery.to_location_in_building is Data and Facility Asset
        .location_in_building is Data, but the movement's from_room/to_room are Link
        Room. So a delivery can park an asset in a room string that is not a Room
        record. _reconcile_origin narrows that to the Link and leaves from_room blank,
        which is unavoidable; what was NOT unavoidable is that on_submit then ledgered
        the blank as the origin and on_cancel restored the blank onto the asset --
        erasing the only record of where the asset came from, with no warning.

        The ledger's from_location is Data, so it can hold the recorded room whatever
        its shape; the origin is kept there and read back on cancel, the same way
        Facility Asset Delivery.on_cancel already does through ledgered_origin.
        """
        # The state a delivery leaves behind: its destination room is Data, and
        # move_asset_on_delivery copies it verbatim onto the asset's Data room. Asserted
        # on the meta rather than staged through a whole 3-exit delivery, so this stays a
        # movement test -- but it is why a non-Room string can be there at all.
        for doctype, field in (
            ("Facility Asset Delivery", "to_location_in_building"),
            ("Facility Asset", "location_in_building"),
        ):
            self.assertEqual(
                frappe.get_meta(doctype).get_field(field).fieldtype,
                "Data",
                f"{doctype}.{field} must be free text for this scenario to be reachable",
            )
        frappe.db.set_value(
            "Facility Asset", self.asset, "location_in_building", self.FREE_TEXT_ROOM
        )
        self.assertFalse(
            frappe.db.exists("Room", self.FREE_TEXT_ROOM),
            "the fixture room must NOT be a Room record, or this proves nothing",
        )

        mv = frappe.get_doc(
            {
                "doctype": "Facility Asset Movement",
                "movement_date": today(),
                "facility_asset": self.asset,
                "movement_category": "Same-Company Relocation",
                "from_building": self.bldg_a,
                "to_building": self.bldg_b,
                "to_room": self.room_l1,
            }
        ).insert(ignore_permissions=True)
        self.assertFalse(
            mv.from_room, "a non-Room origin cannot go in the Link field; from_room stays blank"
        )
        mv.submit()

        # The room the asset actually left survives in the ledger, not in from_room.
        self.assertEqual(
            frappe.db.get_value(
                "Facility Asset Movement Ledger",
                {"source_doctype": mv.doctype, "source_name": mv.name, "reversal_of": ["is", "not set"]},
                "from_location",
            ),
            self.FREE_TEXT_ROOM,
            "the movement must ledger the room the asset really left, not the blank Link",
        )

        mv.db_set("cancellation_reason", "Movement reversed in test")
        mv.reload()
        mv.cancel()

        self.assertEqual(
            frappe.db.get_value("Facility Asset", self.asset, "location_in_building"),
            self.FREE_TEXT_ROOM,
            "cancel must put the asset back in the room it came from, not blank it",
        )

    _AUDIT_TRAIL = (
        "previous_building",
        "previous_location_in_building",
        "last_movement_date",
    )

    def _audit_trail(self):
        return frappe.db.get_value(
            "Facility Asset", self.asset, list(self._AUDIT_TRAIL), as_dict=True
        )

    def test_cancel_clears_the_audit_trail_of_the_movement_it_undid(self):
        """previous_*/last_movement_date are on_submit snapshots; on_cancel must reset
        them together with the location, or reverting the only movement on a fresh
        asset would read "at A, prior location also A" while still stamped with the
        date of a move that no longer exists. The audit PAIR must survive or vanish
        together with the movement it describes."""
        before = self._audit_trail()
        # A never-moved asset carries no trail; that is the value cancel must return to.
        self.assertFalse(before.previous_building, "seed asset must carry no previous building")
        self.assertFalse(before.last_movement_date, "seed asset must carry no movement date")

        mv = self._movement()
        mv.submit()
        stamped = self._audit_trail()
        self.assertEqual(
            stamped.previous_building, self.bldg_a, "submit must stamp the prior building"
        )
        self.assertTrue(stamped.last_movement_date, "submit must stamp the movement date")

        mv.db_set("cancellation_reason", "Movement reversed in test")
        mv.reload()
        mv.cancel()

        after = self._audit_trail()
        for field in self._AUDIT_TRAIL:
            # NULL and "" both read as blank; compare on that axis, not on identity.
            self.assertEqual(
                after.get(field) or None,
                before.get(field) or None,
                f"cancel must return {field} to its pre-submit value",
            )
        self.assertNotEqual(
            after.previous_building,
            self.bldg_a,
            "an asset back at A must not also claim it was previously at A",
        )

    # An out-of-order cancel must not restore from_* blindly: that would drag an asset that has
    # already moved on back to a building it has physically left.

    def _second_leg(self):
        """Building C + room L2, and a SUBMITTED second movement B -> C on the same
        asset. Returns (bldg_c, room_l2, movement)."""
        tag = self._testMethodName
        bldg_c = frappe.get_doc(
            {"doctype": "Building", "building_name": f"FAM-EFFECTS C {tag}"}
        ).insert(ignore_permissions=True).name
        room_l2 = frappe.get_doc(
            {"doctype": "Room", "building": bldg_c, "room_number": f"FAM-EFFECTS L2 {tag}"}
        ).insert(ignore_permissions=True).name
        mv2 = frappe.get_doc(
            {
                "doctype": "Facility Asset Movement",
                "movement_date": today(),
                "facility_asset": self.asset,
                "movement_category": "Same-Company Relocation",
                "from_building": self.bldg_b,
                "from_room": self.room_l1,
                "to_building": bldg_c,
                "to_room": room_l2,
            }
        ).insert(ignore_permissions=True)
        mv2.submit()
        return bldg_c, room_l2, mv2

    def test_cancelling_a_superseded_movement_cannot_drag_the_asset_back(self):
        mv1 = self._movement()
        mv1.submit()
        bldg_c, room_l2, _mv2 = self._second_leg()
        self.assertEqual(
            frappe.db.get_value("Facility Asset", self.asset, "building"),
            bldg_c,
            "the second movement must have left the asset at C",
        )

        mv1.db_set("cancellation_reason", "Out-of-order cancel attempt")
        mv1.reload()
        with self.assertRaises(frappe.ValidationError) as caught:
            mv1.cancel()
        # Every framework pre-cancel check subclasses ValidationError too, so a bare
        # assertRaises would pass on a link or timestamp failure instead of the guard.
        self.assertNotIsInstance(
            caught.exception,
            (frappe.LinkValidationError, frappe.TimestampMismatchError),
            "the refusal must come from the ordering guard, not a framework pre-cancel check",
        )

        asset = frappe.db.get_value(
            "Facility Asset",
            self.asset,
            ["building", "location_in_building", "movement_count"],
            as_dict=True,
        )
        self.assertEqual(
            asset.building, bldg_c, "a superseded cancel must leave the asset at C"
        )
        self.assertNotEqual(
            asset.building, self.bldg_a, "the asset must never be dragged back to A"
        )
        self.assertEqual(asset.location_in_building, room_l2, "the room must stay at L2")
        self.assertEqual(asset.movement_count, 2, "a refused cancel must not decrement the count")
        self.assertEqual(
            frappe.db.get_value("Facility Asset Movement", mv1.name, "docstatus"),
            1,
            "a refused cancel must leave the first movement submitted",
        )

    def test_cancelling_newest_first_walks_the_asset_back_leg_by_leg(self):
        """The remedy the refusal message names must actually work, or the guard is
        a dead end rather than an ordering rule."""
        mv1 = self._movement()
        mv1.submit()
        _bldg_c, _room_l2, mv2 = self._second_leg()

        for mv in (mv2, mv1):
            mv.db_set("cancellation_reason", "Reversed newest first in test")
            mv.reload()
            mv.cancel()

        asset = frappe.db.get_value(
            "Facility Asset",
            self.asset,
            ["building", "location_in_building", "movement_count"],
            as_dict=True,
        )
        self.assertEqual(asset.building, self.bldg_a, "last-in-first-out must land back at A")
        self.assertEqual(asset.location_in_building, self.room_l0, "and back at L0")
        self.assertEqual(asset.movement_count, 0, "both cancels must decrement the count")
class TestFacilityAssetMovement(FrappeTestCase):
    """Basic validate()-level rules: mandatory fields, same-building refusal, and the
    intercompany flag being derived rather than settable."""

    def test_create_valid_movement(self):
        doc = frappe.get_doc({
            "doctype": "Facility Asset Movement",
            "naming_series": "FAM-.YYYY.-.####",
            "movement_date": "2026-06-01",
            "facility_asset": "FAC-AST-QA",
            "from_building": "BLDG-A",
            "to_building": "BLDG-B",
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertIsNotNone(doc.name)
        frappe.delete_doc("Facility Asset Movement", doc.name, force=True, ignore_permissions=True)

    def test_missing_facility_asset_raises(self):
        doc = frappe.get_doc({
            "doctype": "Facility Asset Movement",
            "naming_series": "FAM-.YYYY.-.####",
            "movement_date": "2026-06-01",
            "to_building": "BLDG-B",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_same_from_and_to_raises(self):
        from apex.habitat.doctype.facility_asset_movement.facility_asset_movement import validate

        doc = frappe.get_doc({
            "doctype": "Facility Asset Movement",
            "movement_date": "2026-06-01",
            "facility_asset": "FAC-AST-QA",
            "from_building": "BLDG-SAME",
            "to_building": "BLDG-SAME",
        })
        with self.assertRaises(frappe.ValidationError):
            validate(doc)

    def test_intercompany_detected_in_validate_enforces_gate(self):
        from apex.habitat.doctype.facility_asset_movement.facility_asset_movement import validate

        doc = frappe.get_doc({
            "doctype": "Facility Asset Movement",
            "movement_date": "2026-06-01",
            "facility_asset": "FAC-AST-QA",
            "from_building": "BLDG-A",
            "to_building": "BLDG-B",
            "from_company": "Company X",
            "to_company": "Company Y",
        })
        with self.assertRaises(frappe.ValidationError):
            validate(doc)
        self.assertEqual(doc.is_intercompany, 1)
class TestFacilityAssetMovementOriginReconcile(FrappeTestCase):
    """from_building/from_room are reconciled to the asset's actual location: a
    hand-entered origin that contradicts the asset is rejected, and a blank origin is
    defaulted from the asset so cancel reverts to a trustworthy prior location."""

    def _h(self):
        return frappe.generate_hash(length=12).upper()

    def _building(self, name):
        if not frappe.db.exists("Building", name):
            frappe.get_doc({
                "doctype": "Building", "building_name": name,
            }).insert(ignore_permissions=True, ignore_mandatory=True)
        return name

    def setUp(self):
        h = self._h()
        self.b1 = self._building("ORIG-A-" + h)
        self.b2 = self._building("ORIG-B-" + h)
        self.asset = frappe.get_doc({
            "doctype": "Facility Asset", "naming_series": "FAC-AST-.YYYY.-.####",
            "asset_name": "Origin-QA " + h, "asset_category": "Other", "building": self.b1,
        }).insert(ignore_permissions=True, ignore_mandatory=True).name

    def test_mismatched_from_building_rejected(self):
        """RED before fix: from_building was hand-entered and never checked, so a wrong
        origin slipped through (and on_cancel would later revert the asset to it). GREEN:
        validate throws when from_building contradicts the asset's current building."""
        from apex.habitat.doctype.facility_asset_movement.facility_asset_movement import validate

        doc = frappe.get_doc({
            "doctype": "Facility Asset Movement",
            "movement_date": "2026-06-01",
            "facility_asset": self.asset,
            "from_building": self.b2,
            "to_building": self.b1,
        })
        with self.assertRaises(frappe.ValidationError):
            validate(doc)

    def test_blank_origin_defaulted_and_cancel_restores_true_prior(self):
        """A blank from_building is defaulted from the asset, so after a move and a
        cancel the asset is restored to its genuine prior building (b1), not a phantom."""
        mv = frappe.get_doc({
            "doctype": "Facility Asset Movement",
            "naming_series": "FAM-.YYYY.-.####",
            "movement_date": "2026-06-01",
            "facility_asset": self.asset,
            "to_building": self.b2,
        })
        mv.insert(ignore_permissions=True, ignore_links=True)
        self.assertEqual(mv.from_building, self.b1)
        mv.submit()
        self.assertEqual(
            frappe.db.get_value("Facility Asset", self.asset, "building"), self.b2
        )
        mv.db_set("cancellation_reason", "QA origin test")
        mv.reload()
        mv.cancel()
        self.assertEqual(
            frappe.db.get_value("Facility Asset", self.asset, "building"), self.b1
        )
class TestFacilityAssetMovementLedger(FrappeTestCase):
    """The two ledger properties no OTHER module covers: a posted row cannot be edited,
    and re-posting the same movement does not post twice.

    ``test_submit_posts_one_immutable_from_to_row`` and ``test_cancel_posts_negated_reversal``
    are deliberately absent from this class: both are covered field-for-field and more strictly
    by ``test_facility_asset_movement_reachability`` — its
    ``test_submit_posts_exactly_one_ledger_effect`` counts the ledger GLOBALLY as well as per
    source (so a double post anywhere fails, which a count-by-source version could not
    catch), and its ``test_cancel_preserves_the_audit_trail`` asserts the original row
    survives unedited alongside exactly one reversal that points back at it. Duplicating the
    weaker versions here would only mean a change to the ledger contract has to be made twice.
    """

    LEDGER = "Facility Asset Movement Ledger"

    def _make_building(self, name):
        if not frappe.db.exists("Building", name):
            frappe.get_doc({
                "doctype": "Building",
                "building_name": name,
            }).insert(ignore_permissions=True, ignore_mandatory=True)
        return name

    def _make_asset(self, building):
        doc = frappe.get_doc({
            "doctype": "Facility Asset",
            "naming_series": "FAC-AST-.YYYY.-.####",
            "asset_name": "Ledger-QA-Asset",
            "asset_category": "Other",
            "building": building,
        }).insert(ignore_permissions=True, ignore_mandatory=True)
        return doc.name

    def _make_movement(self, asset, from_b, to_b):
        doc = frappe.get_doc({
            "doctype": "Facility Asset Movement",
            "naming_series": "FAM-.YYYY.-.####",
            "movement_date": "2026-06-01",
            "facility_asset": asset,
            "from_building": from_b,
            "to_building": to_b,
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        doc.submit()
        return doc

    def setUp(self):
        self.b1 = self._make_building("LEDGER-QA-A")
        self.b2 = self._make_building("LEDGER-QA-B")
        self.asset = self._make_asset(self.b1)

    def test_a_posted_row_cannot_be_edited(self):
        """Immutability is the whole reason the ledger is a separate record rather than a
        field on the asset. ``ignore_permissions=True`` is passed deliberately: the refusal
        must come from the ledger's own in_create/immutability guard and not from a DocPerm
        the caller happens to lack, so a bypass flag that silences it would fail here."""
        mv = self._make_movement(self.asset, self.b1, self.b2)
        rows = frappe.get_all(
            self.LEDGER,
            filters={"source_doctype": "Facility Asset Movement", "source_name": mv.name},
            fields=["name"],
        )
        self.assertEqual(len(rows), 1)

        led = frappe.get_doc(self.LEDGER, rows[0].name)
        led.to_location = "tampered"
        with self.assertRaises(frappe.PermissionError):
            led.save(ignore_permissions=True)

    def test_post_is_idempotent(self):
        from apex.habitat.asset_movement_engine import post_asset_movement

        mv = self._make_movement(self.asset, self.b1, self.b2)
        post_asset_movement(mv)
        rows = frappe.get_all(
            self.LEDGER,
            filters={
                "source_doctype": "Facility Asset Movement",
                "source_name": mv.name,
                "reversal_of": ["is", "not set"],
            },
        )
        self.assertEqual(len(rows), 1)


# --- merged from test_facility_asset_movement_reachability.py ---
MOVEMENT = "Facility Asset Movement"
LEDGER = "Facility Asset Movement Ledger"
WRITER_ROLES = ("System Manager", "Accommodation Manager", "Resident Supervisor")
_APP = str(Path(apex.__file__).resolve().parent)
_WORKSPACE_GLOB = os.path.join(_APP, "*", "workspace", "*", "*.json")
def _h_facility_asset_movement_reachability():
    return frappe.generate_hash(length=12).upper()
def _workspaces_linking(doctype):
    """title -> granted roles, for every shipped workspace with a DocType link to
    ``doctype``.

    File-level on purpose: a dead workspace link is a property of the shipped JSON, so it
    has to be catchable from the tree that writes it, not only from a migrated site.
    """
    found = {}
    for path in sorted(glob.glob(_WORKSPACE_GLOB)):
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if any(
            row.get("link_type") == "DocType" and row.get("link_to") == doctype
            for row in data.get("links") or []
        ):
            title = data.get("title") or data.get("name")
            found[title] = {row["role"] for row in data.get("roles") or [] if row.get("role")}
    return found
class TestFacilityAssetMovementReachability(FrappeTestCase):
    """The shipped creation route works for the role it is shipped for, and only for it."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        # Two estates: the supervisor is permitted on `b_in` only, so `b_out` exercises the
        # scope refusal with a doc that is otherwise perfectly valid.
        cls.b_in = cls._building()
        cls.b_out = cls._building()
        cls.room_from = cls._room(cls.b_in)
        cls.room_to = cls._room(cls.b_in)
        cls.room_out_from = cls._room(cls.b_out)
        cls.room_out_to = cls._room(cls.b_out)
        # Never submitted (its every create is refused), so it cannot drift between methods.
        cls.asset_out = cls._asset(cls.b_out, cls.room_out_from)

        cls.supervisor = make_scoped_supervisor(cls._user, cls.b_in, cls.addClassCleanup)
        cls.manager = cls._user("Accommodation Manager")
        # Finance Manager ships an explicit all-zero DocPerm row on this DocType: read and
        # report only. It is the persona for "holds a role on the record but may not write".
        cls.outsider = cls._user("Finance Manager")

    def setUp(self):
        # frappe.session.user is a PROCESS GLOBAL that the row rollback does not restore.
        # Pin it before and after every method so a refusal cannot leak a half-switched
        # session into the next test.
        frappe.set_user("Administrator")
        self.addCleanup(frappe.set_user, "Administrator")
        # Minted per METHOD: on_submit rewrites this asset's building/location/movement_count
        # and the class-scoped rollback would not undo that between sibling methods.
        self.asset_in = self._asset(self.b_in, self.room_from)

    @classmethod
    def _building(cls):
        doc = frappe.get_doc({"doctype": "Building", "building_name": "REACH-" + _h_facility_asset_movement_reachability()})
        doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        return doc.name

    @classmethod
    def _room(cls, building):
        doc = frappe.get_doc(
            {"doctype": "Room", "building": building, "room_number": "REACH-R-" + _h_facility_asset_movement_reachability()}
        )
        doc.insert(ignore_permissions=True, ignore_mandatory=True)
        return doc.name

    @classmethod
    def _asset(cls, building, room):
        doc = frappe.get_doc(
            {
                "doctype": "Facility Asset",
                "naming_series": "FAC-AST-.YYYY.-.####",
                "asset_name": "REACH Asset " + _h_facility_asset_movement_reachability(),
                "asset_category": "Other",
                "building": building,
                # Data field carrying a Room name; _reconcile_origin resolves from_room
                # from it, so the movement's origin must match what is seeded here.
                "location_in_building": room,
                "responsible_supervisor": "Administrator",
            }
        )
        doc.insert(ignore_permissions=True, ignore_mandatory=True)
        return doc.name

    @classmethod
    def _user(cls, role):
        email = "reach-{0}@example.com".format(_h_facility_asset_movement_reachability()).lower()
        frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": "Reach",
                "send_welcome_email": 0,
                "roles": [{"role": role}],
            }
        ).insert(ignore_permissions=True)
        cls.addClassCleanup(frappe.delete_doc, "User", email, force=True, ignore_permissions=True)
        return email

    def _payload(self, asset, from_building, from_room, to_building, to_room):
        """A movement that is VALID on every non-permission axis, so a refusal can only
        be the permission gate: the origin matches the asset and the destination differs."""
        return {
            "doctype": MOVEMENT,
            "movement_date": today(),
            "facility_asset": asset,
            "movement_category": "Same-Company Relocation",
            "from_building": from_building,
            "from_room": from_room,
            "to_building": to_building,
            "to_room": to_room,
        }

    def _in_scope_payload(self):
        return self._payload(self.asset_in, self.b_in, self.room_from, self.b_in, self.room_to)

    def _out_of_scope_payload(self):
        return self._payload(
            self.asset_out, self.b_out, self.room_out_from, self.b_out, self.room_out_to
        )

    def _create_as(self, user, payload):
        """Insert through the REAL permission path (no ignore_permissions) as ``user``."""
        with as_user(user):
            return frappe.get_doc(payload).insert()

    # ---- clause 0: the shipped route exists and a role behind it can use it ----

    def test_workspace_link_is_backed_by_a_role_that_can_create(self):
        """A workspace link to a DocType nobody on that workspace can create is a dead
        end: the list view opens and its primary Add action never renders.

        RED before this change: Custody and Safety both linked the DocType and neither
        granted a single role holding ``create``, because no role held it at all.
        """
        linking = _workspaces_linking(MOVEMENT)
        self.assertTrue(
            linking,
            "no shipped workspace links %s at all — the record would be unreachable "
            "even with perfect DocPerms" % MOVEMENT,
        )

        meta = frappe.get_meta(MOVEMENT)
        creators = {p.role for p in meta.permissions if not p.permlevel and p.create}
        self.assertTrue(
            creators,
            "%s grants `create` to NO role on this site, so its every surface is a dead "
            "end. Shipped DocPerms: %s"
            % (MOVEMENT, sorted({p.role for p in meta.permissions})),
        )

        for title, roles in sorted(linking.items()):
            self.assertTrue(
                roles & creators,
                "workspace %r links %s but grants no role that can create it "
                "(workspace roles=%s, creator roles=%s)"
                % (title, MOVEMENT, sorted(roles), sorted(creators)),
            )

        # The creator set is the controller's own three permlevel-0 writers, and the two
        # read-only personas must never drift into it.
        self.assertEqual(
            creators,
            set(WRITER_ROLES),
            "the roles that may CREATE a movement must stay exactly the permlevel-0 "
            "writers; Finance Manager and Internal Auditor are read-only here by design",
        )

    # ---- clauses 1 + 2: allowed and refused, asserted as one non-collapsing pair ----

    def test_in_scope_create_allowed_and_out_of_scope_refused(self):
        """The authorised in-scope supervisor CAN create; the SAME supervisor CANNOT
        create between two estates they hold no User Permission for.

        Both verdicts are produced in one method and asserted to DIFFER. That is the
        point: in the state shipped before this change (``create`` absent for every role)
        both sides refused, so a refusal-only test was green while the feature was unusable.
        """
        allowed_doc = self._create_as(self.supervisor, self._in_scope_payload())
        self.assertTrue(allowed_doc.name, "in-scope supervisor must get a named draft")
        self.assertEqual(allowed_doc.docstatus, 0)
        # Prove it reached the database rather than only the in-memory document, and that
        # authorship is recorded against the real operator.
        self.assertTrue(frappe.db.exists(MOVEMENT, allowed_doc.name))
        self.assertEqual(
            frappe.db.get_value(MOVEMENT, allowed_doc.name, "owner"), self.supervisor
        )

        before = frappe.db.count(MOVEMENT)
        # frappe.PermissionError by NAME. A link or mandatory failure raises
        # ValidationError instead, and check_permission("create") runs at
        # document.py:300 — before run_before_save_methods — so a validation error
        # cannot stand in for the permission refusal being asserted here.
        with self.assertRaises(frappe.PermissionError):
            self._create_as(self.supervisor, self._out_of_scope_payload())
        self.assertEqual(
            frappe.db.count(MOVEMENT),
            before,
            "a refused create must not leave a row behind",
        )

        # The anti-collapse clause: the two verdicts must be different values.
        in_scope_verdict = frappe.has_permission(
            MOVEMENT,
            "create",
            doc=frappe.get_doc(self._in_scope_payload()),
            user=self.supervisor,
            throw=False,
        )
        out_of_scope_verdict = frappe.has_permission(
            MOVEMENT,
            "create",
            doc=frappe.get_doc(self._out_of_scope_payload()),
            user=self.supervisor,
            throw=False,
        )
        self.assertTrue(in_scope_verdict, "in-scope supervisor must be permitted to create")
        self.assertFalse(out_of_scope_verdict, "out-of-estate create must be refused")
        self.assertNotEqual(
            bool(in_scope_verdict),
            bool(out_of_scope_verdict),
            "allowed and refused collapsed to the same verdict — the pair proves nothing",
        )

    def test_unauthorized_role_refused(self):
        """A second, independent refusal axis: Finance Manager is IN scope everywhere (an
        unscoped oversight role, so the building hook defers) yet still cannot create,
        because its DocPerm row is read/report only. This keeps a refusal proof alive even
        if the scope hook is ever changed."""
        before = frappe.db.count(MOVEMENT)
        with self.assertRaises(frappe.PermissionError):
            self._create_as(self.outsider, self._in_scope_payload())
        self.assertEqual(frappe.db.count(MOVEMENT), before)

        # ...and the refusal is the DocPerm, not the scope hook: the hook defers (None),
        # which frappe reads as "no opinion" (has_controller_permissions, permissions.py:456).
        self.assertIsNone(
            P.building_scoped_has_permission(
                frappe.get_doc(self._in_scope_payload()), "create", user=self.outsider
            ),
            "Finance Manager is an unscoped role, so the building hook must defer — "
            "proving the refusal above came from the read-only DocPerm",
        )

    # ---- clause 3: submission posts EXACTLY ONE ledger effect ----

    def test_submit_posts_exactly_one_ledger_effect(self):
        """Count the ledger before and after. "A row exists" is also true of a double
        post, and the engine carries an idempotency key precisely because a double post
        was possible."""
        movement = self._create_as(self.supervisor, self._in_scope_payload())

        # The supervisor initiates but may not submit — submission is the manager's gate.
        self.assertFalse(
            frappe.has_permission(
                MOVEMENT, "submit", doc=movement, user=self.supervisor, throw=False
            ),
            "Resident Supervisor holds no submit DocPerm; the maker/checker split is the "
            "reason the manager submits below",
        )

        total_before = frappe.db.count(LEDGER)
        source_before = frappe.db.count(
            LEDGER, {"source_doctype": MOVEMENT, "source_name": movement.name}
        )
        self.assertEqual(source_before, 0, "a draft must post nothing")

        with as_user(self.manager):
            frappe.get_doc(MOVEMENT, movement.name).submit()

        self.assertEqual(
            frappe.db.count(LEDGER) - total_before,
            1,
            "submission must post EXACTLY one ledger row app-wide, not zero and not two",
        )
        rows = frappe.get_all(
            LEDGER,
            filters={"source_doctype": MOVEMENT, "source_name": movement.name},
            fields=["name", "from_building", "to_building", "reversal_of", "is_cancelled"],
        )
        self.assertEqual(len(rows), 1, "exactly one ledger row for this source")
        self.assertEqual(rows[0].from_building, self.b_in)
        self.assertEqual(rows[0].to_building, self.b_in)
        self.assertFalse(rows[0].reversal_of, "the posting row is an original, not a reversal")
        self.assertFalse(rows[0].is_cancelled)

    # ---- clause 4: cancellation preserves the audit trail ----

    def test_cancel_preserves_the_audit_trail(self):
        """Assert what SURVIVES the cancellation, not that ``cancel()`` returned.

        The original ledger row must still be there, unedited, alongside exactly one
        negated reversal; the movement document itself must survive as docstatus 2 with
        its reason and its original creator intact.
        """
        movement = self._create_as(self.supervisor, self._in_scope_payload())
        with as_user(self.manager):
            frappe.get_doc(MOVEMENT, movement.name).submit()

        posted = frappe.get_all(
            LEDGER,
            filters={"source_doctype": MOVEMENT, "source_name": movement.name},
            fields=["name", "from_building", "to_building", "from_location", "to_location"],
        )
        self.assertEqual(len(posted), 1)
        original = posted[0]
        total_before = frappe.db.count(LEDGER)

        # cancellation_reason is allow_on_submit, but a save() after submit would re-run
        # validate() -> _reconcile_origin against an asset that has ALREADY moved, which
        # throws. db_set is the shipped pattern for landing it (see the sibling effects
        # test), and the subject here is cancellation, not the reason's own write path.
        frappe.db.set_value(
            MOVEMENT, movement.name, "cancellation_reason", "Reachability audit-trail check"
        )
        with as_user(self.manager):
            frappe.get_doc(MOVEMENT, movement.name).cancel()

        # 1. The source document survives — cancelled, not deleted, reason retained, and
        #    still attributed to the supervisor who initiated it.
        self.assertTrue(
            frappe.db.exists(MOVEMENT, movement.name),
            "cancellation must not delete the movement — the record IS the audit trail",
        )
        survivor = frappe.db.get_value(
            MOVEMENT,
            movement.name,
            ["docstatus", "cancellation_reason", "owner", "from_building", "to_building"],
            as_dict=True,
        )
        self.assertEqual(survivor.docstatus, 2)
        self.assertEqual(survivor.cancellation_reason, "Reachability audit-trail check")
        self.assertEqual(
            survivor.owner,
            self.supervisor,
            "the initiating supervisor must remain recorded as the creator after cancel",
        )
        self.assertEqual(survivor.from_building, self.b_in)
        self.assertEqual(survivor.to_building, self.b_in)

        # 2. The ORIGINAL ledger row survives field-for-field — the reversal is a NEW row,
        #    never an edit of the posting it reverses.
        self.assertTrue(frappe.db.exists(LEDGER, original.name))
        kept = frappe.db.get_value(
            LEDGER,
            original.name,
            [
                "from_building",
                "to_building",
                "from_location",
                "to_location",
                "is_cancelled",
                "reversal_of",
            ],
            as_dict=True,
        )
        self.assertEqual(kept.from_building, original.from_building)
        self.assertEqual(kept.to_building, original.to_building)
        self.assertEqual(kept.from_location, original.from_location)
        self.assertEqual(kept.to_location, original.to_location)
        self.assertFalse(kept.is_cancelled, "the original posting must not be restamped")
        self.assertFalse(kept.reversal_of, "the original posting must not become a reversal")

        # 3. Exactly one reversal was added, and it points back at the original.
        self.assertEqual(
            frappe.db.count(LEDGER) - total_before,
            1,
            "cancellation must post EXACTLY one reversal row",
        )
        reversals = frappe.get_all(
            LEDGER,
            filters={
                "source_doctype": MOVEMENT,
                "source_name": movement.name,
                "reversal_of": ["is", "set"],
            },
            fields=["name", "reversal_of", "is_cancelled", "from_building", "to_building"],
        )
        self.assertEqual(len(reversals), 1)
        self.assertEqual(reversals[0].reversal_of, original.name)
        self.assertTrue(reversals[0].is_cancelled)
