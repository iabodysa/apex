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
REPO_ROOT = os.path.dirname(APP_ROOT)
AR_CSV = os.path.join(APP_ROOT, "translations", "ar.csv")
PATCHES_DIR = os.path.join(APP_ROOT, "patches")
HOOKS_PY = os.path.join(APP_ROOT, "hooks.py")

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
        """Every file under docs/, plus README.md — no extension filter, so a
        published page cannot dodge the scan by not being Markdown."""
        paths = glob.glob(os.path.join(PUBLISHED_DOCS_DIR, "**", "*"), recursive=True)
        return [p for p in paths if os.path.isfile(p)] + [PUBLISHED_README]

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


if __name__ == "__main__":
    unittest.main()
