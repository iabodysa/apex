# Copyright (c) 2026, afmcoltd
"""What Apex Stock Settings guarantees, asserted against the DocType itself.

Patterned on frappe's own document-validation tests (``frappe/tests/test_document.py``,
``test_validate``). This is a Single — one standing row shared by the whole suite — so
every case that changes a value restores it with ``self.addCleanup`` before returning.

The real guarantee lives in the module-level ``validate_posting_allowed``, the write-path
gate the no-GL stock engine calls before any ledger row is written (its own docstring:
"a guard in the caller is a convention the next voucher type will not inherit"). Four
refusals in the order the operator can act on them: engine off, future-dated, frozen
period, closed store — pinned here against an acceptance that proves a fully-open policy
still lets a posting through.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from apex.apex_core.doctype.apex_stock_settings.apex_stock_settings import (
    validate_posting_allowed,
)

test_dependencies = ["Building"]


class TestApexStockSettings(FrappeTestCase):
    def setUp(self):
        self._original = frappe.db.get_singles_dict("Apex Stock Settings")
        self.addCleanup(self._restore_settings)

    def _restore_settings(self):
        for field, value in self._original.items():
            frappe.db.set_single_value("Apex Stock Settings", field, value)

    def test_a_posting_is_refused_while_the_engine_is_switched_off(self):
        """The engine's own off switch must stop every posting before any row is
        written, or turning the engine off gives a false sense that nothing more can
        land."""
        frappe.db.set_single_value("Apex Stock Settings", "enable_stock_engine", 0)

        with self.assertRaisesRegex(frappe.ValidationError, "switched off"):
            validate_posting_allowed("_Test Building")

    def test_a_future_dated_posting_is_refused(self):
        """A posting dated ahead of today would misstate every date-scoped balance
        report between now and then."""
        frappe.db.set_single_value("Apex Stock Settings", "enable_stock_engine", 1)

        with self.assertRaisesRegex(frappe.ValidationError, "cannot be dated in the future"):
            validate_posting_allowed("_Test Building", add_days(today(), 1))

    def test_a_posting_on_or_before_the_frozen_date_is_refused(self):
        """``get_store_balance`` carries no date predicate of its own; the freeze is
        the only thing that stops a backdated posting into an already-closed period
        from silently changing a balance that was already reported."""
        frappe.db.set_single_value("Apex Stock Settings", "enable_stock_engine", 1)
        frappe.db.set_single_value("Apex Stock Settings", "stock_frozen_upto", today())

        with self.assertRaisesRegex(frappe.ValidationError, "Stock is frozen up to"):
            validate_posting_allowed("_Test Building", today())

    def test_a_posting_to_a_closed_store_is_refused_when_required(self):
        """``require_active_store`` is the switch that makes the store's own
        ``is_procurement_store`` / ``store_is_active`` flags binding on every posting,
        not just advisory."""
        frappe.db.set_single_value("Apex Stock Settings", "enable_stock_engine", 1)
        frappe.db.set_single_value("Apex Stock Settings", "require_active_store", 1)
        frappe.db.set_value("Building", "_Test Building", "is_procurement_store", 0)
        self.addCleanup(
            frappe.db.set_value,
            "Building",
            "_Test Building",
            "is_procurement_store",
            frappe.db.get_value("Building", "_Test Building", "is_procurement_store"),
        )

        with self.assertRaisesRegex(frappe.ValidationError, "is closed"):
            validate_posting_allowed("_Test Building", today())

    def test_a_posting_that_satisfies_every_open_policy_is_accepted(self):
        """The acceptance counterpart to all four refusals above — a fully permissive
        policy, an in-window date, and no store requirement must let a posting through
        without raising."""
        frappe.db.set_single_value("Apex Stock Settings", "enable_stock_engine", 1)
        frappe.db.set_single_value("Apex Stock Settings", "stock_frozen_upto", None)
        frappe.db.set_single_value("Apex Stock Settings", "require_active_store", 0)

        validate_posting_allowed("_Test Building", today())
