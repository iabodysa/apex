# Copyright (c) 2026, AFMCO and contributors
"""Bed-occupancy indexes are DECLARED, not only patched (A-113).

A Frappe patch never reaches a freshly installed site: a fresh install marks
every registered patch complete WITHOUT running it. Any index delivered by a
patch alone therefore exists on upgraded sites and is missing on new ones.

``housing_assignment.on_doctype_update`` is the fix — the same shape
``accommodation_stock_ledger`` already uses. Frappe calls a DocType module's
``on_doctype_update`` during app sync (fresh install) AND on every ``bench
migrate`` (existing site), so both populations end up with the index. The legacy
``v0_7.add_bed_assignment_index`` patch stays registered for already-deployed
sites, and uses the SAME index names, so a migrated site recognises its indexes
as already present instead of growing duplicates under new names.

These tests prove causation, not coincidence: the index is DROPPED, shown to be
absent, then re-created by calling ``on_doctype_update()`` — exactly what a fresh
install does. A ``finally`` block re-declares the index whatever happens, so the
DDL (which MariaDB commits implicitly and the suite rollback cannot undo) always
lands back in its original state.

Run standalone:
    bench --site <site> run-tests \
        --module apex.habitat.doctype.housing_assignment.test_housing_assignment_bed_index
"""

from __future__ import annotations

import inspect
import os

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.apex_core.utils.ledger_index import _index_exists, add_index_guarded
from apex.habitat.doctype.accommodation_stock_ledger import accommodation_stock_ledger
from apex.habitat.doctype.housing_assignment import housing_assignment

DOCTYPE = "Housing Assignment"
BED_INDEX = "idx_asgn_bed"
ACTIVE_INDEX = "idx_asgn_bed_active"
LEGACY_PATCH = "apex.patches.v0_7.add_bed_assignment_index"


def _index_columns(doctype, index_name):
    """The ordered column list of one index, straight out of MariaDB."""
    rows = frappe.db.sql(
        f"SHOW INDEX FROM `tab{doctype}` WHERE Key_name = %s",
        (index_name,),
        as_dict=True,
    )
    return [row["Column_name"] for row in sorted(rows, key=lambda r: r["Seq_in_index"])]


def _indexes_covering(doctype, columns):
    """Every index name whose ordered column list equals ``columns``.

    Assert on THIS, not on an index name, wherever the framework may already
    have built an equivalent index of its own. ``bed`` is a Link carrying
    ``search_index: 1``, so Frappe creates its own single-column index (named
    ``bed`` at table creation, ``bed_index`` on a later alter). Since A-129 the
    guarded helper recognises that equivalence and declines to add a duplicate
    under our name, so ``idx_asgn_bed`` is present on some sites and absent on
    others while the invariant the query planner needs — bed is indexed — holds
    on both. A test that pinned the name would fail on exactly the sites where
    the deduplication worked.
    """
    rows = frappe.db.sql(f"SHOW INDEX FROM `tab{doctype}`", as_dict=True)
    grouped = {}
    for row in rows:
        grouped.setdefault(row["Key_name"], []).append(row)
    return {
        name
        for name, index_rows in grouped.items()
        if [r["Column_name"] for r in sorted(index_rows, key=lambda r: r["Seq_in_index"])]
        == list(columns)
    }


