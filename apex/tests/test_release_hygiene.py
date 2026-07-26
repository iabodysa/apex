# Copyright (c) 2026, AFMCO and contributors
"""Pure-Python release-hygiene guards (no live Frappe site required).

These lock in release-hygiene invariants that must not silently regress:

  1. translations/ar.csv stays well-formed (2 columns, every row translated,
     placeholder parity between source and translation).
  2. No patch file carries an embedded "AI INSTRUCTION" prompt-injection comment.
  3. The shipped app declares no test/placeholder role name anywhere in its
     tracked source (DocType permissions, hooks fixtures, seed lists, dashboard
     seeds, and is_standard Notification JSON recipients) — so a Frappe-core test
     fixture such as `_Test Role` can never be packaged and surfaced to operators.
  4. Every portal in the SPA lockfile CI matrix ships both its manifest and lockfile.
  5. No Arabic reaches published source (.py/.json/.js/.html) or the published
     documentation set (README.md and docs/) outside the localization homes.
  6. Every shipped line-oriented data file (translations, modules.txt,
     patches.txt) uses LF endings, so an edit diffs as the rows it changed.

Run standalone:  python3 -m unittest apex.tests.test_release_hygiene -v
"""

import csv
import glob
import io
import json
import os
import re
import subprocess
import sys
import tokenize
import types
import unittest

APP_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
REPO_ROOT = os.path.dirname(APP_ROOT)
AR_CSV = os.path.join(APP_ROOT, "translations", "ar.csv")
TRANSLATIONS_DIR = os.path.join(APP_ROOT, "translations")
PATCHES_DIR = os.path.join(APP_ROOT, "patches")
HOOKS_PY = os.path.join(APP_ROOT, "hooks.py")

# Line-oriented data the app itself ships. Vendored third-party files are out:
# they must stay byte-identical to upstream, CRLF included -- see the scope
# decision on TestShippedDataLineEndings before widening this.
SHIPPED_DATA_MANIFESTS = ("modules.txt", "patches.txt")

ARABIC = re.compile(r"[؀-ۿ]")
PLACEHOLDER = re.compile(r"\{\d+")

# [#k9i6gc]
ARABIC_HOMES = (
    os.sep + "tests" + os.sep,
    os.sep + "print_format" + os.sep,
    "worker_portal",
    "fleet_portal",
    "fleet_os_portal",
    "safety_portal",
    "housing_portal",
    "route_supervisor_portal",
    os.sep + "change_log" + os.sep,
)

# Homes that need not exist in every checkout, so the reachability check below
# exempts them: translations/ holds only ar.csv, demo/ ships conditionally, and
# node_modules/ appears only after a local install.
OPTIONAL_ARABIC_HOMES = (
    os.sep + "translations" + os.sep,
    os.sep + "demo" + os.sep,
    os.sep + "node_modules" + os.sep,
)

ALL_ARABIC_HOMES = ARABIC_HOMES + OPTIONAL_ARABIC_HOMES

# `.html` is in the set because the www Jinja shells and the print formats are
# shipped source too, and an Arabic <title> there reaches every visitor.
SCANNED_SOURCE_EXTS = ("py", "json", "js", "html")

# The published Markdown set. Restricted to these two paths on purpose: globbing
# the whole repo root would walk locally-ignored directories, so a developer's
# tree would disagree with CI's fresh checkout.
PUBLISHED_DOCS_DIR = os.path.join(REPO_ROOT, "docs")
PUBLISHED_README = os.path.join(REPO_ROOT, "README.md")

# [#oy1z45]
LATIN_BRAND_SOURCES = {"AFMCO"}

# [#bsvh0z]
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


