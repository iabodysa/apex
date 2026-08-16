# Copyright (c) 2026, AFMCO and contributors
"""The Finance Manager permlevel-1 rows, and the one DocType that also holds permlevel 0.

Five Habitat DocTypes -- Custody Damage Assessment, Housing Checkout, Maintenance
Request, Subcontractor Service Contract, Subcontractor Service Order -- give
``Finance Manager`` a permlevel-1 read+write row. Four of them still ship no
permlevel-0 row at all. Two readings of that shape were possible:

LAYERED  the row is a deliberate FIELD unlock over a document some OTHER role opens.
FLAT     the row is inert, because a role with no permlevel-0 row cannot open the doc.

LAYERED is correct as a matter of framework mechanics: document access reads
permlevel-0 rows only, while field access is a separate computation that unions
every permlevel a user's roles hold. A permlevel-1 row is therefore live for any
user holding that role PLUS a role that opens the document, and never a duplicate
of a permlevel-0 row.

CUSTODY DAMAGE ASSESSMENT IS THE EXCEPTION -- it ALSO carries a permlevel-0
``read`` row for Finance Manager, granted over three stated costs: the shipped role
profile already pairs Finance Manager with Internal Auditor, who holds the read, so only
a hand-assembled solo finance user lacks it; the permlevel-1 row unlocks exactly one
field while a level-0 read is the WHOLE record, resident identity included; and Finance
Manager is unscoped, so the read spans every building. The other four keep the
overlay-only shape.

MAINTENANCE REQUEST IS A SECOND EXCEPTION: it ships an ``All`` permlevel-0 row
(read+create, if_owner), and every logged-in user holds ``All``. A Finance-Manager-only
user therefore CAN create one and populate the financial fields on it. On that DocType
the flat "inert" reading is false outright, with no layering involved.

WHY THIS ASKS THE FRAMEWORK RATHER THAN THE FILE. The previous version replayed
frappe's own permission algorithms (``is_perm_applicable``, ``get_permlevel_access``,
``apply_fieldlevel_read_permissions``) by hand against the shipped JSON. A hand-written
replay can drift from the algorithm it mirrors and pass for the wrong reason. This
version asks ``frappe.has_permission`` and ``frappe.model.get_permitted_fields``
directly, for a real user holding each role combination -- the same two calls the desk
and the REST API make, and the same question a Finance Manager actually meets.
"""

from __future__ import annotations

import frappe
from frappe.model import get_permitted_fields
from frappe.tests.utils import FrappeTestCase

from apex.tests._helpers import _user

FINANCE = "Finance Manager"
GRANTED = "Custody Damage Assessment"

# The five DocTypes that carry the Finance Manager permlevel-1 row, and the
# non-display fields each overlay unlocks.
OVERLAY = {
    "Custody Damage Assessment": ("total_estimated_replacement_cost",),
    "Housing Checkout": ("cost_center", "damage_deduction_amount", "additional_salary_deduction"),
    "Maintenance Request": ("cost_of_repair", "cost_center"),
    "Subcontractor Service Contract": ("rate_per_visit", "monthly_retainer"),
    "Subcontractor Service Order": ("service_cost",),
}

# The three that stay flat at document level: Maintenance Request opens through its
# ``All`` row, Custody Damage Assessment through its own permlevel-0 read grant.
DOCUMENT_LEVEL_FLAT = tuple(d for d in OVERLAY if d not in ("Maintenance Request", GRANTED))

# Fields the Custody Damage Assessment read newly puts in front of Finance Manager --
# named so the cost of that grant is asserted, not just described.
RESIDENT_IDENTITY = ("party_type", "party", "employee")


def _role_user(email, role):
    return _user(email, role)


def _multi_role_user(email, *roles):
    """A user idempotently created and holding every role in ``roles``.

    ``_user`` (apex.tests._helpers) grants one role; this layers the rest onto the
    same account so a "Finance Manager who also opens the document" test exercises
    one real user, not two roles asserted separately.
    """
    user = _user(email, roles[0])
    missing = set(roles[1:]) - set(frappe.get_roles(user))
    if missing:
        frappe.get_doc("User", user).add_roles(*missing)
    return user