class TestHousingAssignmentBedIndexDeclaration(FrappeTestCase):
    def test_on_doctype_update_is_a_module_level_hook(self):
        """Frappe's sync/migrate calls the DocType module's MODULE-LEVEL
        ``on_doctype_update`` — a method on the controller class is never
        invoked, so the declaration only reaches a fresh install in this shape."""
        hook = getattr(housing_assignment, "on_doctype_update", None)
        self.assertTrue(callable(hook), "housing_assignment declares no on_doctype_update")
        self.assertTrue(inspect.isfunction(hook), "on_doctype_update must be a module-level function")
        self.assertEqual(hook.__module__, housing_assignment.__name__)

    def test_it_mirrors_the_accommodation_stock_ledger_declaration(self):
        """Same fix, same effect: the sibling ledger's declaration also puts its
        index on the table. Asserted by running it and inspecting the database,
        not by reading either module's source."""
        sibling = getattr(accommodation_stock_ledger, "on_doctype_update", None)
        self.assertTrue(callable(sibling), "the mirrored ASL declaration disappeared")
        sibling()
        self.assertTrue(
            _index_exists("Accommodation Stock Ledger", "idx_asl_cancel_type_emp"),
            "the mirrored declaration must produce its index too",
        )

    def test_both_bed_indexes_are_declared_and_shaped_correctly(self):
        """The state a freshly synced site must end up in."""
        housing_assignment.on_doctype_update()
        self.assertTrue(
            _indexes_covering(DOCTYPE, ["bed"]),
            "no index covers the bed column alone — the occupancy lookup would "
            "table-scan whether or not our own index name is the one present",
        )
        self.assertTrue(_index_exists(DOCTYPE, ACTIVE_INDEX))
        self.assertEqual(
            _index_columns(DOCTYPE, ACTIVE_INDEX),
            ["bed", "docstatus", "check_out_date"],
            "the composite index must serve the active-occupancy lookup "
            '({"bed": ..., "docstatus": 1, "check_out_date": ["is", "not set"]})',
        )

    def _rebuild(self, index_name, fields):
        add_index_guarded(DOCTYPE, fields, index_name)

    def _prove_declaration_recreates(self, index_name, fields):
        """Drop every index over these columns, prove none remain, then let the
        declaration put coverage back.

        This is what makes the test causal: without the drop, a green would only
        show that SOME earlier migrate had created the index, which is exactly the
        upgraded-site case A-113 is NOT about.

        Every equivalent index goes, not just ours — leaving the framework's own
        ``bed`` search index in place would make the declaration a legitimate
        no-op (A-129) and the test would prove nothing. The rebuild registered
        first restores coverage under our name, which is the same invariant, not
        necessarily the same index name the site started with.
        """
        # Make sure coverage is there to drop (and register the rebuild first, so
        # the column is indexed again even if an assertion below fails).
        housing_assignment.on_doctype_update()
        self.addCleanup(self._rebuild, index_name, fields)
        for existing in _indexes_covering(DOCTYPE, fields):
            frappe.db.sql(f"ALTER TABLE `tab{DOCTYPE}` DROP INDEX `{existing}`")
        self.assertEqual(
            _indexes_covering(DOCTYPE, fields),
            set(),
            f"no index over {fields} should remain — this is the fresh-install "
            "starting state",
        )

        housing_assignment.on_doctype_update()

        self.assertIn(
            index_name,
            _indexes_covering(DOCTYPE, fields),
            f"on_doctype_update must create {index_name} on a site where nothing "
            f"else indexes {fields}",
        )
        self.assertEqual(_index_columns(DOCTYPE, index_name), fields)

    def test_a_site_without_the_bed_index_gets_it_from_the_declaration(self):
        self._prove_declaration_recreates(BED_INDEX, ["bed"])

    def test_a_site_without_the_active_index_gets_it_from_the_declaration(self):
        self._prove_declaration_recreates(
            ACTIVE_INDEX, ["bed", "docstatus", "check_out_date"]
        )

    def test_re_declaring_on_an_existing_site_is_an_idempotent_no_op(self):
        """``on_doctype_update`` runs on EVERY migrate. A site that already has
        the indexes must not grow a second copy under the same or a new name."""
        housing_assignment.on_doctype_update()
        before = {
            row["Key_name"]
            for row in frappe.db.sql(f"SHOW INDEX FROM `tab{DOCTYPE}`", as_dict=True)
        }
        housing_assignment.on_doctype_update()
        housing_assignment.on_doctype_update()
        after = {
            row["Key_name"]
            for row in frappe.db.sql(f"SHOW INDEX FROM `tab{DOCTYPE}`", as_dict=True)
        }
        self.assertEqual(after, before, "repeated declaration must add no new index")
        self.assertTrue(
            _indexes_covering(DOCTYPE, ["bed"]),
            "the bed column must stay indexed under some name across re-declaration",
        )
        self.assertIn(ACTIVE_INDEX, after)

    def test_the_legacy_patch_stays_registered_for_deployed_sites(self):
        """The declaration does not replace the patch: an already-deployed site
        that has run the patch keeps it in its completed list, and the patch must
        stay registered so a site mid-upgrade still gets the index."""
        app_root = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..")
        )
        patch_path = os.path.join(
            app_root, "patches", "v0_7", "add_bed_assignment_index.py"
        )
        self.assertTrue(os.path.exists(patch_path), "the legacy bed-index patch was removed")

        with open(os.path.join(app_root, "patches.txt"), encoding="utf-8") as fh:
            registered = fh.read()
        self.assertIn(LEGACY_PATCH, registered, "the legacy bed-index patch was unregistered")

        # Assert what the patch DOES, not what its source says. The earlier version
        # searched the file text for the two index names; when the patch was made to
        # delegate to the controller declaration — removing the duplicated call pair
        # the copy-paste guard rejected — the names left the file and this test went
        # red on a refactor that improved the very property it exists to protect.
        from unittest import mock

        from apex.apex_core.utils import ledger_index
        from apex.patches.v0_7 import add_bed_assignment_index

        with mock.patch.object(
            ledger_index, "add_index_guarded", return_value=True
        ) as add_index:
            add_bed_assignment_index.execute()

        declared = {call.args[2] for call in add_index.call_args_list}
        for index_name in (BED_INDEX, ACTIVE_INDEX):
            with self.subTest(index=index_name):
                self.assertIn(
                    index_name,
                    declared,
                    "the patch must use the SAME index name as the declaration, or a "
                    "migrated site would end up with two indexes for one access path",
                )
