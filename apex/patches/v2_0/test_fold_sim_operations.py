# Copyright (c) 2026, AFMCO and contributors
"""Idempotency receipt for the SIM Operations -> Logistay fold (A-098 clause 8.6).

The fold patch is registered at ``patches.txt:158``, so ``bench migrate`` has
already run it once by the time this suite starts — but nothing ever exercised
it. A repo-wide ``grep -rn fold_sim_operations apex/`` returned that single
registration line and nothing else, which left "an idempotent migration preserves
records" an unproven claim. This module is that proof: it runs ``execute()``
twice and asserts the four SIM-owned DocType row counts are identical after each
run, and that all four end stamped ``module = Logistay``.

Non-vacuity is the trap here. A count comparison over four empty tables passes
for entirely the wrong reason, so ``setUpClass`` seeds a real Telecom Contract
and SIM Card and the first test asserts the SIM count is non-zero before any
count equality is claimed. Likewise, a fold that no-ops because the site was
already clean proves nothing about the repoint path, so the last test puts the
site back into the broken state the patch exists for (records still stamped with
the retired module) and proves one run repairs it and a second changes nothing.

``execute()`` ends in ``frappe.db.commit()``, so rollback cannot undo it. Cleanup
is therefore explicit rather than transactional, and the module-stamp mutation
registers its restore with ``addCleanup`` BEFORE it mutates, so a mid-test
failure still hands the suite back a Logistay-owned schema.

That broken state is planted with ``db_insert()``, never ``insert()`` (A-203).
``ModuleDef.on_update`` (frappe module_def.py:29-35) calls ``create_modules_folder``
and ``add_to_modules_txt`` whenever ``developer_mode`` is on, so a controller insert
wrote ``SIM Operations`` back into ``apex/modules.txt`` and recreated
``apex/sim_operations/`` in the SOURCE TREE on every run — resurrecting the exact
ghost module ``apex/tests/test_declared_modules_are_alive.py`` exists to forbid.
The modules.txt half is cache-gated (``add_to_modules_txt`` short-circuits while a
warm ``app_modules`` cache still lists the module), so it fires intermittently —
always on the cold cache a fresh bench or CI run starts from. Nothing is weakened
by the change: ``frappe.installer.add_module_defs`` mints a real site's Module Def
with ``frappe.new_doc`` + ``insert``, so the row planted here is field-identical
(``custom = 0`` included), and the patch only ever reads it via ``db.exists`` /
``db.delete`` by name. ``custom = 1`` would also skip ``on_update``, but it would
plant a user-created module where a deployed site carries an app-shipped one.
"""

from __future__ import annotations

from pathlib import Path

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.patches.v2_0 import fold_sim_operations_into_logistay as fold
from apex.tests import factories

# The four SIM-owned DocTypes A-098 clause 3 requires the fold to preserve.
SIM_DOCTYPES = (
    "SIM Card",
    "SIM Custody Assignment",
    "Telecom Contract",
    "Telecom Billing Document",
)


