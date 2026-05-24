"""Pure-Python release-hygiene guards (no live Frappe site required).

These lock in three fixes made during the hardening overhaul so they cannot
silently regress:

  1. translations/ar.csv stays well-formed (2 columns, every row translated,
     placeholder parity between source and translation).
  2. The duplicate-workspace cleanup patch keeps its canonical name/label sets
     in sync with the shipped workspace JSON — a mismatch previously risked
     deleting the wrong workspace copy.
  3. No patch file carries an embedded "AI INSTRUCTION" prompt-injection comment.

Run standalone:  python3 -m unittest tests.test_release_hygiene -v
"""

import csv
import glob
import json
import os
import re
import sys
import types
import unittest

APP_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
AR_CSV = os.path.join(APP_ROOT, "translations", "ar.csv")
WORKSPACE_DIR = os.path.join(APP_ROOT, "habitat", "workspace")
PATCHES_DIR = os.path.join(APP_ROOT, "patches")

ARABIC = re.compile(r"[؀-ۿ]")
PLACEHOLDER = re.compile(r"\{\d+")


class TestTranslationFile(unittest.TestCase):
    def _rows(self):
        with open(AR_CSV, encoding="utf-8") as fh:
            return [r for r in csv.reader(fh) if r]

    def test_every_row_has_exactly_two_columns(self):
        bad = [(i, r) for i, r in enumerate(self._rows(), 1) if len(r) != 2]
        self.assertEqual(
            bad, [], f"ar.csv rows must be (source, translation); offenders: {bad[:10]}"
        )

    def test_every_translation_contains_arabic(self):
        missing = [r[0] for r in self._rows() if len(r) == 2 and not ARABIC.search(r[1])]
        self.assertEqual(
            missing, [], f"ar.csv rows with no Arabic translation: {missing[:10]}"
        )

    def test_placeholder_parity(self):
        bad = [
            r[0]
            for r in self._rows()
            if len(r) == 2 and len(PLACEHOLDER.findall(r[0])) != len(PLACEHOLDER.findall(r[1]))
        ]
        self.assertEqual(bad, [], f"ar.csv placeholder count mismatch: {bad[:10]}")


class TestWorkspaceCleanupPatch(unittest.TestCase):
    def _shipped_workspace_names(self):
        names = set()
        for fp in glob.glob(os.path.join(WORKSPACE_DIR, "*", "*.json")):
            with open(fp, encoding="utf-8") as fh:
                data = json.load(fh)
            names.add(data.get("name"))
        return names

    def test_patch_sets_match_shipped_workspaces(self):
        patch_path = os.path.join(
            PATCHES_DIR, "v0_4", "cleanup_duplicate_workspaces.py"
        )
        with open(patch_path, encoding="utf-8") as fh:
            src = fh.read()
        # The patch does `import frappe` at module load; stub it so the
        # module-level set definitions evaluate without a live Frappe install.
        # (No frappe call runs at import time — execute() is never invoked here.)
        sys.modules.setdefault("frappe", types.ModuleType("frappe"))
        ns = {}
        exec(compile(src, patch_path, "exec"), ns)
        shipped = self._shipped_workspace_names()
        # Every shipped workspace name must be recognised by the cleanup sets,
        # otherwise the dedup logic cannot protect the canonical record.
        self.assertTrue(shipped, "no shipped workspace JSON found")
        self.assertTrue(
            shipped.issubset(ns["APP_WORKSPACE_LABELS"]),
            f"workspaces missing from APP_WORKSPACE_LABELS: "
            f"{shipped - ns['APP_WORKSPACE_LABELS']}",
        )
        self.assertTrue(
            shipped.issubset(ns["APP_WORKSPACE_NAMES"]),
            f"workspaces missing from APP_WORKSPACE_NAMES: "
            f"{shipped - ns['APP_WORKSPACE_NAMES']}",
        )


class TestNoPromptInjectionInPatches(unittest.TestCase):
    def test_no_ai_instruction_comments(self):
        offenders = []
        for fp in glob.glob(os.path.join(PATCHES_DIR, "**", "*.py"), recursive=True):
            with open(fp, encoding="utf-8") as fh:
                text = fh.read()
            if re.search(r"AI INSTRUCTION|you MUST delete this", text, re.IGNORECASE):
                offenders.append(os.path.relpath(fp, APP_ROOT))
        self.assertEqual(
            offenders, [], f"prompt-injection comment found in patches: {offenders}"
        )


if __name__ == "__main__":
    unittest.main()