def _duplicate_perm_pairs(permissions):
    """The (role, permlevel) pairs a DocPerm list declares more than once.

    Pure over its argument so the guard's planted-violation proof can drive it with
    synthetic rows. permlevel is normalised because a permlevel-0 row usually omits the
    key entirely while some rows spell it out.
    """
    seen, dupes = set(), set()
    for row in permissions or []:
        role = row.get("role")
        if not role:
            continue
        pair = (role, int(row.get("permlevel") or 0))
        if pair in seen:
            dupes.add(pair)
        seen.add(pair)
    return dupes


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
    if re.search(r"\.#+", a):  # [#abkkxs]
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
        missing = [
            r[0]
            for r in self._rows()
            if len(r) == 2
            and r[0] not in LATIN_BRAND_SOURCES
            and not ARABIC.search(r[1])
        ]
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


class TestShippedDataLineEndings(unittest.TestCase):
    """Two line-ending styles in one file make every edit unreviewable: the
    editor renormalizes the minority rows, so a two-row change arrives as
    thousands of identical-looking lines. LF is the required ending because
    frappe/translate.py write_csv_file() regenerates the translation CSVs with
    lineterminator="\\n" — any other choice is undone on the next
    `bench update-translations`. .gitattributes prevents; this test detects.

    SCOPE — settled, do not re-litigate: this guard judges apex-owned files
    only. The apps we depend on carry the same mixed-ending drift in the
    same-named file; measured on the pinned checkouts, hrms
    translations/ar.csv has 388 CRLF rows of 1234, erpnext
    translations/ar.csv 459 of 9489. Widening the scan to reach them was
    considered and rejected:

      1. We cannot fix what we do not ship. Those files live in sibling apps,
         outside this repo's tree and index. `_files()` roots at APP_ROOT and
         the matching .gitattributes rules are written against apex/ paths, so
         neither can reach them by construction. Normalizing them in place
         would only make the checkout diverge from upstream — exactly what the
         byte-identical rule above forbids.
      2. A red nobody can clear is a red that gets deleted. Those endings come
         back on the next dependency update, so the gate would fail for a
         reason no commit in this repo can address, and would be switched off.
      3. The blast radius is nil for us. The damage this guard prevents — a
         two-row edit arriving as a whole-file rewrite — is confined to the
         file that mixes endings, and no apex diff renders through a sibling
         app's CSV.

    Reporting the drift upstream stays a courtesy, never a release gate; that
    fix belongs in a pull request to the app that owns the file.
    """

    def _files(self):
        found = [os.path.join(APP_ROOT, n) for n in SHIPPED_DATA_MANIFESTS]
        found += sorted(glob.glob(os.path.join(TRANSLATIONS_DIR, "*")))
        return [fp for fp in found if os.path.isfile(fp)]

    def test_scan_covers_the_translation_files(self):
        names = {os.path.basename(fp) for fp in self._files()}
        self.assertIn("ar.csv", names, f"line-ending scan missed ar.csv; saw {sorted(names)}")

    def test_shipped_data_files_use_lf_only(self):
        offenders = []
        for fp in self._files():
            with open(fp, "rb") as fh:
                data = fh.read()
            crlf = data.count(b"\r\n")
            stray_cr = data.count(b"\r") - crlf
            if crlf or stray_cr:
                offenders.append(
                    f"{os.path.relpath(fp, REPO_ROOT)} (CRLF rows: {crlf}, stray CR: {stray_cr})"
                )
        self.assertEqual(
            offenders,
            [],
            "shipped data files must use LF line endings, else the next edit "
            "rewrites every row; offenders: " + "; ".join(offenders),
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


class TestFrontendWorkspaceOwnership(unittest.TestCase):
    """frontend/ is ONE npm workspace: exactly one manifest owns every dependency
    and exactly one lockfile pins them. Replaces the retired per-portal
    spa-lockfiles matrix (and frontend_shared/pins.json), which only existed to
    keep six hand-mirrored manifests from drifting."""

    def _root_manifest(self):
        path = os.path.join(REPO_ROOT, "frontend", "package.json")
        self.assertTrue(os.path.isfile(path), "frontend/package.json is missing")
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)

    def test_exactly_one_lockfile_under_frontend(self):
        lockfiles = []
        for dirpath, dirnames, filenames in os.walk(os.path.join(REPO_ROOT, "frontend")):
            dirnames[:] = [d for d in dirnames if d != "node_modules"]
            if "package-lock.json" in filenames:
                lockfiles.append(
                    os.path.relpath(
                        os.path.join(dirpath, "package-lock.json"), REPO_ROOT
                    )
                )
        self.assertEqual(
            sorted(lockfiles),
            ["frontend/package-lock.json"],
            "frontend/package-lock.json must be the only frontend lockfile",
        )

    def test_only_the_root_manifest_declares_dependencies(self):
        offenders = []
        for workspace in self._root_manifest()["workspaces"]:
            path = os.path.join(REPO_ROOT, "frontend", workspace, "package.json")
            if not os.path.isfile(path):
                offenders.append(f"{workspace}: no package.json")
                continue
            with open(path, encoding="utf-8") as fh:
                manifest = json.load(fh)
            owned = [
                key
                for key in ("dependencies", "devDependencies", "overrides")
                if manifest.get(key)
            ]
            if owned:
                offenders.append(f"{workspace}: declares {', '.join(owned)}")
        self.assertEqual(
            offenders,
            [],
            "frontend deps belong only in frontend/package.json: "
            f"{offenders}",
        )

    def test_root_manifest_keeps_the_security_overrides(self):
        overrides = self._root_manifest().get("overrides", {})
        self.assertEqual(
            sorted(overrides),
            ["dompurify", "ws"],
            "frontend/package.json must keep the dompurify + ws security overrides",
        )

    def test_every_workspace_that_builds_ships_a_committed_bundle(self):
        """A workspace with a vite.config.js is a portal; its bundle is committed
        under apex/public/<workspace>_portal/ and guarded by portal-bundles."""
        missing = []
        for workspace in sorted(self._root_manifest()["workspaces"]):
            if not os.path.isfile(
                os.path.join(REPO_ROOT, "frontend", workspace, "vite.config.js")
            ):
                continue
            output = os.path.join(REPO_ROOT, "apex", "public", f"{workspace}_portal")
            if not os.path.isdir(output):
                missing.append(os.path.relpath(output, REPO_ROOT))
        self.assertEqual(
            missing, [], f"workspace portals with no committed bundle: {missing}"
        )