class TestFoldSIMOperationsIdempotency(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = factories.make_company("Test AFMCO").name
        cls.supplier = factories.make_supplier("QA Fold Telco")
        cls.contract = frappe.get_doc(
            {
                "doctype": "Telecom Contract",
                "company": cls.company,
                "supplier": cls.supplier,
                "contract_start_date": "2026-01-01",
                "contract_end_date": "2027-01-01",
                # Mandatory on the shipped DocType; omitting it aborts the fixture
                # before any assertion runs, which a static check cannot see.
                "recurring_amount": 100,
            }
        ).insert(ignore_permissions=True).name
        cls.sim = frappe.get_doc(
            {
                "doctype": "SIM Card",
                "company": cls.company,
                "telecom_contract": cls.contract,
                # Distinct from the sibling migration test's number: the SIM
                # controller rejects a duplicate normalized MSISDN.
                "mobile_number": "0559 000 8461",
            }
        ).insert(ignore_permissions=True).name
        frappe.db.commit()

    @classmethod
    def tearDownClass(cls):
        # The patch commits, so these rows outlive a rollback and must be removed.
        frappe.delete_doc("SIM Card", cls.sim, force=True, ignore_permissions=True)
        frappe.delete_doc("Telecom Contract", cls.contract, force=True, ignore_permissions=True)
        frappe.db.commit()
        super().tearDownClass()

    @staticmethod
    def _counts() -> dict[str, int]:
        return {doctype: frappe.db.count(doctype) for doctype in SIM_DOCTYPES}

    @staticmethod
    def _modules() -> dict[str, str]:
        return {
            doctype: frappe.db.get_value("DocType", doctype, "module")
            for doctype in SIM_DOCTYPES
        }

    def test_the_seeded_data_makes_the_count_assertions_non_vacuous(self):
        """Guard the guard: an equality over empty tables proves nothing."""
        self.assertTrue(frappe.db.exists("SIM Card", self.sim))
        self.assertGreaterEqual(frappe.db.count("SIM Card"), 1)
        self.assertGreaterEqual(frappe.db.count("Telecom Contract"), 1)

    def test_running_the_fold_twice_preserves_records_and_ownership(self):
        """The clause itself: two runs, identical counts, Logistay throughout."""
        owned_by_logistay = {doctype: fold.NEW_MODULE for doctype in SIM_DOCTYPES}
        before = self._counts()
        self.assertGreaterEqual(before["SIM Card"], 1)

        fold.execute()
        after_first = self._counts()
        self.assertEqual(
            after_first, before, "the first fold run must not add or drop a SIM record"
        )
        self.assertEqual(self._modules(), owned_by_logistay)

        fold.execute()
        self.assertEqual(
            self._counts(), after_first, "a second fold run must be a complete no-op"
        )
        self.assertEqual(self._modules(), owned_by_logistay)

    @staticmethod
    def _source_tree_state() -> tuple[str, bool]:
        """The two things ``ModuleDef.on_update`` writes to disk in developer_mode:
        modules.txt content, and whether the retired module package exists."""
        return (
            Path(frappe.get_app_path("apex", "modules.txt")).read_text(),
            Path(frappe.get_app_path("apex", fold.OLD_MODULE)).exists(),
        )

    def _restore_logistay_ownership(self):
        for doctype in SIM_DOCTYPES:
            frappe.db.set_value(
                "DocType", doctype, "module", fold.NEW_MODULE, update_modified=False
            )
        if frappe.db.exists("Module Def", fold.OLD_MODULE):
            frappe.db.delete("Module Def", {"name": fold.OLD_MODULE})
        frappe.db.commit()
        frappe.clear_cache()

    def test_the_fold_repairs_a_site_still_stamped_with_the_retired_module(self):
        """Non-triviality: on an already-clean site the repoint is a no-op, which
        proves nothing. Put the site back into the deployed state the patch
        exists for, then prove one run repairs it and a second does nothing."""
        # Registered BEFORE the mutation so a failure mid-test still restores.
        self.addCleanup(self._restore_logistay_ownership)

        # db_insert, never insert(): the controller's on_update would write the retired
        # module back into the source tree in developer_mode (see the module docstring).
        tree_before = self._source_tree_state()
        ghost = frappe.new_doc("Module Def")
        ghost.module_name = fold.OLD_MODULE
        ghost.app_name = "apex"
        ghost.db_insert()
        self.assertEqual(
            self._source_tree_state(),
            tree_before,
            "planting the retired Module Def must not write to the source tree",
        )

        for doctype in SIM_DOCTYPES:
            frappe.db.set_value(
                "DocType", doctype, "module", fold.OLD_MODULE, update_modified=False
            )
        frappe.db.commit()
        self.assertEqual(
            self._modules(),
            {doctype: fold.OLD_MODULE for doctype in SIM_DOCTYPES},
            "the broken state must actually be established, or the repair is untested",
        )
        before = self._counts()

        fold.execute()
        self.assertEqual(
            self._modules(),
            {doctype: fold.NEW_MODULE for doctype in SIM_DOCTYPES},
            "one run must repoint every SIM DocType onto Logistay",
        )
        self.assertFalse(
            frappe.db.exists("Module Def", fold.OLD_MODULE),
            "the retired Module Def must be gone once nothing references it",
        )
        self.assertEqual(
            self._counts(), before, "repairing the module stamp must not touch a record"
        )

        fold.execute()
        self.assertEqual(
            self._modules(), {doctype: fold.NEW_MODULE for doctype in SIM_DOCTYPES}
        )
        self.assertEqual(self._counts(), before)
