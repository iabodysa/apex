# Copyright (c) 2026, AFMCO and contributors
"""P-040 regression: Trip Fulfilment Ledger single-write immutability.

The ledger is a machine-written audit memo: one row is inserted per completed
Dispatch Trip and never re-saved (reversal deletes the row, it does not edit it).
``_enforce_single_write_immutability`` lets the initial insert (``is_new``)
through but blocks any later save of a persisted row, so a posted fulfilment
record cannot be silently altered after the fact.

The DocType is NOT submittable (no docstatus gate), so immutability lives in
validate(); the on_cancel deletion in the Dispatch Trip controller uses
delete_doc (which does not run validate) so it is unaffected by this guard.

Run with:
    bench --site <site> run-tests --app apex_habitat \
        --module apex_habitat.salis.doctype.trip_fulfilment_ledger.test_trip_fulfilment_ledger
"""

from __future__ import annotations

import unittest

import frappe


class TestTripFulfilmentLedgerImmutability(unittest.TestCase):
    def test_not_submittable(self):
        """Confirms the design premise: immutability is enforced in validate(),
        not via a docstatus gate."""
        self.assertFalse(
            frappe.get_meta("Trip Fulfilment Ledger").is_submittable,
            "Ledger must stay non-submittable; immutability is a validate() guard.",
        )

    def test_new_row_passes(self):
        """A brand-new (unsaved) row is allowed through so the controller can post it."""
        doc = frappe.new_doc("Trip Fulfilment Ledger")
        doc.worker_count = 5
        # Must not raise — is_new() is True.
        doc._enforce_single_write_immutability()

    def test_resave_of_persisted_row_throws(self):
        """Insert a row, then attempt to save it again → blocked."""
        frappe.set_user("Administrator")
        doc = frappe.new_doc("Trip Fulfilment Ledger")
        doc.worker_count = 5
        doc.source_doctype = "Dispatch Trip"
        # Bypass Link validation: this test exercises the immutability guard, not
        # the link targets, which need no real Dispatch Trip / vehicle / driver.
        doc.flags.ignore_links = True
        doc.insert(ignore_permissions=True)
        try:
            doc.worker_count = 99
            # The guard throws frappe.PermissionError (NOT a ValidationError
            # subclass), so the assertion must name PermissionError exactly.
            with self.assertRaises(frappe.PermissionError):
                doc.save(ignore_permissions=True)
        finally:
            frappe.delete_doc(
                "Trip Fulfilment Ledger",
                doc.name,
                ignore_permissions=True,
                force=True,
            )

    def tearDown(self):
        frappe.set_user("Administrator")