class TestMasarWorkerTokenNaming(unittest.TestCase):
    def test_driver_name_is_not_synced_into_the_worker_party_field(self):
        path = os.path.join(
            APP_ROOT,
            "apex_core",
            "doctype",
            "masar_worker_token",
            "masar_worker_token.json",
        )
        with open(path, encoding="utf-8") as fh:
            doctype = json.load(fh)

        self.assertEqual(doctype.get("autoname"), "hash")
        self.assertEqual(doctype.get("naming_rule"), "Random")


class TestNoTestRolesShipped(unittest.TestCase):
    """The shipped app must declare zero test/placeholder role names.

    Roles such as `_Test Role` are Frappe-core test fixtures; they appear on a
    bench site only because the framework test suite ran there. They must never
    leak into apex's tracked source, where they would be packaged and
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
                # [#fz2jvh]
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
            # [#8bv3s4]
            for m in re.finditer(r'"roles"\s*:\s*(\[[^\]]*\])', text):
                roles.update(quoted.findall(m.group(1)))
            # [#mhln5m]
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
            os.path.join(
                "apex_core", "setup", "seeders", "habitat_dashboard_seed.py"
            ),
        )
        return roles

    def test_detector_recognises_known_fixtures(self):
        # [#pack7e]
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
        # [#cdebmq]
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
        # [#hi39j1]
        names = {n for n, _, _ in self._doctypes()}
        self.assertIn("Bed", names, "DocType scan found nothing — parser broke")

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


class TestNoDuplicateDocPermRows(unittest.TestCase):
    """No shipped DocType may carry the same (role, permlevel) DocPerm row twice.

    A duplicate row is not cosmetic. ``frappe/permissions.py:283-307``
    ``get_role_permissions`` ORs every applicable row together, and line 287
    ``has_permission_without_if_owner_enabled`` disables an ``if_owner`` narrowing for a
    permission type as soon as ANY applicable row grants that type without ``if_owner``.
    A second plain read row therefore silently converts an owner-scoped read into a read
    of every record, with nothing in the JSON to show it happened.

    The pair, not the role alone, is the invariant: line 284 ``is_perm_applicable`` keeps
    only ``permlevel == 0`` rows, so a permlevel-1 row is a DIFFERENT grant governing the
    permlevel-1 fields and coexists with the permlevel-0 row by design. Sixteen shipped
    DocTypes carry a role twice across two permlevels for exactly that reason; keying on
    role alone would condemn all of them and, if "fixed", would strip field-level access.
    """

    def _doctype_permissions(self):
        """(DocType name, permissions list) for every DocType JSON apex ships."""
        out = []
        for fp in glob.glob(os.path.join(APP_ROOT, "*", "doctype", "*", "*.json")):
            with open(fp, encoding="utf-8") as fh:
                try:
                    data = json.load(fh)
                except json.JSONDecodeError:
                    continue
            if not isinstance(data, dict) or data.get("doctype") != "DocType":
                continue
            out.append((data.get("name"), data.get("permissions") or []))
        return out

    def test_scan_finds_doctypes(self):
        names = {n for n, _ in self._doctype_permissions()}
        self.assertIn("Salis Driver", names, "DocType scan found nothing — parser broke")

    def test_no_doctype_ships_a_duplicate_role_permlevel_pair(self):
        offenders = {}
        for name, perms in self._doctype_permissions():
            dupes = sorted(_duplicate_perm_pairs(perms))
            if dupes:
                offenders[name] = dupes
        self.assertEqual(
            offenders,
            {},
            "DocType ships the same (role, permlevel) permission row more than once. The "
            "rows are OR-ed together, so a duplicate can silently disable an if_owner "
            f"narrowing on the same role: {offenders}",
        )

    def test_the_detector_flags_a_planted_duplicate(self):
        """Proof the guard can fail, driven with synthetic rows so it proves the DETECTOR
        rather than the current file contents."""
        planted = [
            {"role": "Fleet Manager", "read": 1, "if_owner": 1},
            {"role": "Fleet Manager", "read": 1},
        ]
        self.assertEqual(_duplicate_perm_pairs(planted), {("Fleet Manager", 0)})

    def test_the_detector_allows_one_role_across_two_permlevels(self):
        """The counter-case that keeps the guard from condemning a legitimate shape:
        get_role_permissions filters to permlevel 0, so a permlevel-1 row is a separate
        grant, not a duplicate."""
        legitimate = [
            {"role": "Fleet Manager", "read": 1, "write": 1},
            {"role": "Fleet Manager", "read": 1, "permlevel": 1},
        ]
        self.assertEqual(_duplicate_perm_pairs(legitimate), set())


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

        # [#lthu2d]
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


class TestNoArabicInSource(unittest.TestCase):
    """Arabic belongs in ar.csv and the portal bundles, never in what we publish.

    Two published surfaces used to escape this scan. The www Jinja shells are
    `.html`, an extension the scan never read, so an Arabic `<title>` shipped
    unreviewed on every portal route; and the docs/ tree GitHub renders was not
    scanned at all. Both are covered here, so a translation review cannot be
    skipped by choosing a different file type.

    Two ARABIC_HOMES entries named those www shells. They were dead code — the
    scan never read `.html`, so they exempted nothing — and they are retired
    rather than kept: both shells now resolve their `<title>` through ar.csv, so
    with `.html` scanned neither needs an exemption.
    """

    def _source_files(self):
        """Published package source, minus the directories where Arabic belongs."""
        paths = []
        for ext in SCANNED_SOURCE_EXTS:
            for path in glob.glob(os.path.join(APP_ROOT, "**", f"*.{ext}"), recursive=True):
                if not any(home in path for home in ALL_ARABIC_HOMES):
                    paths.append(path)
        return paths

    def _published_doc_files(self):
        """Every TRACKED file under docs/, plus README.md — no extension filter, so
        a published page cannot dodge the scan by not being Markdown.

        Tracked, because "published" means what git ships. `docs/` also holds local
        working notes that are gitignored and absent from a fresh checkout; judging
        those makes the verdict depend on whose machine ran it, which is the exact
        defect A-135 fixed in the comment gate.
        """
        listed = subprocess.run(
            ["git", "-C", REPO_ROOT, "ls-files", "-z", "--", "docs"],
            capture_output=True,
            text=True,
            check=False,
        )
        if listed.returncode != 0:
            # No git (an sdist / tarball): fall back to the whole tree rather than
            # an empty set, so the scan degrades loud instead of silently passing.
            paths = glob.glob(os.path.join(PUBLISHED_DOCS_DIR, "**", "*"), recursive=True)
            return [p for p in paths if os.path.isfile(p)] + [PUBLISHED_README]
        tracked = [
            os.path.join(REPO_ROOT, rel) for rel in listed.stdout.split("\0") if rel
        ]
        return [p for p in tracked if os.path.isfile(p)] + [PUBLISHED_README]

    def test_scan_reaches_html_and_published_docs(self):
        # Non-vacuity: a broken glob would green the scan below by finding nothing.
        rels = {
            os.path.relpath(p, REPO_ROOT)
            for p in self._source_files() + self._published_doc_files()
        }
        for expected in (
            os.path.join("apex", "www", "fleet-os.html"),
            os.path.join("apex", "www", "masar-supervisor.html"),
            os.path.join("apex", "hooks.py"),
            os.path.join("docs", "WORKSPACE-DESIGN.md"),
            os.path.join("docs", "training", "safety.md"),
            "README.md",
        ):
            self.assertIn(expected, rels, f"the Arabic scan no longer reaches {expected}")

    def test_every_arabic_home_still_matches_a_scanned_file(self):
        """A home that matches nothing is dead code masquerading as an exemption —
        exactly how the two www entries survived while the scan skipped .html."""
        every = []
        for ext in SCANNED_SOURCE_EXTS:
            every += glob.glob(os.path.join(APP_ROOT, "**", f"*.{ext}"), recursive=True)
        unreachable = [home for home in ARABIC_HOMES if not any(home in p for p in every)]
        self.assertEqual(
            unreachable,
            [],
            "ARABIC_HOMES entry matches no shipped file — exercise it, retire it, "
            f"or move it to OPTIONAL_ARABIC_HOMES: {unreachable}",
        )

    def test_no_arabic_in_published_code_or_metadata(self):
        """Keep Arabic in supported localization surfaces, not published source."""
        offenders = []
        for path in self._source_files() + self._published_doc_files():
            try:
                with open(path, encoding="utf-8") as fh:
                    text = fh.read()
            except (OSError, UnicodeDecodeError):
                continue
            lines = [i + 1 for i, ln in enumerate(text.splitlines()) if ARABIC.search(ln)]
            if lines:
                offenders.append(f"{os.path.relpath(path, REPO_ROOT)}:{lines}")
        self.assertEqual(
            sorted(offenders),
            [],
            "Arabic found in published source or documentation — move it to "
            f"translations/ar.csv: {sorted(offenders)}",
        )


# [#i460py]
INTERNAL_MARKERS = re.compile(
    r"(T-\d{2,}|\bterminal-\d|\bTODO\b|\bFIXME\b|\bHACK\b|\bWIP\b|\bskeptic|by terminal)",
    re.IGNORECASE,
)
_METADATA_TEXT_KEYS = {"description", "label", "documentation", "options"}


class TestNotificationCompanionModule(unittest.TestCase):
    """Every is_standard Notification dir must carry its <name>.py companion.

    When a standard Notification fires, Frappe imports
    `<app>.<module>.notification.<slug>.<slug>` (Notification.load_standard_properties
    → get_doc_module). A JSON-only dir raises ModuleNotFoundError mid-send; because
    alerts fire inside the document's try/except hook, the exception silently rolls
    back the parent insert. Seven dirs shipped JSON-only (fixed here); this guard
    stops a new one regressing — it bites the moment the notification is enabled.
    """

    def _notification_dirs(self):
        """(rel_dir, slug) for every shipped is_standard Notification dir."""
        out = []
        for fp in glob.glob(
            os.path.join(APP_ROOT, "*", "notification", "*", "*.json"), recursive=False
        ):
            if "node_modules" in fp:
                continue
            try:
                with open(fp, encoding="utf-8") as fh:
                    data = json.load(fh)
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(data, dict) or data.get("doctype") != "Notification":
                continue
            if not data.get("is_standard"):
                continue
            d = os.path.dirname(fp)
            out.append((os.path.relpath(d, APP_ROOT), os.path.basename(d)))
        return out

    def test_scan_finds_notifications(self):
        slugs = {slug for _, slug in self._notification_dirs()}
        self.assertIn(
            "salis___trip_scheduled",
            slugs,
            "Notification scan found nothing — parser broke",
        )

    def test_every_standard_notification_has_py_companion(self):
        missing = []
        for rel, slug in self._notification_dirs():
            d = os.path.join(APP_ROOT, rel)
            if not os.path.exists(os.path.join(d, slug + ".py")):
                missing.append(rel + "/" + slug + ".py")
            if not os.path.exists(os.path.join(d, "__init__.py")):
                missing.append(rel + "/__init__.py")
        self.assertEqual(
            missing,
            [],
            "is_standard Notification dir missing its companion module "
            f"(ModuleNotFoundError on fire → silent parent rollback): {sorted(missing)}",
        )


class TestNoInternalMarkersInMetadata(unittest.TestCase):
    def test_user_facing_metadata_has_no_dev_process_text(self):
        """DocType descriptions / labels / Select options must not carry internal
        dev-process text (a task id, a dev-terminal ref, a TODO, "by terminal", ...)
        — that would surface internal workflow to operators (T-128 / publication
        hygiene). The tree is clean today; this fails the build on a future leak."""
        offenders = []
        for path in glob.glob(os.path.join(APP_ROOT, "**", "*.json"), recursive=True):
            if (os.sep + "node_modules" + os.sep in path) or (
                os.sep + "print_format" + os.sep in path
            ):
                continue
            try:
                with open(path, encoding="utf-8") as fh:
                    payload = json.load(fh)
            except (OSError, ValueError):
                continue
            rel = os.path.relpath(path, APP_ROOT)

            def visit(obj, key=None):
                if isinstance(obj, dict):
                    for k, v in obj.items():
                        visit(v, k)
                elif isinstance(obj, list):
                    for item in obj:
                        visit(item, key)
                elif isinstance(obj, str) and key in _METADATA_TEXT_KEYS:
                    found = INTERNAL_MARKERS.search(obj)
                    if found:
                        offenders.append(f"{rel} [{key}] <{found.group(0)}>")

            visit(payload)
        self.assertEqual(
            sorted(offenders),
            [],
            f"internal dev-process text in user-facing metadata: {sorted(offenders)}",
        )


class TestPrintFormatGuards(unittest.TestCase):
    """Static guards for three print-format fixes (no live site needed).

    A Jinja print format renders on the server; an unguarded lookup or a missing
    translation wrapper only shows up when an operator prints a real edge-case doc.
    These checks read the shipped .html templates and lock the fixes in source.
    """

    ROOM_LABEL = os.path.join(
        APP_ROOT, "habitat", "print_format", "accommodation_room_label",
        "accommodation_room_label.html",
    )
    QR_POSTER = os.path.join(
        APP_ROOT, "habitat", "print_format", "accommodation_qr_location_poster",
        "accommodation_qr_location_poster.html",
    )
    FUEL_VOUCHER = os.path.join(
        APP_ROOT, "salis", "print_format", "fuel_claim_voucher",
        "fuel_claim_voucher.html",
    )

    def _read(self, path):
        self.assertTrue(os.path.exists(path), f"print format missing: {path}")
        with open(path, encoding="utf-8") as fh:
            return fh.read()

    def test_room_label_building_lookup_cannot_raise(self):
        """P-008: an empty OR dangling `building` link must not abort the print.

        `frappe.get_doc("Building", doc.building)` raises
        DoesNotExistError both when the link is unset and when it points at a
        deleted record. The template must use a non-raising lookup (db.get_value
        guarded on `doc.building`) so the label still renders with a blank name.
        """
        html = self._read(self.ROOM_LABEL)
        self.assertNotIn(
            'frappe.get_doc("Building"',
            html,
            "room label still uses get_doc — raises on empty/dangling building link",
        )
        self.assertIn(
            'frappe.db.get_value("Building"',
            html,
            "room label must look up the building name via non-raising db.get_value",
        )
        self.assertIn("if doc.building else None", html, "building lookup must be guarded on doc.building")
        # [#ovmfuy]
        self.assertNotRegex(
            html, r"\bbuilding\.building_name\b",
            "render must not dereference a possibly-None building doc",
        )

    def test_qr_poster_user_strings_are_translatable(self):
        """P-009: every user-facing QR-poster string must go through `_()`.

        Hardcoded English never reaches ar.csv, so the poster prints English on an
        Arabic site. Assert each visible label is wrapped and brace-free.
        """
        html = self._read(self.QR_POSTER)
        required = [
            '_("Need Help? Scan to Report")',
            '_("Resident Support Services")',
            '_("Location Reference")',
            '_("Site")',
            '_("Building")',
            '_("Room")',
            '_("Ref")',
            '_("N/A")',
            '_("Point your phone camera at the QR code to open the request form.")',
            '_("For life or safety emergencies, contact the accommodation supervisor directly.")',
        ]
        missing = [s for s in required if s not in html]
        self.assertEqual(missing, [], f"QR poster strings not wrapped in _(): {missing}")
        # [#k7p94t]
        for m in re.finditer(r'_\(\s*"([^"]*)"\s*\)', html):
            self.assertNotRegex(
                m.group(1), r"\{",
                f"static translatable label must be placeholder-free: {m.group(1)!r}",
            )

    def test_fuel_voucher_litres_use_locale_number_format(self):
        """P-010: litre Floats must print through frappe.format, not raw.

        Raw `{{ doc.claimed_litres }}` emits an unformatted number (no thousands
        separator / locale precision). Each litre measure must pass through
        frappe.format with a Float/Currency fieldtype.
        """
        html = self._read(self.FUEL_VOUCHER)
        for field in ("claimed_litres", "consumed_litres", "variance_litres"):
            self.assertRegex(
                html,
                r"frappe\.format\(\s*doc\." + field,
                f"{field} must render via frappe.format for locale number formatting",
            )
        # [#74035w]
        for field in ("claimed_litres", "consumed_litres", "variance_litres"):
            self.assertNotRegex(
                html,
                r"\{\{\s*doc\." + field + r"(\s*or\s*0)?\s*\}\}",
                f"{field} printed raw without frappe.format",
            )


TRACKED_MIXED_INDENT = frozenset(
    {
        "apex/salis/api/driver_portal/__init__.py",
        "apex/salis/api/driver_portal/attendance.py",
        "apex/salis/api/driver_portal/boarding.py",
        "apex/salis/api/driver_portal/clearance.py",
        "apex/salis/api/driver_portal/execution.py",
        "apex/salis/api/driver_portal/fuel.py",
        "apex/salis/api/driver_portal/home.py",
        "apex/salis/api/driver_portal/notifications.py",
        "apex/salis/api/driver_portal/profile.py",
        "apex/salis/api/driver_portal/support.py",
        "apex/salis/api/driver_portal/test_driver_portal.py",
        "apex/salis/api/driver_portal/trips.py",
        "apex/salis/api/web_push.py",
        "apex/tests/test_b5_role_workspaces.py",
    }
)

_NOT_INDENTATION = frozenset(
    {tokenize.INDENT, tokenize.DEDENT, tokenize.ENDMARKER, tokenize.ENCODING}
)


class TestIndentationConsistency(unittest.TestCase):
    """A file must indent with tabs or with spaces, never both.

    The repo runs two styles on purpose: 81 files are tab-indented in the
    Frappe house style and 695 are four-space, and .editorconfig still declares
    tab. Neither is wrong, so this guard never judges which one a file picked —
    only that it picked one. A file that runs both renders at a different width
    in every reader whose tab stop is not four, and the mixed block is invisible
    in review because the characters look identical.

    Why this is a test and not a ruff rule: ruff's tab rule (W191) is a
    style vote, not a consistency check — it fires on all 5867 tab-indented
    lines across 97 files, which is a red nobody would keep. E101
    (mixed-spaces-and-tabs) only catches a single line that mixes both
    characters in one indent, so it scored zero on the file that provoked this
    guard even while that file ran 42 tab lines against 589 space ones. Neither
    rule expresses "one style per file", so the check lives here.

    TRACKED_MIXED_INDENT freezes the files that already mix, so this lands at
    zero new failures. It is not a permanent exemption: the stale-entry test
    fails once an entry is cleaned up, so the list can only shrink.
    """

    @staticmethod
    def _indent_styles(source):
        """{"tab": [lines], "space": [lines]} for the LOGICAL lines of `source`.

        Only the leading whitespace of a physical line that begins a logical
        line counts. Continuation lines inside brackets and the interior of a
        multi-line string never start one, so a space-aligned continuation in a
        tab file — and a tab inside a string or docstring — is correctly not an
        indentation defect.
        """
        lines = source.splitlines()
        found = {"tab": [], "space": []}
        at_line_start = True
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type in (tokenize.NEWLINE, tokenize.NL):
                at_line_start = True
                continue
            if token.type in _NOT_INDENTATION:
                continue
            if not at_line_start:
                continue
            at_line_start = False
            row = token.start[0]
            text = lines[row - 1]
            indent = text[: len(text) - len(text.lstrip(" \t"))]
            if "\t" in indent:
                found["tab"].append(row)
            elif indent:
                found["space"].append(row)
        return found

    def _tracked_python_files(self):
        """Every tracked .py file, because "shipped" means what git ships."""
        listed = subprocess.run(
            ["git", "-C", REPO_ROOT, "ls-files", "-z", "--", "*.py"],
            capture_output=True,
            check=True,
        ).stdout.decode("utf-8")
        return sorted(p for p in listed.split("\0") if p)

    def _mixed_files(self):
        mixed = {}
        for rel in self._tracked_python_files():
            path = os.path.join(REPO_ROOT, rel)
            try:
                with open(path, encoding="utf-8") as fh:
                    source = fh.read()
                styles = self._indent_styles(source)
            except (OSError, UnicodeDecodeError, SyntaxError, tokenize.TokenError):
                continue
            if styles["tab"] and styles["space"]:
                mixed[rel] = styles
        return mixed

    def test_scan_reads_the_package(self):
        """Anti-vacuity: a broken scan must not pass by finding nothing."""
        found = self._tracked_python_files()
        self.assertIn(
            "apex/tests/test_release_hygiene.py",
            found,
            f"python scan missed this very file; saw {len(found)} files",
        )

    def test_no_file_mixes_tabs_and_spaces(self):
        offenders = []
        for rel, styles in sorted(self._mixed_files().items()):
            if rel in TRACKED_MIXED_INDENT:
                continue
            minority = min(styles, key=lambda k: len(styles[k]))
            majority = "tab" if minority == "space" else "space"
            offenders.append(
                f"{rel}:{styles[minority][0]} ({len(styles[minority])} {minority}-indented "
                f"vs {len(styles[majority])} {majority}-indented)"
            )
        self.assertEqual(
            offenders,
            [],
            "a python file indents with both tabs and spaces — pick the style "
            "already dominant in that file and reindent the minority: "
            + "; ".join(offenders),
        )

    def test_no_stale_mixed_indent_entry(self):
        """An entry that got cleaned up must leave, so the debt can only shrink."""
        mixed = set(self._mixed_files())
        stale = sorted(TRACKED_MIXED_INDENT - mixed)
        self.assertEqual(
            stale,
            [],
            "these files no longer mix indentation — drop them from "
            f"TRACKED_MIXED_INDENT so they stay clean: {stale}",
        )


if __name__ == "__main__":
    unittest.main()
