# Copyright (c) 2026, AFMCO and contributors
"""Migrate-safety guard for the Salis composite UNIQUE indexes.

``on_doctype_update`` runs inside ``bench migrate``. A raw ``frappe.db.add_unique``
there propagates MariaDB error 1062 the moment the table already holds duplicate
rows for the constraint columns, and the WHOLE migrate aborts on an existing
site. Each controller must therefore route through
``apex_core.utils.ledger_index.add_unique_guarded``, which rolls back, logs the
blocking duplicate groups and returns False so migrate continues.

One table-driven test rather than a near-copy per doctype directory: these
controllers are identical in shape, so a per-directory duplicate would add no
coverage. ``GUARDED`` must list EVERY Salis controller with an
``on_doctype_update`` — the machine-written ledgers/snapshots and the
human-written masters alike, since duplicate rows abort migrate regardless of
who wrote them. Add a row when another Salis DocType takes a composite UNIQUE
index.

A table-driven test grades only the rows it lists, so the table has to prove its
own completeness or a half-covered subject reports green: this one listed two of
four controllers while every assertion passed.
``test_guarded_lists_every_salis_on_doctype_update`` closes that by globbing
``salis/**/*.py``, keeping the files that declare the hook, and asserting that
set equals ``GUARDED``'s. It is deliberately keyed on DECLARING THE HOOK, not on
taking a UNIQUE index: the hook is the seam that can abort migrate, and it is
what the rest of this module actually calls.

It does NOT reach outside ``salis/`` — a Habitat or Apex Core controller taking
the same hook needs its own guard — and it cannot tell a correct constraint from
a wrong one, only that some row exists for the module.

Pure unit test — the DDL is mocked, so it needs no site and no live table.
"""

from __future__ import annotations

import ast
import glob
import os
import unittest
from unittest import mock
from pathlib import Path

import apex
from apex.apex_core.utils import ledger_index
from apex.salis.doctype.fuel_consumption_ledger import fuel_consumption_ledger
from apex.salis.doctype.fuel_quota import fuel_quota
from apex.salis.doctype.rental_accrual_ledger import rental_accrual_ledger
from apex.salis.doctype.transport_trip_rating import transport_trip_rating
from apex.salis.doctype.vehicle_utilisation_snapshot import vehicle_utilisation_snapshot

# (controller module, DocType, constraint columns, constraint name)
GUARDED = [
    (
        fuel_consumption_ledger,
        "Fuel Consumption Ledger",
        ["source_type", "source_name"],
        "unique_fcl_source",
    ),
    (
        fuel_quota,
        "Fuel Quota",
        ["vehicle", "period_month", "docstatus"],
        "uq_fuel_quota_vehicle_period",
    ),
    (
        rental_accrual_ledger,
        "Rental Accrual Ledger",
        ["vehicle", "accrual_date"],
        "unique_ral_vehicle_date",
    ),
    (
        transport_trip_rating,
        "Transport Trip Rating",
        ["employee", "dispatch_trip"],
        "unique_ttr_employee_trip",
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


HOOK = "on_doctype_update"
SALIS_ROOT = os.path.join(str(Path(apex.__file__).resolve().parent), "salis")


def _source(module):
    with open(module.__file__, encoding="utf-8") as fh:
        return fh.read()


def _declares_hook(path):
    """True when the file defines ``on_doctype_update`` anywhere.

    Anywhere, not just at module level: a controller that declares it as a METHOD
    is silently never called by Frappe, and pulling it in here means the author
    is told to add a row and then told by the module-level assertion why the row
    fails — instead of the file staying invisible to both.
    """
    with open(path, encoding="utf-8") as fh:
        try:
            tree = ast.parse(fh.read(), filename=path)
        except SyntaxError:
            return False
    return any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == HOOK
        for node in ast.walk(tree)
    )


def salis_modules_declaring_hook():
    """Absolute paths of every non-test ``salis/**/*.py`` that declares the hook."""
    return {
        os.path.realpath(path)
        for path in glob.glob(os.path.join(SALIS_ROOT, "**", "*.py"), recursive=True)
        if not os.path.basename(path).startswith("test_")
        and _declares_hook(path)
    }


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
                    # Nothing is rolled back. frappe.db.add_unique commits before it
                    # runs its own ALTER TABLE (frappe/database/mariadb/database.py:447),
                    # so the caller's work is committed and its savepoints released
                    # before this except can be reached: a bare rollback would undo
                    # nothing while resetting the caller's commit hooks, and a scoped
                    # one would raise 1305 SAVEPOINT ... does not exist and abort the
                    # migrate this guard exists to survive.
                    mf.db.rollback.assert_not_called()
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

    def test_guarded_lists_every_salis_on_doctype_update(self):
        """The table must cover its whole subject, or a green run means nothing.

        Every assertion above iterates GUARDED, so a controller left out of the
        table is not weakly covered — it is not covered at all, while the suite
        still reports green. This is the only assertion that can see that.
        """
        on_disk = salis_modules_declaring_hook()
        listed = {os.path.realpath(module.__file__) for module, *_rest in GUARDED}
        missing = sorted(os.path.relpath(p, SALIS_ROOT) for p in on_disk - listed)
        extra = sorted(os.path.relpath(p, SALIS_ROOT) for p in listed - on_disk)
        self.assertEqual(
            ([], []),
            (missing, extra),
            f"GUARDED must list every salis controller declaring {HOOK}. Missing a row "
            f"means nothing checks that controller routes through add_unique_guarded "
            f"rather than a raw frappe.db.add_unique — which is the call that aborts "
            f"migrate on a duplicate-data site: {missing}. Listed but no longer "
            f"declaring the hook (drop the row): {extra}.",
        )

    def test_the_completeness_scan_is_not_silently_empty(self):
        """Guard-of-the-guard: an empty scan would make the check above vacuous.

        ``salis_modules_declaring_hook`` returning nothing — a moved SALIS_ROOT, a
        broken glob — turns the completeness assertion into ``[] == []``. Prove
        the root is really salis/ and that the scan finds this module's own
        subject before believing any equality it reports.
        """
        self.assertTrue(
            os.path.isdir(os.path.join(SALIS_ROOT, "doctype")),
            f"SALIS_ROOT is not the salis module: {SALIS_ROOT}",
        )
        found = salis_modules_declaring_hook()
        self.assertGreaterEqual(len(found), 4, "hook scan returned implausibly few files")
        self.assertIn(os.path.realpath(vehicle_utilisation_snapshot.__file__), found)


if __name__ == "__main__":
    unittest.main()