class TestFinanceManagerOverlayIsLayeredNotFlat(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.finance_only = _role_user("finance_overlay_solo@example.com", FINANCE)
        cls.finance_plus_accommodation = _multi_role_user(
            "finance_overlay_layered@example.com", FINANCE, "Accommodation Manager"
        )
        cls.accommodation_manager_only = _role_user(
            "finance_overlay_opener_am@example.com", "Accommodation Manager"
        )
        cls.system_manager_only = _role_user(
            "finance_overlay_opener_sm@example.com", "System Manager"
        )

    def test_a_solo_finance_manager_cannot_open_three_of_the_five(self):
        for doctype in DOCUMENT_LEVEL_FLAT:
            with self.subTest(doctype=doctype):
                for ptype in ("read", "write", "create"):
                    self.assertFalse(
                        frappe.has_permission(doctype, ptype, user=self.finance_only),
                        f"{doctype}: a solo Finance Manager gained document {ptype}",
                    )

    def test_the_overlay_field_is_still_write_permitted_for_the_solo_user(self):
        """The grant exists at field level even while document access is nil -- which is
        exactly why it is NOT inert: it activates the moment the user is also given an
        opener role, with no DocPerm edit anywhere."""
        for doctype, fields in OVERLAY.items():
            with self.subTest(doctype=doctype):
                writable = get_permitted_fields(
                    doctype, user=self.finance_only, permission_type="write"
                )
                for fieldname in fields:
                    self.assertIn(
                        fieldname, writable,
                        f"{doctype}: {fieldname} is no longer write-permitted for a "
                        "solo Finance Manager",
                    )

    def test_layering_an_opener_role_makes_document_write_live_and_keeps_the_field(self):
        for doctype in OVERLAY:
            with self.subTest(doctype=doctype):
                self.assertTrue(
                    frappe.has_permission(
                        doctype, "write", user=self.finance_plus_accommodation
                    ),
                    f"{doctype}: layering Accommodation Manager did not open document write",
                )
                writable = get_permitted_fields(
                    doctype, user=self.finance_plus_accommodation, permission_type="write"
                )
                for fieldname in OVERLAY[doctype]:
                    self.assertIn(fieldname, writable)

    def test_the_openers_already_hold_both_levels_without_finance(self):
        """System Manager and Accommodation Manager open these documents AND hold their
        own permlevel-1 rows already -- re-granting at level 1 what they hold at level 0
        is only meaningful to an author who knew the two levels are independent, so the
        Finance Manager row omitting level 0 is a choice, not an oversight."""
        for doctype in OVERLAY:
            for opener in (self.accommodation_manager_only, self.system_manager_only):
                with self.subTest(doctype=doctype, opener=opener):
                    self.assertTrue(frappe.has_permission(doctype, "write", user=opener))
                    writable = get_permitted_fields(
                        doctype, user=opener, permission_type="write"
                    )
                    for fieldname in OVERLAY[doctype]:
                        self.assertIn(fieldname, writable)


class TestCustodyDamageAssessmentIsTheGrantedException(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.finance_only = _role_user(
            "finance_overlay_custody_solo@example.com", FINANCE
        )
        # A bystander who opens nothing and holds no accounting role: the guard-of-the-guard
        # that shows the read is Finance Manager's, not something every logged-in user has.
        cls.bystander = _role_user(
            "finance_overlay_custody_bystander@example.com", "Employee"
        )

    def test_a_solo_finance_manager_opens_the_record_and_reads_the_resident(self):
        self.assertTrue(
            frappe.has_permission(GRANTED, "read", user=self.finance_only),
            "the permlevel-0 read grant is gone -- a Finance Manager holding no other "
            "role can no longer open this record",
        )
        readable = get_permitted_fields(
            GRANTED, user=self.finance_only, permission_type="read"
        )
        for fieldname in RESIDENT_IDENTITY:
            with self.subTest(field=fieldname):
                self.assertIn(
                    fieldname, readable,
                    f"{fieldname} no longer reaches Finance Manager on the granted read",
                )

    def test_a_bystander_with_no_accounting_role_still_cannot(self):
        self.assertFalse(
            frappe.has_permission(GRANTED, "read", user=self.bystander),
            "a role with no grant on this DocType must not be able to read it -- if this "
            "passes, the read above proves nothing about Finance Manager specifically",
        )

    def test_the_grant_covers_exactly_read_and_report(self):
        for ptype in ("write", "create", "submit", "cancel", "delete", "export", "share"):
            with self.subTest(ptype=ptype):
                self.assertFalse(
                    frappe.has_permission(GRANTED, ptype, user=self.finance_only),
                    f"the grant widened to {ptype}",
                )
        self.assertTrue(frappe.has_permission(GRANTED, "report", user=self.finance_only))


class TestMaintenanceRequestIsTheOtherException(FrappeTestCase):
    """Maintenance Request ships an ``All`` permlevel-0 row (read+create, if_owner).
    Every logged-in user holds ``All``, so a Finance-Manager-only user reaches
    permlevel-0 ``create`` with no layering at all, and their permlevel-1 write then
    keeps the cost fields on the draft they just created."""

    DOCTYPE = "Maintenance Request"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.finance_only = _role_user(
            "finance_overlay_mr_solo@example.com", FINANCE
        )
        cls.bystander = _role_user(
            "finance_overlay_mr_bystander@example.com", "Employee"
        )

    def test_the_all_row_lets_even_a_bystander_create_but_not_write_or_submit(self):
        for ptype, expected in (("create", True), ("write", False), ("submit", False)):
            with self.subTest(ptype=ptype):
                self.assertEqual(
                    frappe.has_permission(self.DOCTYPE, ptype, user=self.bystander),
                    expected,
                    f"the All row's shape changed for {ptype}",
                )

    def test_solo_finance_manager_can_create_but_not_edit(self):
        self.assertTrue(frappe.has_permission(self.DOCTYPE, "create", user=self.finance_only))
        self.assertFalse(frappe.has_permission(self.DOCTYPE, "write", user=self.finance_only))
        self.assertFalse(frappe.has_permission(self.DOCTYPE, "submit", user=self.finance_only))

    def test_and_the_money_fields_stick_on_that_created_draft(self):
        """reset_values_if_no_permlevel_access resets only fields whose permlevel is NOT
        in the user's write set. Permlevel 1 IS in it, purely from holding Finance
        Manager -- independent of the document-level write the All row withholds."""
        writable = get_permitted_fields(
            self.DOCTYPE, user=self.finance_only, permission_type="write"
        )
        for fieldname in OVERLAY[self.DOCTYPE]:
            with self.subTest(field=fieldname):
                self.assertIn(fieldname, writable)
