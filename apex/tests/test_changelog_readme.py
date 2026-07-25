# Copyright (c) 2026, AFMCO and contributors
"""change_log/README.md must link every version popup — no skipped versions.

The README is a derived mirror of the per-version notes under change_log/v*/.
This guard keeps it complete: every shipped version note must have a link in
the README, so a new release that forgets to add its line fails the build.
"""

import glob
import os
import re
import unittest

APP_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
CHANGE_LOG = os.path.join(APP_ROOT, "change_log")
ARABIC = re.compile(r"[؀-ۿ]")


class TestChangelogReadmeComplete(unittest.TestCase):
    def _readme(self):
        with open(os.path.join(CHANGE_LOG, "README.md"), encoding="utf-8") as fh:
            return fh.read()

    def test_every_popup_is_linked(self):
        readme = self._readme()
        popups = [
            os.path.relpath(path, CHANGE_LOG)
            for path in glob.glob(os.path.join(CHANGE_LOG, "v*", "v*_*_*.md"))
        ]
        self.assertTrue(popups, "no version popups found under change_log/v*/")
        missing = [path for path in popups if f"({path})" not in readme]
        self.assertEqual(
            sorted(missing),
            [],
            "change_log/README.md is missing links for these version popups "
            f"(regenerate the mirror): {sorted(missing)}",
        )

    def test_readme_is_english(self):
        # [#d3rf70]
        offenders = [ln for ln in self._readme().splitlines() if ARABIC.search(ln)]
        self.assertEqual(offenders, [], f"Arabic in change_log/README.md: {offenders[:5]}")


# [#kc1808]
BANNED_REGISTER = re.compile(
    r"""(?ix)
      \(\s*\d+\s+tests?\s*\)            # "(1601 tests)"
    | \b(?:full\s+|behaviou?ral\s+|automated\s+)?test\s+suite\b
    | \bfull\s+suite\b
    | \bsuite\s+green\b
    | \bgreen\s+(?:test\s+)?suite\b
    | \btest\s+coverage\b
    | \bbehaviou?ral\s+tests?\b
    | \bautomated\s+tests?\b
    | \bproper\s+tests?\b
    | \btest[-\s]isolation\b
    | \btest[-\s]environment\b
    | \btest[-\s]only\b
    | \bscope-tested\b
    | \bcontinuous\s+integration\b
    | \bregression\b
    | \bscanner\b
    | \bcorrection\s+wave\b
    | \bhotfix\b
    | \blatent\s+bug
    | \bruntime\s+check\b
    | \bdirect\s+scan\b
    | \boverstat
    | \bschema\s+rename\b
    | \bQA\b
    """,
    re.VERBOSE,
)

VERSION_IN_TITLE = re.compile(r"\b(\d+\.\d+(?:\.\d+)?)\b")
POPUP_FILE = re.compile(r"^v(\d+)_(\d+)_(\d+)\.md$")


def _popup_files():
    """Every shipped version popup file (change_log/v*/vX_Y_Z.md)."""
    out = []
    for fp in glob.glob(os.path.join(CHANGE_LOG, "v*", "v*_*_*.md")):
        if POPUP_FILE.match(os.path.basename(fp)):
            out.append(fp)
    return out


class TestChangelogRegisterVoice(unittest.TestCase):
    """No popup may carry internal-QA / build-process register.

    The FIX/SECURITY register is brief and never narrates: no test counts, no
    scanner/test/CI vocabulary, no cause narration or audit-reply tone. A leak
    here (e.g. "full test suite green (1601 tests)") shipped internal QA voice to
    operators; this guard rejects it so a future entry cannot regress.
    """

    def test_scan_finds_popups(self):
        self.assertTrue(_popup_files(), "no version popups found under change_log/v*/")

    def test_no_qa_or_build_register_in_popups(self):
        offenders = []
        for fp in _popup_files():
            with open(fp, encoding="utf-8") as fh:
                text = fh.read()
            for m in BANNED_REGISTER.finditer(text):
                offenders.append(f"{os.path.relpath(fp, CHANGE_LOG)} <{m.group(0)!r}>")
        self.assertEqual(
            sorted(offenders),
            [],
            "internal-QA / build register in operator-facing changelog popup "
            f"(rewrite to plain user terms): {sorted(offenders)}",
        )


class TestFeedCoversPopups(unittest.TestCase):
    """Every popup version must have an entry in changelog.py `_RELEASES`.

    `_RELEASES` feeds the "What's New" sidebar; it had drifted and omitted
    shipped versions. This guard keeps the feed complete: a new (or restored)
    popup with no matching feed title fails the build. Parsed from source so no
    live Frappe/site is needed.
    """

    CHANGELOG_PY = os.path.join(APP_ROOT, "apex_core", "utils", "changelog.py")

    def _feed_versions(self):
        """Normalised (3-part) version set drawn from _RELEASES titles."""
        with open(self.CHANGELOG_PY, encoding="utf-8") as fh:
            text = fh.read()
        versions = set()
        for m in re.finditer(r'"title":\s*(["\'])(.*?)\1', text, re.DOTALL):
            for v in VERSION_IN_TITLE.findall(m.group(2)):
                parts = v.split(".")
                if len(parts) == 2:  # [#5r0z70]
                    versions.add(f"{parts[0]}.{parts[1]}.0")
                versions.add(v)
        return versions

    def test_feed_parser_finds_titles(self):
        # Sentinel is the 2.0.0 floor: the shipped feed and the popup dirs both
        # start there, so a pre-2.0 sentinel would re-require retired history.
        self.assertIn("2.0.0", self._feed_versions(), "feed title parse broke")

    def test_every_popup_version_is_in_releases(self):
        feed = self._feed_versions()
        missing = []
        for fp in _popup_files():
            maj, minr, pat = POPUP_FILE.match(os.path.basename(fp)).groups()
            ver = f"{int(maj)}.{int(minr)}.{int(pat)}"
            if ver not in feed:
                missing.append(f"{os.path.relpath(fp, CHANGE_LOG)} -> {ver}")
        self.assertEqual(
            sorted(missing),
            [],
            "popup versions absent from changelog.py _RELEASES feed "
            f"(add the missing feed entries): {sorted(missing)}",
        )


