# Copyright (c) 2026, AFMCO and contributors
"""P-189 acceptance tests — Rate Card price book + Rate Resolution snapshot.

The Rate Card engine is an effective-dated, never-mutate, versioned price book.
Its three committed invariants (``rate_card.py``) are proven here cell-for-cell
against SYNTHETIC golden fixtures — obviously-fake round numbers, no real AFMCO
rate, client, or IBAN value anywhere:

* WINDOW            — effective_from must not fall after effective_to.
* DIVISOR-PRESENT C3 — a day-rate line on a package-day / attendance-day card
  MUST name its own day-rate basis (there is NO flat divisor default).
* NEVER-MUTATE      — an active/superseded card is immutable; the sole legal
  write is the single active -> superseded transition with no smuggled change.

Rate Resolution is the append-only pricing log; its immutability + on_trash
block are proven. The day-rate BASIS snapshot is proven to persist onto BOTH the
Billable Line and the Payable Line for EACH of the four bases (the pairing key
the P-190 BASIS-CONSISTENT guard later compares).

GAP (reported, NOT worked around): there is NO committed resolver that computes
the per-day rate from a monthly/period package for each basis (actual_cycle_days
/ fixed_365_12 / div_31 / explicit_rate_per_day). ``rc_day_rate_applied`` is
documented "computed at runtime from the seeded card value" and no function in
``logistay/`` performs that arithmetic. Asserting a golden day-rate cell-for-cell
would test a non-existent function (a tautology against a test-local formula), so
it is deliberately left as an owner-evidence / integrator step. Only the four
committed invariants + the basis snapshot are asserted here. See the
``test_day_rate_arithmetic_is_a_documented_gap`` marker below.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

# The four day-rate bases — the enum domain shared by Rate Card, Rate Resolution,
# Billable Line and Payable Line (kept in one place in reconciliation_engine).
from apex.logistay.reconciliation_engine import DAY_RATE_BASIS


def _suffix() -> str:
    # >=12-char hash so synthetic fixture names never collide across parallel runs.
    return frappe.generate_hash(length=12)


class TestRateCardInvariants(FrappeTestCase):
    """The three committed Rate Card guards, each proven to FIRE and to PASS."""

    def _card(self, **overrides):
        name = f"LGZT-CARD-{_suffix()}"
        doc = frappe.get_doc(
            {
                "doctype": "Rate Card",
                "rc_card_name": name,
                "rc_client": f"LGZT-CLIENT-{_suffix()}",  # link value; existence not needed
                "rc_service_line": "delivery",
                "rc_billing_unit": "package_day",
                "rc_status": "draft",
                "rc_effective_from": "2026-03-01",
                **overrides,
            }
        )
        doc.flags.ignore_links = True  # isolate the guards from the Client master cascade
        return doc

    # --- WINDOW ------------------------------------------------------------- #
    def test_window_rejects_from_after_to(self):
        doc = self._card(rc_effective_from="2026-03-31", rc_effective_to="2026-03-01")
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True, ignore_mandatory=True)

    def test_window_accepts_from_before_to(self):
        doc = self._card(rc_effective_from="2026-03-01", rc_effective_to="2026-03-31")
        doc.insert(ignore_permissions=True, ignore_mandatory=True)
        self.assertTrue(frappe.db.exists("Rate Card", doc.name))

    # --- DIVISOR-PRESENT (C3) ---------------------------------------------- #
    def test_divisor_present_blocks_day_rate_line_without_basis(self):
        # package_day card + a day_rate line with NO basis -> C3 halts the save.
        doc = self._card(
            rc_billing_unit="package_day",
            rc_components=[{"rc_component": "day_rate", "rc_unit": "per_day"}],
        )
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True, ignore_mandatory=True)

    def test_divisor_present_accepts_day_rate_line_with_basis(self):
        doc = self._card(
            rc_billing_unit="package_day",
            rc_components=[
                {"rc_component": "day_rate", "rc_unit": "per_day", "rc_day_rate_basis": "div_31"}
            ],
        )
        doc.insert(ignore_permissions=True, ignore_mandatory=True)
        self.assertTrue(frappe.db.exists("Rate Card", doc.name))

    def test_divisor_present_ignored_on_non_divisor_unit(self):
        # A shift_hour card is not a divisor unit -> a basis-less day_rate line is fine.
        doc = self._card(
            rc_billing_unit="shift_hour",
            rc_components=[{"rc_component": "day_rate", "rc_unit": "per_hour"}],
        )
        doc.insert(ignore_permissions=True, ignore_mandatory=True)
        self.assertTrue(frappe.db.exists("Rate Card", doc.name))

    # --- NEVER-MUTATE ------------------------------------------------------- #
    def test_active_card_cannot_be_edited(self):
        doc = self._card(rc_status="active")
        doc.insert(ignore_permissions=True, ignore_mandatory=True)
        reloaded = frappe.get_doc("Rate Card", doc.name)
        reloaded.flags.ignore_links = True
        reloaded.rc_service_line = "cleaning"  # any non-status field
        with self.assertRaises(frappe.ValidationError):
            reloaded.save(ignore_permissions=True)

    def test_active_to_superseded_status_only_is_allowed(self):
        doc = self._card(rc_status="active")
        doc.insert(ignore_permissions=True, ignore_mandatory=True)
        reloaded = frappe.get_doc("Rate Card", doc.name)
        reloaded.flags.ignore_links = True
        reloaded.rc_status = "superseded"  # the SOLE legal write
        reloaded.save(ignore_permissions=True)
        self.assertEqual(frappe.db.get_value("Rate Card", doc.name, "rc_status"), "superseded")

    def test_superseding_may_not_smuggle_another_change(self):
        doc = self._card(rc_status="active")
        doc.insert(ignore_permissions=True, ignore_mandatory=True)
        reloaded = frappe.get_doc("Rate Card", doc.name)
        reloaded.flags.ignore_links = True
        reloaded.rc_status = "superseded"
        reloaded.rc_service_line = "security"  # smuggled alongside the transition
        with self.assertRaises(frappe.ValidationError):
            reloaded.save(ignore_permissions=True)

    def test_day_rate_arithmetic_is_a_documented_gap(self):
        # There is NO committed function that converts a package value to a day
        # rate per basis, so the golden per-basis arithmetic cannot be asserted
        # against the engine without adding source (out of scope). This marker
        # keeps the gap visible; only the enum DOMAIN is a committed fact.
        self.assertEqual(
            DAY_RATE_BASIS,
            ("actual_cycle_days", "fixed_365_12", "div_31", "explicit_rate_per_day"),
        )


class TestRateResolutionAppendOnly(FrappeTestCase):
    """Rate Resolution is an append-only pricing log: no edit, no delete."""

    def _resolution(self, **overrides):
        doc = frappe.get_doc(
            {
                "doctype": "Rate Resolution",
                "rc_resolved_card": f"LGZT-CARD-{_suffix()}",  # link value; existence not needed
                "rc_resolved_version": 1,
                "rc_day_rate_applied": 100,  # synthetic round placeholder, never asserted
                "rc_day_rate_basis_applied": "div_31",
                **overrides,
            }
        )
        doc.flags.ignore_links = True  # isolate the append-only rule from master cascade
        return doc

    def test_new_resolution_saves(self):
        doc = self._resolution()
        doc.insert(ignore_permissions=True, ignore_mandatory=True)
        self.assertTrue(frappe.db.exists("Rate Resolution", doc.name))

    def test_existing_resolution_cannot_be_edited(self):
        doc = self._resolution()
        doc.insert(ignore_permissions=True, ignore_mandatory=True)
        reloaded = frappe.get_doc("Rate Resolution", doc.name)
        reloaded.flags.ignore_links = True
        reloaded.rc_day_rate_applied = 999
        with self.assertRaises(frappe.ValidationError):
            reloaded.save(ignore_permissions=True)

    def test_resolution_cannot_be_deleted(self):
        doc = self._resolution()
        doc.insert(ignore_permissions=True, ignore_mandatory=True)
        with self.assertRaises(frappe.ValidationError):
            frappe.delete_doc("Rate Resolution", doc.name, ignore_permissions=True)


class TestBasisSnapshotOntoLines(FrappeTestCase):
    """The day-rate BASIS is snapshotted onto BOTH output lines for EVERY basis.

    Uses ignore_links so the snapshot persistence is isolated from the Worker /
    Reconciliation Run / Rate Resolution master cascade — the guard that later
    compares these snapshots is proven separately in test_reconciliation.py.
    """

    def test_billable_line_snapshots_each_basis(self):
        for basis in DAY_RATE_BASIS:
            with self.subTest(basis=basis):
                line = frappe.get_doc(
                    {
                        "doctype": "Billable Line",
                        "rec_run": f"LGZT-RUN-{_suffix()}",
                        "rec_component": "timesheet",
                        "rec_resolution_ref": f"LGZT-RES-{_suffix()}",
                        "rec_day_rate_basis_applied": basis,
                    }
                )
                line.flags.ignore_links = True
                line.insert(ignore_permissions=True, ignore_mandatory=True)
                self.assertEqual(
                    frappe.db.get_value("Billable Line", line.name, "rec_day_rate_basis_applied"),
                    basis,
                )

    def test_payable_line_snapshots_each_basis(self):
        for basis in DAY_RATE_BASIS:
            with self.subTest(basis=basis):
                line = frappe.get_doc(
                    {
                        "doctype": "Payable Line",
                        "rec_run": f"LGZT-RUN-{_suffix()}",
                        "rec_worker": f"LGZT-WORKER-{_suffix()}",
                        "rec_partial_reason": "full_month",
                        "rec_resolution_ref": f"LGZT-RES-{_suffix()}",
                        "rec_day_rate_basis_applied": basis,
                    }
                )
                line.flags.ignore_links = True
                line.insert(ignore_permissions=True, ignore_mandatory=True)
                self.assertEqual(
                    frappe.db.get_value("Payable Line", line.name, "rec_day_rate_basis_applied"),
                    basis,
                )


if __name__ == "__main__":
    import unittest

    unittest.main()
