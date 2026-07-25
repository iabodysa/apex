# Copyright (c) 2026, AFMCO and contributors
"""Guard: the bed-occupancy indexes reach BOTH install paths, under one set of names.

Frappe gives a DocType index two disjoint delivery paths and this app needs both:

  * fresh install — the table is created and ``on_doctype_update`` runs, while every
    registered patch is marked complete WITHOUT being executed;
  * already-installed site — a plain ``bench migrate`` re-imports only a DocType JSON
    whose hash changed, so ``on_doctype_update`` never fires, and only a patch that no
    Patch Log has seen yet can still create the index.

So the hook alone leaves existing sites unindexed and the patch alone leaves fresh
installs unindexed. These tests pin both paths, and pin them to the SAME index names —
if the two drift apart a site ends up with the same index twice under two names.

No live site or DB is needed: the DDL boundary (``add_index_guarded``) is mocked, so
what is asserted is the delegation itself, never the SQL.

The v1_x patch carries no body of its own — it exists so an already-installed site
gets a Patch Log entry it has never seen, and it delegates to the v0_7 patch, which
delegates to the controller declaration. That is why the ``frappe`` guard these tests
mock lives on the v0_7 module: three copies of the same two calls is exactly what the
duplicate-code guard rejects, and the drift it prevents is a site holding one index
twice under two names.
"""

import os
import unittest
from unittest import mock

import apex
from apex.apex_core.utils import ledger_index
from apex.habitat.doctype.housing_assignment import housing_assignment
from apex.patches.v0_7 import add_bed_assignment_index as legacy_patch
from apex.patches.v1_x import add_bed_occupancy_indexes as bed_index_patch

_PATCH = "apex.patches.v1_x.add_bed_occupancy_indexes"

# The contract both delivery paths must satisfy: {index_name: [column, ...]}.
_EXPECTED_INDEXES = {
    "idx_asgn_bed": ["bed"],
    "idx_asgn_bed_active": ["bed", "docstatus", "check_out_date"],
}


def _patches_txt_sections():
    """{section_name: [dotted entry, ...]} parsed out of patches.txt, comments and
    blank lines dropped — the same shape frappe's patch handler reads."""
    path = os.path.join(os.path.dirname(apex.__file__), "patches.txt")
    sections, current = {}, None
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if line.startswith("[") and line.endswith("]"):
                current = line[1:-1]
                sections.setdefault(current, [])
            elif line and not line.startswith("#") and current is not None:
                sections[current].append(line)
    return sections


def _index_calls(add_index_mock):
    """{index_name: [column, ...]} recorded off the mocked helper, so an assertion
    reads as the index contract rather than as call plumbing."""
    calls = {}
    for call in add_index_mock.call_args_list:
        doctype, fields, index_name = call.args
        assert doctype == "Housing Assignment", f"unexpected doctype {doctype!r}"
        calls[index_name] = list(fields)
    return calls


class TestBedOccupancyIndexPatchRegistration(unittest.TestCase):
    def test_patch_is_registered_post_model_sync(self):
        """post_model_sync, deliberately: the index spans bed / docstatus /
        check_out_date, columns that must already exist when the DDL runs. It reads
        no column that sync_all() is about to change, so pre_model_sync would buy
        nothing and would risk indexing a column the same migrate still has to add."""
        sections = _patches_txt_sections()
        self.assertIn(
            _PATCH,
            sections.get("post_model_sync", []),
            f"{_PATCH} must be registered under [post_model_sync] — without a "
            "patches.txt entry no already-installed site ever gains the bed indexes.",
        )
        self.assertNotIn(
            _PATCH,
            sections.get("pre_model_sync", []),
            f"{_PATCH} indexes columns that must already exist, so it belongs in "
            "[post_model_sync], not before the model sync.",
        )


class TestBedOccupancyIndexPatchExecute(unittest.TestCase):
    def test_execute_delegates_both_indexes_to_the_guarded_helper(self):
        with mock.patch.object(legacy_patch, "frappe") as mock_frappe, mock.patch.object(
            ledger_index, "add_index_guarded", return_value=True
        ) as add_index:
            mock_frappe.db.exists.return_value = True
            bed_index_patch.execute()

        self.assertEqual(
            _index_calls(add_index),
            _EXPECTED_INDEXES,
            "the patch must create BOTH bed indexes through add_index_guarded",
        )
        mock_frappe.db.sql.assert_not_called()

    def test_execute_writes_no_raw_ddl_of_its_own(self):
        """The helper owns the idempotency check and the rollback-on-error path; a
        patch issuing its own ALTER TABLE would abort migrate on a bad table."""
        with mock.patch.object(legacy_patch, "frappe") as mock_frappe, mock.patch.object(
            ledger_index, "add_index_guarded", return_value=True
        ):
            mock_frappe.db.exists.return_value = True
            bed_index_patch.execute()

        mock_frappe.db.sql.assert_not_called()
        mock_frappe.db.add_index.assert_not_called()

    def test_execute_is_a_noop_when_the_doctype_is_absent(self):
        with mock.patch.object(legacy_patch, "frappe") as mock_frappe, mock.patch.object(
            ledger_index, "add_index_guarded"
        ) as add_index:
            mock_frappe.db.exists.return_value = False
            bed_index_patch.execute()

        add_index.assert_not_called()

    def test_rerun_is_idempotent_at_the_helper_boundary(self):
        """Two consecutive runs issue the same guarded calls; the helper no-ops on an
        existing index, so replaying the patch can never duplicate one."""
        with mock.patch.object(legacy_patch, "frappe") as mock_frappe, mock.patch.object(
            ledger_index, "add_index_guarded", return_value=True
        ) as add_index:
            mock_frappe.db.exists.return_value = True
            bed_index_patch.execute()
            first = _index_calls(add_index)
            add_index.reset_mock()
            bed_index_patch.execute()
            second = _index_calls(add_index)

        self.assertEqual(first, second)
        self.assertEqual(second, _EXPECTED_INDEXES)


class TestFreshInstallHookStillDeclaresTheIndexes(unittest.TestCase):
    def test_on_doctype_update_declares_the_same_indexes_as_the_patch(self):
        """A fresh install marks patches complete without running them, so the hook
        is the ONLY path that indexes a brand-new site — it must stay, and it must
        name the same indexes as the patch or a site gains each one twice."""
        with mock.patch.object(
            ledger_index, "add_index_guarded", return_value=True
        ) as add_index:
            housing_assignment.on_doctype_update()

        self.assertEqual(_index_calls(add_index), _EXPECTED_INDEXES)


if __name__ == "__main__":
    unittest.main()
