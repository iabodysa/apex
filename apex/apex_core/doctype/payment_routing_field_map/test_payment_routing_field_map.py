# Copyright (c) 2026, AFMCO and contributors
"""Tests for the Payment Routing Field Map child row.

The child carries no standalone logic; it is exercised in its real parent
context — the Payment Routing Settings single's ``field_map`` table — via an ORM
round-trip that proves each mapping column persists and reads back, and that the
parent's guards see the rows: static/source integrity, and that both fieldnames
actually exist on the target and the source. Requires a live site.

Fixtures name REAL fields on both sides on purpose. The target here is the router's
unconfigured default, the native Payment Request, so a fieldname is checked against
that DocType — mapping something it does not have is the negative case below, not
the fixture."""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

SETTINGS = "Payment Routing Settings"


class TestPaymentRoutingFieldMap(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        settings = frappe.get_single(SETTINGS)
        # The parent is deployment config, so snapshot it and restore on teardown:
        # this test owns only the field_map rows and must leave the rest untouched.
        self._target = settings.target_payment_doctype
        self._auto_submit = settings.auto_submit_target
        # Snapshot the WHOLE row rather than a hand-picked field list, which would
        # silently stop restoring any column added to the child later.
        self._rows = [
            row.as_dict(no_default_fields=True, no_child_table_fields=True)
            for row in settings.field_map
        ]
        # _validate_links runs BEFORE validate (document.py _save), so a stale target
        # Link — another test's throwaway DocType, already deleted — would abort every
        # save here and mask the parent guard behind a LinkValidationError (itself a
        # ValidationError). Clear it so the field map is what is actually under test.
        if self._target and not frappe.db.exists("DocType", self._target):
            self._target = None
            # A map only means anything against the target it was written for, so the
            # rows go with it: restoring stub fieldnames against the default Payment
            # Request would be refused by the parent's existence guard.
            self._rows = []
        # Register the restore BEFORE the first mutating save: if this very save
        # throws, an un-registered cleanup would leave the Single wiped for good.
        self.addCleanup(self._restore_settings)
        settings.target_payment_doctype = None
        # Clear the incoming rows in the SAME save. They were written for whatever
        # target was configured, and this save re-points the router at the default —
        # leaving them would validate another module's fieldnames against Payment
        # Request and abort here, far from the module that actually left them.
        settings.set("field_map", [])
        settings.save(ignore_permissions=True)

    def _restore_settings(self):
        settings = frappe.get_single(SETTINGS)
        settings.set("field_map", self._rows)
        settings.target_payment_doctype = self._target
        settings.auto_submit_target = self._auto_submit
        settings.save(ignore_permissions=True)

    def test_field_map_rows_round_trip(self):
        """Round-trip against the router's own default target, the native Payment
        Request, using fields that exist on both sides.

        The previous fixture mapped ``remarks`` — not a Payment Request field — from
        ``employee`` — not a Salis Payment Request field. Both halves were dropped in
        silence, so the row this test "proved" persisted described a payment that
        would have been created with no party and no remark at all.
        """
        settings = frappe.get_single(SETTINGS)
        settings.set("field_map", [])
        # A non-static row copies from a source field ...
        settings.append(
            "field_map",
            {"target_fieldname": "party", "source_fieldname": "supplier", "is_static": 0},
        )
        # ... a static row carries a literal value (and no source).
        settings.append(
            "field_map",
            {"target_fieldname": "subject", "is_static": 1, "static_value": "Routed by Apex"},
        )
        settings.save(ignore_permissions=True)

        reloaded = frappe.get_single(SETTINGS)
        rows = {r.target_fieldname: r for r in reloaded.field_map}
        self.assertIn("party", rows)
        self.assertEqual(rows["party"].source_fieldname, "supplier")
        self.assertEqual(rows["party"].is_static, 0)
        self.assertEqual(rows["subject"].is_static, 1)
        self.assertEqual(rows["subject"].static_value, "Routed by Apex")

    def test_a_row_naming_a_field_neither_side_has_is_refused(self):
        """The old fixture's own values, kept as the negative case.

        A valid pair must save first, or a refusal proves nothing. Then each half is
        spoiled in turn: ``remarks`` does not exist on the target and would be dropped
        at insert; ``employee`` does not exist on the source and would be read as
        None, writing the target field blank.
        """
        settings = frappe.get_single(SETTINGS)
        settings.set(
            "field_map", [{"target_fieldname": "party", "source_fieldname": "supplier"}]
        )
        settings.save(ignore_permissions=True)

        settings = frappe.get_single(SETTINGS)
        settings.set(
            "field_map", [{"target_fieldname": "remarks", "source_fieldname": "supplier"}]
        )
        with self.assertRaises(frappe.exceptions.ValidationError) as cm:
            settings.save(ignore_permissions=True)
        self.assertIn("remarks", str(cm.exception))

        settings = frappe.get_single(SETTINGS)
        settings.set(
            "field_map", [{"target_fieldname": "party", "source_fieldname": "employee"}]
        )
        with self.assertRaises(frappe.exceptions.ValidationError) as cm:
            settings.save(ignore_permissions=True)
        self.assertIn("employee", str(cm.exception))

    def test_static_row_with_a_source_field_is_rejected_by_parent(self):
        settings = frappe.get_single(SETTINGS)
        settings.set("field_map", [])
        # Both fieldnames are real, so the existence guards pass and the static/source
        # integrity guard is provably the one that fires.
        settings.append(
            "field_map",
            {"target_fieldname": "party", "source_fieldname": "supplier", "is_static": 1},
        )
        with self.assertRaises(frappe.exceptions.ValidationError) as cm:
            settings.save(ignore_permissions=True)
        self.assertIn("Static row", str(cm.exception))
