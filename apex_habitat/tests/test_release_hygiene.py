"""Pure-Python release-hygiene guards (no live Frappe site required).

These lock in four fixes made during the hardening overhaul so they cannot
silently regress:

  1. translations/ar.csv stays well-formed (2 columns, every row translated,
     placeholder parity between source and translation).
  2. The duplicate-workspace cleanup patch keeps its canonical name/label sets
     in sync with the shipped workspace JSON — a mismatch previously risked
     deleting the wrong workspace copy.
  3. No patch file carries an embedded "AI INSTRUCTION" prompt-injection comment.
  4. The shipped app declares no test/placeholder role name anywhere in its
     tracked source (DocType permissions, hooks fixtures, seed lists, dashboard
     seeds, and is_standard Notification JSON recipients) — so a Frappe-core test
     fixture such as `_Test Role` can never be packaged and surfaced to operators.

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
HOOKS_PY = os.path.join(APP_ROOT, "hooks.py")

ARABIC = re.compile(r"[؀-ۿ]")
PLACEHOLDER = re.compile(r"\{\d+")

# A role name is "test-shaped" if the substring "test" appears (case-insensitive)
# as a standalone word, OR it is one of the known Frappe-core test fixtures.
# Frappe ships these in frappe/core/doctype/role/test_records.json and only
# creates them when its own test suite runs on a site; the app must never
# package or declare any of them.
TEST_ROLE_RE = re.compile(r"(?:^|[\s_])test(?:$|[\s_0-9])", re.IGNORECASE)
KNOWN_FRAPPE_TEST_ROLES = {
    "_Test Role",
    "_Test Role 2",
    "_Test Role 3",
    "_Test Role 4",
}


def _is_test_role(name):
    """True if `name` looks like a test/placeholder role the app must not ship."""
    if not name or not isinstance(name, str):
        return False
    return name in KNOWN_FRAPPE_TEST_ROLES or bool(TEST_ROLE_RE.search(name))


def _expected_naming_rule(autoname):
    """The canonical Frappe `naming_rule` implied by an `autoname` string.

    Returns None for naming styles we do not assert on (hash / autoincrement /
    Prompt), so the consistency check stays narrow and non-brittle.
    """
    a = autoname or ""
    if a.startswith("field:"):
        return "By fieldname"
    if a.startswith("naming_series:"):
        return 'By "Naming Series" field'
    if a.startswith("format:"):
        return "Expression"
    if re.search(r"\.#+", a):  # old-style series embedded in autoname, e.g. "TFL-.######"
        return "Expression (old style)"
    return None


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


class TestNoTestRolesShipped(unittest.TestCase):
    """The shipped app must declare zero test/placeholder role names.

    Roles such as `_Test Role` are Frappe-core test fixtures; they appear on a
    bench site only because the framework test suite ran there. They must never
    leak into apex_habitat's tracked source, where they would be packaged and
    shown to real operators. This guard scans every place the app names a Role.
    """

    def _doctype_permission_roles(self):
        """Role names declared in DocType JSON `permissions` blocks."""
        roles = set()
        for fp in glob.glob(
            os.path.join(APP_ROOT, "**", "doctype", "**", "*.json"), recursive=True
        ):
            if "node_modules" in fp:
                continue
            with open(fp, encoding="utf-8") as fh:
                try:
                    data = json.load(fh)
                except json.JSONDecodeError:
                    continue
            if not isinstance(data, dict):
                continue
            for perm in data.get("permissions", []) or []:
                role = perm.get("role")
                if role:
                    roles.add(role)
        return roles

    def _seed_list_roles(self):
        """Role names from the Salis role-seed modules' list constants.

        The seed modules `import frappe` at load time; stub it (exactly as
        TestWorkspaceCleanupPatch does) so the module-level constants evaluate
        without a live Frappe install. execute() is never invoked here.
        """
        sys.modules.setdefault("frappe", types.ModuleType("frappe"))
        roles = set()
        seed_specs = [
            ("v1_0/seed_salis_roles.py", "SALIS_ROLES"),
            ("v1_0/seed_salis_authority_roles.py", "AUTHORITY_ROLES"),
            ("v1_0/seed_salis_operations_roles.py", "OPERATIONS_ROLES"),
        ]
        for rel, const in seed_specs:
            path = os.path.join(PATCHES_DIR, *rel.split("/"))
            self.assertTrue(os.path.exists(path), f"seed module missing: {rel}")
            with open(path, encoding="utf-8") as fh:
                ns = {}
                exec(compile(fh.read(), path, "exec"), ns)  # noqa: S102 (trusted, in-repo)
            self.assertIn(const, ns, f"{rel} no longer defines {const}")
            for entry in ns[const]:
                # SALIS_ROLES holds (name, ...) tuples; the others hold names.
                name = entry[0] if isinstance(entry, (tuple, list)) else entry
                roles.add(name)
        return roles

    def _literal_roles_in_files(self, *rel_paths):
        """Role names from `"roles": [...]` literals and hooks Role fixtures.

        Covers files (hooks.py, dashboard/notification seeds) whose role names
        live in inline Python/JSON literals rather than importable constants.
        Scans the raw quoted strings so the source need not be imported.
        """
        roles = set()
        list_block = re.compile(r"\[[^\[\]]*\]")
        quoted = re.compile(r"""['"]([^'"]+)['"]""")
        for rel in rel_paths:
            path = os.path.join(APP_ROOT, rel)
            if not os.path.exists(path):
                continue
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            # "roles": [ ... ] used by dashboard/notification seeds.
            for m in re.finditer(r'"roles"\s*:\s*(\[[^\]]*\])', text):
                roles.update(quoted.findall(m.group(1)))
            # hooks.py Role fixtures: {"dt": "Role", "filters": [["name", "in", [...]]]}
            for m in re.finditer(
                r'"dt"\s*:\s*"Role".*?\[\s*"name"\s*,\s*"in"\s*,\s*(\[[^\]]*\])',
                text,
                re.DOTALL,
            ):
                inner = list_block.search(m.group(1))
                roles.update(quoted.findall(inner.group(0) if inner else m.group(1)))
        return roles

    def _notification_json_roles(self):
        """Recipient role names from the shipped is_standard Notification JSON.

        The operational/event Notifications now ship as is_standard JSON under
        `*/notification/<slug>/<slug>.json` (imported by migrate) instead of the
        retired `notifications_seed.py` modules. Harvest every
        `recipients[].receiver_by_role` so the hygiene check still covers
        notification recipient roles.
        """
        roles = set()
        for fp in glob.glob(
            os.path.join(APP_ROOT, "**", "notification", "**", "*.json"),
            recursive=True,
        ):
            if "node_modules" in fp:
                continue
            with open(fp, encoding="utf-8") as fh:
                try:
                    data = json.load(fh)
                except json.JSONDecodeError:
                    continue
            if not isinstance(data, dict):
                continue
            for recipient in data.get("recipients", []) or []:
                role = recipient.get("receiver_by_role")
                if role:
                    roles.add(role)
        return roles

    def _all_declared_roles(self):
        roles = set()
        roles |= self._doctype_permission_roles()
        roles |= self._seed_list_roles()
        roles |= self._notification_json_roles()
        roles |= self._literal_roles_in_files(
            "hooks.py",
            os.path.join("habitat", "dashboard_seed.py"),
            os.path.join("salis", "dashboard_seed.py"),
        )
        return roles

    def test_detector_recognises_known_fixtures(self):
        # Guard the guard: the matcher must flag the names we are protecting
        # against, and must NOT flag the real business roles the app ships.
        for bad in ("_Test Role", "_Test Role 4", "Test Role", "Some test role"):
            self.assertTrue(_is_test_role(bad), f"should flag {bad!r}")
        for good in (
            "Fleet Manager",
            "Accommodation Manager",
            "Government Relations Officer",
            "System Manager",
            "Driver",
        ):
            self.assertFalse(_is_test_role(good), f"should NOT flag {good!r}")

    def test_app_source_declares_no_doctype_permission_test_role(self):
        offenders = sorted(r for r in self._doctype_permission_roles() if _is_test_role(r))
        self.assertEqual(
            offenders, [], f"test-shaped role in DocType permissions: {offenders}"
        )

    def test_app_source_declares_no_seed_or_fixture_test_role(self):
        declared = self._all_declared_roles()
        # Sanity: the scan must actually find the app's real roles, otherwise a
        # silent parse regression could make this guard vacuously pass.
        self.assertIn("Fleet Manager", declared, "role scan found nothing — parser broke")
        offenders = sorted(r for r in declared if _is_test_role(r))
        self.assertEqual(
            offenders,
            [],
            f"shipped app declares test/placeholder role(s): {offenders}",
        )


class TestNamingRuleConsistency(unittest.TestCase):
    """Every DocType with an `autoname` must carry the matching `naming_rule`.

    Frappe derives the Naming tab's `naming_rule` from `autoname`; when a
    hand-authored DocType JSON sets `autoname` but leaves `naming_rule` empty,
    the desk Naming UI shows blank and a UI save can silently rewrite the
    naming. Seven shipped DocTypes had this gap (fixed 2026-06-03); this guard
    stops it recurring.
    """

    def _doctypes(self):
        out = []
        for fp in glob.glob(os.path.join(APP_ROOT, "*", "doctype", "*", "*.json")):
            with open(fp, encoding="utf-8") as fh:
                try:
                    data = json.load(fh)
                except json.JSONDecodeError:
                    continue
            if not isinstance(data, dict) or data.get("doctype") != "DocType":
                continue
            out.append((data.get("name"), data.get("autoname"), data.get("naming_rule")))
        return out

    def test_scan_finds_doctypes(self):
        # Guard the guard: a parser regression must not make this vacuously pass.
        names = {n for n, _, _ in self._doctypes()}
        self.assertIn("Accommodation Bed", names, "DocType scan found nothing — parser broke")

    def test_autoname_implies_naming_rule(self):
        offenders = sorted(name for name, an, nr in self._doctypes() if an and not nr)
        self.assertEqual(
            offenders, [], f"DocType sets autoname but leaves naming_rule empty: {offenders}"
        )

    def test_naming_rule_matches_autoname_style(self):
        bad = []
        for name, an, nr in self._doctypes():
            expected = _expected_naming_rule(an)
            if expected and nr != expected:
                bad.append((name, an, nr, expected))
        self.assertEqual(bad, [], f"naming_rule inconsistent with autoname style: {bad[:10]}")


class TestNoFutureDatedModified(unittest.TestCase):
    """No shipped is_standard JSON may carry a FUTURE `modified` timestamp.

    A future `modified` is a migrate-skip-trap: once installed, the DB row holds
    the future date, so a later real edit (stamped now) looks OLDER and Frappe's
    import skips the file — edits silently fail to re-import in place. Three
    Doc/Workspace JSONs had this (fixed 2026-06-03); this guard stops it.
    """

    def _parse_modified(self, value):
        import datetime

        if not value or not isinstance(value, str):
            return None
        for fmt, width in (("%Y-%m-%d %H:%M:%S.%f", 26), ("%Y-%m-%d %H:%M:%S", 19)):
            try:
                return datetime.datetime.strptime(value[:width], fmt)
            except ValueError:
                continue
        return None

    def test_no_modified_in_the_future(self):
        import datetime

        # `modified` strings are naive and are often stamped in LOCAL time, while
        # CI runs in UTC — a naive compare to "now" would flag a stamp made a few
        # hours ago in a UTC+N zone as "future". Tolerate 2 days of skew (well
        # above any timezone offset) so the guard only fires on the real defect:
        # hand-authored dates DAYS/years ahead (the migrate-skip-trap).
        horizon = datetime.datetime.now() + datetime.timedelta(days=2)
        offenders = []
        for fp in glob.glob(os.path.join(APP_ROOT, "*", "**", "*.json"), recursive=True):
            if "node_modules" in fp:
                continue
            try:
                with open(fp, encoding="utf-8") as fh:
                    data = json.load(fh)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if not isinstance(data, dict):
                continue
            ts = self._parse_modified(data.get("modified"))
            if ts and ts > horizon:
                offenders.append((os.path.relpath(fp, APP_ROOT), data.get("modified")))
        self.assertEqual(
            offenders, [], f"is_standard JSON carries a FUTURE `modified`: {offenders[:10]}"
        )


if __name__ == "__main__":
    unittest.main()
