# Copyright (c) 2026, AFMCO and contributors
"""Standard-record path parity: every shipped record folder must be scrub(record name).

Frappe exports a standard record to
``<module>/<doctype_slug>/<scrub(name)>/<scrub(name)>.json`` -- the folder comes
from ``create_folder(module, doc.doctype, doc.name, ...)`` and the file basename
from ``fname = scrub(doc.name)`` (frappe/modules/export_file.py:44-53). It reads
those records back by WALKING the folders and opening
``os.path.join(doctype_path, docname, docname) + ".json"``
(frappe/model/sync.py:133-138). Dashboards, Dashboard Charts and Number Cards
take a second walk with the same shape, ``import_file_by_path(f"{path}/{fname}/
{fname}.json")`` (frappe/utils/dashboard.py:97-113), so they are covered here
too. ``scrub`` is a slug rule only -- spaces and hyphens to underscores,
lowercased (frappe/__init__.py:1463-1465).

Two silent failures follow from a folder that disagrees with the record it holds:

1. a re-export writes a SECOND folder beside the stale one, so the app then
   ships two on-disk copies of one record;
2. a JSON whose basename differs from its folder is never synced at all -- the
   walk builds the path from the folder name, so the file ships as dead weight.

Neither surfaces as an error, so this guard walks every shipped record folder in
the app and asserts both properties. The DB row is keyed on the record ``name``
inside the JSON, not on the path, so correcting a folder is a pure rename with
no data migration.
"""

import json
import os
import unittest

import frappe
from frappe.model.sync import IMPORTABLE_DOCTYPES

APP = frappe.get_app_path("apex")

# Read off the framework list rather than hardcoded, so a newly importable record
# type is covered here the day the framework starts syncing it.
SYNC_SLUGS = sorted({slug for _module, slug in IMPORTABLE_DOCTYPES})

# The second walk, from make_records_in_module: "<module>_dashboard" is added
# per module below because the slug carries the module name.
DASHBOARD_SLUGS = ("dashboard_chart", "number_card")

# Frozen pre-existing mismatches, as "<module>/<slug>/<folder>". Renaming the FOLDER
# to scrub(name), punctuation included, is the fix: the record name is the primary
# key a Dashboard or Workspace row points at, so renaming the record to buy a
# cleaner path would orphan those pointers, and "(" or "%" in a record folder is
# what a Desk re-export writes anyway (ERPNext and HRMS ship many).
# Nothing may be added here: a new entry admits a record re-export will duplicate.
KNOWN_MISMATCHES = frozenset()

# Floor for the vacuity check; the app ships 522 record folders today.
MIN_RECORD_FOLDERS = 480


def _record_folders():
    """Yield (module, slug, folder, path) for every shipped record folder."""
    for module in sorted(os.listdir(APP)):
        module_path = os.path.join(APP, module)
        if not os.path.isdir(module_path):
            continue
        for slug in [*SYNC_SLUGS, *DASHBOARD_SLUGS, f"{module}_dashboard"]:
            slug_path = os.path.join(module_path, slug)
            if not os.path.isdir(slug_path):
                continue
            for folder in sorted(os.listdir(slug_path)):
                path = os.path.join(slug_path, folder)
                if not os.path.isdir(path):
                    continue
                # A record folder is one that SHIPS something. Skip the interpreter's
                # __pycache__ and any directory git left behind empty when its files
                # were removed: neither is in a fresh checkout, so judging them would
                # make the verdict depend on which machine ran the gate.
                if folder == "__pycache__" or not any(os.scandir(path)):
                    continue
                yield module, slug, folder, path


class TestStandardRecordPathParity(unittest.TestCase):
    def test_record_json_basename_matches_its_folder(self):
        bad = []
        for module, slug, folder, path in _record_folders():
            if os.path.isfile(os.path.join(path, f"{folder}.json")):
                continue
            shipped = sorted(f for f in os.listdir(path) if f.endswith(".json"))
            bad.append(f"{module}/{slug}/{folder}: expected {folder}.json, found {shipped}")
        self.assertEqual(bad, [], f"record JSON is unreachable to the import walk: {bad}")

    def test_folder_name_matches_scrubbed_record_name(self):
        bad = []
        for module, slug, folder, path in _record_folders():
            doc_path = os.path.join(path, f"{folder}.json")
            if not os.path.isfile(doc_path):
                continue  # already reported by the basename test
            with open(doc_path, encoding="utf-8") as handle:
                name = json.load(handle).get("name")
            if not name:
                bad.append(f"{module}/{slug}/{folder}: JSON has no 'name'")
                continue
            expected = frappe.scrub(name)
            if expected != folder and f"{module}/{slug}/{folder}" not in KNOWN_MISMATCHES:
                bad.append(f"{module}/{slug}/{folder}: holds {name!r}, re-export writes {expected}/")
        self.assertEqual(bad, [], f"record folder disagrees with the record it holds: {bad}")

    def test_frozen_exceptions_are_still_real(self):
        """A fixed entry must leave this set, or the exception silently outlives the debt."""
        stale = []
        for entry in sorted(KNOWN_MISMATCHES):
            module, slug, folder = entry.split("/")
            doc_path = os.path.join(APP, module, slug, folder, f"{folder}.json")
            if not os.path.isfile(doc_path):
                stale.append(f"{entry}: no longer on disk")
                continue
            with open(doc_path, encoding="utf-8") as handle:
                name = json.load(handle).get("name")
            if name and frappe.scrub(name) == folder:
                stale.append(f"{entry}: now matches -- drop it from KNOWN_MISMATCHES")
        self.assertEqual(stale, [], f"frozen exceptions no longer describe real debt: {stale}")

    def test_scan_is_not_vacuous(self):
        seen = {f"{module}/{slug}/{folder}" for module, slug, folder, _ in _record_folders()}
        self.assertIn(
            "habitat/form_tour/housing_assignment",
            seen,
            "expected Form Tour folder not scanned -- the walk is broken",
        )
        self.assertIn(
            "salis/module_onboarding/fleet_go_live",
            seen,
            "expected Module Onboarding folder not scanned -- the walk is broken",
        )
        self.assertIn(
            "salis/number_card/active_vehicles",
            seen,
            "expected Number Card folder not scanned -- the dashboard walk is broken",
        )
        self.assertGreaterEqual(
            len(seen),
            MIN_RECORD_FOLDERS,
            f"only {len(seen)} record folders scanned -- the walk is broken",
        )
