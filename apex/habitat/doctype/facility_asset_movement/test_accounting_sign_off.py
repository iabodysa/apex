# Copyright (c) 2026, AFMCO and contributors
"""the accounting sign-off on an intercompany movement must be givable.

`accounting_acknowledged` had no `allow_on_submit`, so once a movement was submitted the
flag could never change — not by Accounting, not by anyone. The throw in
`_validate_intercompany_gates` demands it BEFORE submit for Intercompany Permanent only,
so a Permanent movement always carried it and every other intercompany movement could be
submitted without it and then never acquire it. That is why the pending-acknowledgement
Number Card only ever counted up: nothing could ever leave its filter.

The two fields now sit at permlevel 1 with write granted only to Finance Manager, both
carry `allow_on_submit`, and one whitelisted POST method sets them together so the record
says who signed rather than only that someone did.

The two refusals are the point, and they get a test each: a caller without the role, and
the movement's own submitter. A sign-off the submitter can give themselves records
nothing, so the desk being able to offer it is not the same as the control existing.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from apex.habitat.doctype.facility_asset_movement.facility_asset_movement import (
    acknowledge_intercompany_movement,
)

# The controller names no role. It gates on permlevel-1 WRITE access to the flag
# (facility_asset_movement.py:177), and the shipped DocType JSON gives that row to
# Finance Manager alone, so the role is read off the schema rather than a constant.
ACCOUNTING_ROLE = "Finance Manager"

ORIGIN_COMPANY = "_Test Company"
DESTINATION_COMPANY = "_Test Company 1"

TILE_FILTERS = [
    ["is_intercompany", "=", 1],
    ["accounting_acknowledged", "=", 0],
    ["docstatus", "=", 1],
]


def _h(n=12):
    return frappe.generate_hash(length=n).upper()


class TestTheAccountingSignOffCanBeGiven(FrappeTestCase):
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
                "doctype": "Facility Asset Movement",
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
                "Facility Asset Movement", doc.name, "owner", owner, update_modified=False
            )
        frappe.db.set_value(
            "Facility Asset Movement", doc.name, "docstatus", 1, update_modified=False
        )
        self.addCleanup(self._drop, doc.name)
        doc.reload()
        return doc

    def _drop(self, name):
        frappe.set_user("Administrator")
        frappe.db.set_value(
            "Facility Asset Movement", name, "docstatus", 0, update_modified=False
        )
        frappe.delete_doc(
            "Facility Asset Movement", name, force=True, ignore_permissions=True
        )

    def _tile_count(self):
        from frappe.client import get_count

        return int(get_count("Facility Asset Movement", filters=TILE_FILTERS))

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
        meta = frappe.get_meta("Facility Asset Movement")
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
