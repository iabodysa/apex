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


if __name__ == "__main__":
    unittest.main()
