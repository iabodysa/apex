# Copyright (c) 2026, AFMCO and contributors
"""Migrate-safety guard for the Salis machine-written ledgers' UNIQUE indexes.

``on_doctype_update`` runs inside ``bench migrate``. A raw ``frappe.db.add_unique``
there propagates MariaDB error 1062 the moment the table already holds duplicate
rows for the constraint columns, and the WHOLE migrate aborts on an existing
site. Each controller must therefore route through
``apex_core.utils.ledger_index.add_unique_guarded``, which rolls back, logs the
blocking duplicate groups and returns False so migrate continues.

One table-driven test rather than a near-copy per doctype directory: these
controllers are identical in shape, so a per-directory duplicate would add no
coverage. Add a row to ``GUARDED`` when another machine-written Salis ledger
takes a composite UNIQUE index.

Pure unit test — the DDL is mocked, so it needs no site and no live table.
"""

from __future__ import annotations

import unittest
from unittest import mock

from apex.apex_core.utils import ledger_index
from apex.salis.doctype.rental_accrual_ledger import rental_accrual_ledger
from apex.salis.doctype.vehicle_utilisation_snapshot import vehicle_utilisation_snapshot

# (controller module, DocType, constraint columns, constraint name)
GUARDED = [
    (
        rental_accrual_ledger,
        "Rental Accrual Ledger",
        ["vehicle", "accrual_date"],
        "unique_ral_vehicle_date",
    ),
    (
        vehicle_utilisation_snapshot,
        "Vehicle Utilisation Snapshot",
        ["vehicle", "snapshot_date"],
        "unique_vus_vehicle_date",
    ),
]

# The exact shape MariaDB raises when the target columns already hold duplicates.
DUPLICATE_ENTRY = (
    "(1062, \"Duplicate entry 'VEH-0001-2026-06-20' for key 'uq_probe'\")"
)


def _source(module):
    with open(module.__file__, encoding="utf-8") as fh:
        return fh.read()


class TestSalisLedgerMigrateGuard(unittest.TestCase):
    def test_no_controller_calls_raw_add_unique(self):
        """The raw call is the one that aborts migrate, so it must be absent."""
        for module, doctype, _cols, _constraint in GUARDED:
            with self.subTest(doctype=doctype):
                src = _source(module)
                self.assertNotIn(
                    "frappe.db.add_unique",
                    src,
                    f"{doctype} still calls raw frappe.db.add_unique; a duplicate-data "
                    f"site would abort bench migrate here",
                )
                self.assertIn(
                    "add_unique_guarded",
                    src,
                    f"{doctype} must route its UNIQUE index through add_unique_guarded",
                )

    def test_on_doctype_update_survives_duplicate_entry_ddl_error(self):
        """Duplicate-entry from the DDL is swallowed, logged, and never propagated.

        The failure is injected at the lowest possible seam — ``frappe.db.add_unique``
        inside ledger_index — so this exercises the controller's real call path, not a
        stand-in. ``on_doctype_update`` must return normally: an exception escaping
        here aborts the entire migrate.
        """
        for module, doctype, cols, constraint in GUARDED:
            with self.subTest(doctype=doctype):
                with mock.patch.object(ledger_index, "_constraint_exists", return_value=False), \
                     mock.patch.object(ledger_index, "_log_blocking_duplicates") as logged, \
                     mock.patch.object(ledger_index, "frappe") as mf:
                    mf.db.add_unique.side_effect = Exception(DUPLICATE_ENTRY)

                    module.on_doctype_update()  # must not raise

                    mf.db.add_unique.assert_called_once_with(
                        doctype, cols, constraint_name=constraint
                    )
                    mf.db.rollback.assert_called_once()
                    logged.assert_called_once_with(doctype, cols, constraint)

    def test_on_doctype_update_creates_the_expected_constraint_when_clean(self):
        """On a clean table the guard still issues the intended DDL, unchanged."""
        for module, doctype, cols, constraint in GUARDED:
            with self.subTest(doctype=doctype):
                with mock.patch.object(
                    ledger_index, "_constraint_exists", side_effect=[False, True]
                ), mock.patch.object(ledger_index, "frappe") as mf:
                    module.on_doctype_update()
                    mf.db.add_unique.assert_called_once_with(
                        doctype, cols, constraint_name=constraint
                    )
                    mf.db.rollback.assert_not_called()

    def test_on_doctype_update_is_a_module_level_function(self):
        """Frappe only calls a MODULE-level on_doctype_update; a method is never run."""
        for module, doctype, _cols, _constraint in GUARDED:
            with self.subTest(doctype=doctype):
                hook = getattr(module, "on_doctype_update", None)
                self.assertTrue(
                    callable(hook), f"{doctype} declares no on_doctype_update"
                )


if __name__ == "__main__":
    unittest.main()
