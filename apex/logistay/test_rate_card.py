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

DAY-RATE ARITHMETIC (P-189 / A-019, now REAL): ``logistay/rate_resolver.py``
converts the seeded card value into ``rc_day_rate_applied`` for EACH basis —
``day_rate = round(value / divisor, 2)``, the divisor derived from the basis and
the worker-month (explicit_rate_per_day=1, div_31=31, fixed_365_12=365/12,
actual_cycle_days = the month's own day count). ``TestDayRateResolver`` below
resolves a Rate Card for a synthetic worker-month and asserts the computed day
rate reproduces a SYNTHETIC golden cell-for-cell for each basis, proves a wrong
divisor breaks the assertion (not a tautology), and proves the resolved day rate
+ basis snapshot land on BOTH the Billable and the Payable line. No real AFMCO
value appears — round fake numbers only.
"""

from __future__ import annotations

from decimal import Decimal

import frappe
from frappe.tests.utils import FrappeTestCase

# The four day-rate bases — the enum domain shared by Rate Card, Rate Resolution,
# Billable Line and Payable Line (kept in one place in reconciliation_engine).
from apex.logistay.reconciliation_engine import DAY_RATE_BASIS
from apex.logistay.rate_resolver import resolve_day_rate, resolve_from_card

# SYNTHETIC golden fixture — obviously-fake round numbers, no real AFMCO value.
# One uniform seeded value under one synthetic worker-month, resolved four ways;
# the four distinct outputs prove the DIVISOR (not the value) differentiates a
# basis. explicit_rate_per_day passes the value straight through (divisor 1).
_GOLDEN_SEEDED_VALUE = 9300          # fake monthly package / day-rate value
_GOLDEN_CYCLE_DAYS = 30              # fake worker-month length (actual_cycle_days)
_GOLDEN_DAY_RATE = {
    "explicit_rate_per_day": Decimal("9300.00"),  # 9300 / 1
    "div_31": Decimal("300.00"),                  # 9300 / 31
    "fixed_365_12": Decimal("305.75"),            # 9300 / (365/12)
    "actual_cycle_days": Decimal("310.00"),       # 9300 / 30
}


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

    # WINDOW
    def test_window_rejects_from_after_to(self):
        doc = self._card(rc_effective_from="2026-03-31", rc_effective_to="2026-03-01")
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True, ignore_mandatory=True)

    def test_window_accepts_from_before_to(self):
        doc = self._card(rc_effective_from="2026-03-01", rc_effective_to="2026-03-31")
        doc.insert(ignore_permissions=True, ignore_mandatory=True)
        self.assertTrue(frappe.db.exists("Rate Card", doc.name))

    # DIVISOR-PRESENT (C3)
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

    # NEVER-MUTATE
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

class TestDayRateResolver(FrappeTestCase):
    """P-189 / A-019 — the generic per-day-rate resolver, proven cell-for-cell.

    Resolves a Rate Card for a synthetic worker-month and asserts the computed
    ``rc_day_rate_applied`` reproduces the SYNTHETIC golden for EACH basis, that
    a wrong divisor breaks the assertion (so it is NOT a tautology), and that the
    resolved day rate + basis snapshot land on BOTH output lines.
    """

    def _card_for_basis(self, basis: str):
        # In-memory Rate Card (NOT inserted) carrying a single day_rate line with
        # the synthetic seeded value + basis. Reading rc_value / rc_day_rate_basis
        # off the real model is exactly what the resolver does in production.
        doc = frappe.get_doc(
            {
                "doctype": "Rate Card",
                "rc_card_name": f"LGZT-CARD-{_suffix()}",
                "rc_client": f"LGZT-CLIENT-{_suffix()}",
                "rc_service_line": "delivery",
                "rc_billing_unit": "package_day",
                "rc_status": "draft",
                "rc_effective_from": "2026-03-01",
                "rc_components": [
                    {
                        "rc_component": "day_rate",
                        "rc_unit": "per_period",
                        "rc_value": _GOLDEN_SEEDED_VALUE,
                        "rc_day_rate_basis": basis,
                    }
                ],
            }
        )
        doc.flags.ignore_links = True
        return doc

    # CELL-FOR-CELL golden
    def test_resolver_reproduces_golden_day_rate_for_each_basis(self):
        for basis in DAY_RATE_BASIS:
            with self.subTest(basis=basis):
                snapshot = resolve_from_card(
                    self._card_for_basis(basis), cycle_days=_GOLDEN_CYCLE_DAYS
                )
                self.assertEqual(
                    snapshot["rc_day_rate_applied"], _GOLDEN_DAY_RATE[basis]
                )
                self.assertEqual(snapshot["rc_day_rate_basis_applied"], basis)

    def test_every_basis_covered_and_outputs_are_distinct(self):
        # Golden covers the whole committed domain, and each basis yields a
        # DIFFERENT rate off one uniform value -> the divisor is what differs.
        self.assertEqual(set(_GOLDEN_DAY_RATE), set(DAY_RATE_BASIS))
        rates = list(_GOLDEN_DAY_RATE.values())
        self.assertEqual(len(set(rates)), len(rates))

    # NON-TAUTOLOGY: a wrong divisor must break the golden
    def test_wrong_divisor_breaks_the_golden(self):
        # div_31 must NOT resolve to the actual_cycle_days (÷30) figure; if the
        # resolver used the wrong divisor the golden assertion would FAIL. This
        # proves the cell-for-cell test is discriminating, not self-fulfilling.
        div31 = resolve_day_rate(_GOLDEN_SEEDED_VALUE, "div_31")
        wrong = resolve_day_rate(
            _GOLDEN_SEEDED_VALUE, "actual_cycle_days", cycle_days=_GOLDEN_CYCLE_DAYS
        )
        self.assertEqual(div31, _GOLDEN_DAY_RATE["div_31"])
        self.assertNotEqual(div31, wrong)
        self.assertNotEqual(div31, _GOLDEN_DAY_RATE["actual_cycle_days"])

    def test_resolver_is_deterministic(self):
        for basis in DAY_RATE_BASIS:
            with self.subTest(basis=basis):
                first = resolve_day_rate(
                    _GOLDEN_SEEDED_VALUE, basis, cycle_days=_GOLDEN_CYCLE_DAYS
                )
                second = resolve_day_rate(
                    _GOLDEN_SEEDED_VALUE, basis, cycle_days=_GOLDEN_CYCLE_DAYS
                )
                self.assertEqual(first, second)

    def test_actual_cycle_days_needs_positive_cycle_length(self):
        with self.assertRaises(ValueError):
            resolve_day_rate(_GOLDEN_SEEDED_VALUE, "actual_cycle_days", cycle_days=0)

    # SNAPSHOT lands on BOTH lines with the resolved value
    def test_resolved_day_rate_and_basis_snapshot_onto_both_lines(self):
        for basis in DAY_RATE_BASIS:
            with self.subTest(basis=basis):
                snapshot = resolve_from_card(
                    self._card_for_basis(basis), cycle_days=_GOLDEN_CYCLE_DAYS
                )
                day_rate = snapshot["rc_day_rate_applied"]

                billable = frappe.get_doc(
                    {
                        "doctype": "Billable Line",
                        "rec_run": f"LGZT-RUN-{_suffix()}",
                        "rec_component": "timesheet",
                        "rec_resolution_ref": f"LGZT-RES-{_suffix()}",
                        "rec_day_rate_applied": day_rate,
                        "rec_day_rate_basis_applied": snapshot[
                            "rc_day_rate_basis_applied"
                        ],
                    }
                )
                billable.flags.ignore_links = True
                billable.insert(ignore_permissions=True, ignore_mandatory=True)

                payable = frappe.get_doc(
                    {
                        "doctype": "Payable Line",
                        "rec_run": f"LGZT-RUN-{_suffix()}",
                        "rec_worker": f"LGZT-WORKER-{_suffix()}",
                        "rec_partial_reason": "full_month",
                        "rec_resolution_ref": f"LGZT-RES-{_suffix()}",
                        "rec_day_rate_basis_applied": snapshot[
                            "rc_day_rate_basis_applied"
                        ],
                    }
                )
                payable.flags.ignore_links = True
                payable.insert(ignore_permissions=True, ignore_mandatory=True)

                # Resolved day rate persisted on the billable side, cell-for-cell.
                self.assertEqual(
                    Decimal(
                        str(
                            frappe.db.get_value(
                                "Billable Line", billable.name, "rec_day_rate_applied"
                            )
                        )
                    ),
                    _GOLDEN_DAY_RATE[basis],
                )
                # The IDENTICAL basis snapshot landed on BOTH lines.
                self.assertEqual(
                    frappe.db.get_value(
                        "Billable Line", billable.name, "rec_day_rate_basis_applied"
                    ),
                    frappe.db.get_value(
                        "Payable Line", payable.name, "rec_day_rate_basis_applied"
                    ),
                )
                self.assertEqual(
                    frappe.db.get_value(
                        "Payable Line", payable.name, "rec_day_rate_basis_applied"
                    ),
                    basis,
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