# [#a081x1]
CHANGELOG_PY = os.path.join(APP_ROOT, "apex_core", "utils", "changelog.py")
FEED_TITLE = re.compile(r'"title":\s*(["\'])(.*?)\1', re.DOTALL)
README_LINK = re.compile(r"\[(\d+\.\d+(?:\.\d+)?)\]\((v\d+/v\d+_\d+_\d+\.md)\)")


def _ver_key(version):
    return [int(part) for part in version.split(".")]


def _normalise(version):
    """A 2-part release title ("Apex 2.1") names the X.Y.0 note on disk."""
    parts = version.split(".")
    return version if len(parts) == 3 else f"{parts[0]}.{parts[1]}.0"


def _popup_versions():
    """Versions that have a shipped note on disk under change_log/v*/."""
    out = set()
    for fp in _popup_files():
        maj, minr, pat = POPUP_FILE.match(os.path.basename(fp)).groups()
        out.add(f"{int(maj)}.{int(minr)}.{int(pat)}")
    return out


def _readme_links():
    """Every (version, link target) pair indexed in change_log/README.md."""
    with open(os.path.join(CHANGE_LOG, "README.md"), encoding="utf-8") as fh:
        return [(_normalise(v), target) for v, target in README_LINK.findall(fh.read())]


def _feed_release_versions():
    """One version per _RELEASES entry: the first version its title declares.

    Deliberately first-match rather than every match — a title may mention an
    unrelated number ("ZATCA 2.0 invoicing"), and only the leading one names the
    release. Returned as a list so a duplicated entry stays visible.
    """
    with open(CHANGELOG_PY, encoding="utf-8") as fh:
        text = fh.read()
    out = []
    for match in FEED_TITLE.finditer(text):
        found = VERSION_IN_TITLE.findall(match.group(2))
        if found:
            out.append(_normalise(found[0]))
    return out


def _disagreements(notes, readme, feed):
    """Versions absent from at least one of the three shipped release sources.

    Symmetric on purpose: the pre-existing guards above only run notes -> README
    and notes -> feed, so a README line or a feed entry for a release with no note
    on disk passed unseen. This compares all three sets in both directions at once.
    """
    out = []
    sources = (("notes", notes), ("README", readme), ("feed", feed))
    for version in sorted(notes | readme | feed, key=_ver_key):
        absent = [name for name, known in sources if version not in known]
        if absent:
            out.append(f"{version} missing from {'+'.join(absent)}")
    return out


class TestReleaseSourcesAgree(unittest.TestCase):
    """The notes on disk, the README index and the _RELEASES feed must match.

    A release carried by one source and not the others is the drift that broke
    the build when 2.1.2 shipped a note with no feed entry. All three are edited
    by hand at release time, so nothing but this guard keeps them aligned.
    """

    def test_the_three_release_sources_carry_the_same_versions(self):
        notes = _popup_versions()
        readme = {version for version, _ in _readme_links()}
        feed = set(_feed_release_versions())
        self.assertEqual(
            _disagreements(notes, readme, feed),
            [],
            "change_log notes, change_log/README.md and changelog.py _RELEASES "
            "disagree. Add the release to whichever source omits it — a shipped "
            "note is product history and is never removed to force agreement.",
        )

    def test_every_readme_link_resolves_to_the_note_it_names(self):
        offenders = []
        for version, target in _readme_links():
            if not os.path.exists(os.path.join(CHANGE_LOG, target)):
                offenders.append(f"{version} -> {target} (no such file)")
            elif os.path.basename(target) != f"v{_normalise(version).replace('.', '_')}.md":
                offenders.append(f"{version} -> {target} (target names another release)")
        self.assertEqual(
            sorted(offenders), [], f"broken README release links: {sorted(offenders)}"
        )

    def test_no_version_is_listed_twice_in_the_feed(self):
        feed = _feed_release_versions()
        dupes = sorted({v for v in feed if feed.count(v) > 1})
        self.assertEqual(
            dupes, [], f"_RELEASES carries more than one entry per version: {dupes}"
        )

    def test_guard_detects_a_release_missing_from_any_one_source(self):
        """Guard-of-the-guard: prove the scans are populated and the comparison bites."""
        notes, readme = _popup_versions(), {v for v, _ in _readme_links()}
        feed = set(_feed_release_versions())
        for name, found in (("notes", notes), ("README", readme), ("feed", feed)):
            self.assertGreaterEqual(len(found), 2, f"{name} scan returned too little")
        self.assertEqual(_disagreements({"9.9.9"}, {"9.9.9"}, {"9.9.9"}), [])
        # Punch the hole in each slot in turn, so no slot is silently unchecked.
        gap = min(notes, key=_ver_key)
        for slots in ((notes - {gap}, readme, feed), (notes, readme - {gap}, feed),
                      (notes, readme, feed - {gap})):
            self.assertNotEqual(_disagreements(*slots), [], f"undetected hole: {gap}")


if __name__ == "__main__":
    unittest.main()
