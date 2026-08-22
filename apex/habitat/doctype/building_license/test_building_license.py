# Copyright (c) 2026, afmcoltd
"""What Building License guarantees, asserted against the DocType itself.

Patterned on ``frappe/tests/test_document.py`` — the subject is ``validate``,
``before_cancel`` and the two whitelisted actions, ``renew`` and ``mark_revoked``, that
carry this regulatory record through its real lifecycle. ``validate`` refuses an expiry
that does not fall after the issue date, derives ``status`` from how close the expiry
is (Active / Expiring Soon / Expired), and stamps ``last_renewal_date`` only when the
expiry is pushed forward — never when it moves back. Once ``mark_revoked`` has set the
terminal ``Revoked`` state, ``before_cancel`` keeps it uncancellable and every future
save keeps re-deriving ``Revoked`` rather than a date-derived status.

Each case builds on a throwaway Building: this DocType shares one transaction across
its own test methods (`FrappeTestCase` rolls back once at class teardown), so reusing a
fixture building across cases would be an unearned assumption of isolation.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate, today

from apex.habitat.doctype.building_license.building_license import mark_revoked, renew

test_dependencies = ["Building"]


def _fresh_building():
    """A Building unique to the calling test, so its license never collides with one
    already standing on a shared fixture building."""
    building = frappe.copy_doc(frappe.get_test_records("Building")[0])
    building.building_name = f"_T-License Building {frappe.generate_hash(length=8)}"
    building.floor_plan = []
    building.insert()
    return building.name


def _new_license(**overrides):
    record = frappe.copy_doc(frappe.get_test_records("Building License")[0])
    record.building = _fresh_building()
    record.issue_date = add_days(today(), -30)
    record.expiry_date = add_days(today(), 400)
    record.renewal_lead_days = 30
    for field, value in overrides.items():
        record.set(field, value)
    return record


class TestBuildingLicense(FrappeTestCase):
    def test_an_expiry_date_not_after_the_issue_date_is_refused(self):
        """An expiry on or before the issue date describes a license valid for no time."""
        record = _new_license(expiry_date=add_days(today(), -30))

        with self.assertRaisesRegex(frappe.ValidationError, "Expiry Date must be after"):
            record.insert()

    def test_status_is_derived_from_how_close_the_expiry_is(self):
        """Active, Expiring Soon and Expired must each be reachable from their own dates."""
        far = _new_license(expiry_date=add_days(today(), 400), renewal_lead_days=30)
        far.insert()
        self.assertEqual(far.status, "Active")

        soon = _new_license(expiry_date=add_days(today(), 10), renewal_lead_days=30)
        soon.insert()
        self.assertEqual(soon.status, "Expiring Soon")

        past = _new_license(
            issue_date=add_days(today(), -400), expiry_date=add_days(today(), -1)
        )
        past.insert()
        self.assertEqual(past.status, "Expired")

    def test_pushing_the_expiry_forward_stamps_the_renewal_date_and_pulling_it_back_does_not(self):
        """A renewal is an expiry pushed forward; moving it back is an edit, not a renewal."""
        record = _new_license()
        record.insert()
        self.assertIsNone(record.last_renewal_date)

        record.expiry_date = add_days(record.expiry_date, 60)
        record.save()
        self.assertEqual(record.last_renewal_date, today())

        record.db_set("last_renewal_date", None)
        record.expiry_date = add_days(record.expiry_date, -30)
        record.save()
        self.assertIsNone(
            record.last_renewal_date,
            "pulling the expiry back must not be recorded as a renewal",
        )

    def test_a_revoked_license_cannot_be_cancelled_and_keeps_re_deriving_revoked(self):
        """The terminal state must survive both a cancel attempt and a later save."""
        record = _new_license()
        record.insert()
        record.submit()

        mark_revoked(record.name, "Expired paperwork found on inspection")
        record.reload()
        self.assertEqual(record.status, "Revoked")

        with self.assertRaisesRegex(frappe.ValidationError, "cannot be cancelled or reinstated"):
            record.cancel()

        record.reload()
        record.save()
        self.assertEqual(
            record.status,
            "Revoked",
            "a later save must not let the date-derived status overwrite Revoked",
        )

    def test_a_submitted_non_revoked_license_can_be_cancelled(self):
        """The cancel lock belongs to Revoked specifically, not to submission itself."""
        record = _new_license()
        record.insert()
        record.submit()

        record.cancel()

        self.assertEqual(record.docstatus, 2)

    def test_mark_revoked_is_refused_without_a_reason_on_a_draft_or_twice(self):
        """Every guard mark_revoked stands on: a reason, a submitted document, and only once."""
        draft = _new_license()
        draft.insert()

        with self.assertRaisesRegex(frappe.ValidationError, "Only submitted"):
            mark_revoked(draft.name, "reason")

        draft.submit()
        with self.assertRaisesRegex(frappe.ValidationError, "reason is required"):
            mark_revoked(draft.name, "   ")

        mark_revoked(draft.name, "First revocation")
        with self.assertRaisesRegex(frappe.ValidationError, "already revoked"):
            mark_revoked(draft.name, "Second attempt")

    def test_renew_is_refused_without_a_later_date_on_a_submitted_or_revoked_license(self):
        """Every guard renew stands on: a real forward date, a still-draft license, and not revoked."""
        record = _new_license()
        record.insert()

        with self.assertRaisesRegex(frappe.ValidationError, "Provide either"):
            renew(record.name)

        with self.assertRaisesRegex(frappe.ValidationError, "must be later"):
            renew(record.name, new_expiry_date=record.expiry_date)

        record.submit()
        with self.assertRaisesRegex(frappe.ValidationError, "This license is submitted"):
            renew(record.name, extend_days=30)

        mark_revoked(record.name, "Revoked before renewal attempt")
        with self.assertRaisesRegex(frappe.ValidationError, "cannot be renewed"):
            renew(record.name, extend_days=30)

    def test_renew_extends_the_expiry_and_stamps_the_renewal_date(self):
        """The acceptance case: a draft license's expiry moves forward and the renewal is dated."""
        record = _new_license()
        record.insert()
        original_expiry = getdate(record.expiry_date)

        renew(record.name, extend_days=30)

        reloaded = frappe.get_doc("Building License", record.name)
        self.assertEqual(reloaded.expiry_date, getdate(add_days(original_expiry, 30)))
        self.assertEqual(reloaded.last_renewal_date, getdate(today()))
