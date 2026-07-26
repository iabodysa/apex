"""A print format pins its language only if it prints both languages itself.

A-293 started from the reading that `default_print_language: "en"` on all thirteen
formats is uniformly wrong, because an attached copy takes that field
(frappe/email/doctype/notification/notification.py:441-444 -> frappe/__init__.py:2175,
`with print_language(lang or local.lang)`). Clearing it everywhere would have been
worse than leaving it: ten of the thirteen print English and Arabic side by side in
their own markup, and several pair a `_()` sentence with a hand-written Arabic twin
right beneath it. Rendering those in Arabic resolves the `_()` half to Arabic too, so
the sheet loses its English column and repeats itself instead.

So the pin is load-bearing for a bilingual sheet and wrong for a translated one, and
the rule is a property of the TEMPLATE, not a per-file preference:

    Arabic in the template  <=>  default_print_language == "en"

The three formats with no Arabic in their markup carry no pin, so the reader's
language wins; they must also take their `dir` from is_rtl(), or an Arabic render
lays out left-to-right.

Colocated with the print formats because apex/tests/ is a shrink-only ratchet, and
stdlib-only so it grades the source tree without a bench.
"""

from __future__ import annotations

import glob
import json
import os
import re
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
# apex/habitat/print_format -> apex/habitat -> apex
_APP_ROOT = os.path.dirname(os.path.dirname(_HERE))

# Arabic block + supplement + presentation forms. Source strings are English-first
# (CLAUDE.md), so any Arabic character in a template is a hand-written bilingual
# gloss, never the argument of a _() call.
_ARABIC = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")

# The pin that makes a bilingual sheet render its English column.
_PIN = "en"


def _formats() -> list[tuple[str, str, dict]]:
    """(relative dir, template text, metadata) for every print format in the app."""
    pattern = os.path.join(_APP_ROOT, "*", "print_format", "*", "*.html")
    found = []
    for html_path in sorted(glob.glob(pattern)):
        json_path = html_path[: -len(".html")] + ".json"
        with open(html_path, encoding="utf-8") as fh:
            text = fh.read()
        with open(json_path, encoding="utf-8") as fh:
            meta = json.load(fh)
        found.append((os.path.relpath(os.path.dirname(html_path), _APP_ROOT), text, meta))
    return found


def _is_bilingual(text: str) -> bool:
    return bool(_ARABIC.search(text))


class TestPrintFormatLanguagePinning(unittest.TestCase):
    def test_bilingual_formats_stay_pinned(self):
        """A sheet that prints Arabic itself must keep its English column."""
        violations = [
            f"  {rel}: prints Arabic but default_print_language={meta.get('default_print_language')!r}"
            for rel, text, meta in _formats()
            if _is_bilingual(text) and meta.get("default_print_language") != _PIN
        ]
        self.assertEqual(
            violations,
            [],
            "A bilingual print format lost its language pin. Rendering it in Arabic "
            'resolves its _() strings to Arabic as well, so the sheet repeats itself '
            "and the English column disappears:\n" + "\n".join(violations),
        )

    def test_translated_formats_follow_the_reader(self):
        """A fully translated sheet must not pin a language over its reader."""
        violations = [
            f"  {rel}: no Arabic in the template but default_print_language="
            f"{meta.get('default_print_language')!r}"
            for rel, text, meta in _formats()
            if not _is_bilingual(text) and meta.get("default_print_language")
        ]
        self.assertEqual(
            violations,
            [],
            "A print format whose text is entirely _() pins a print language. An "
            "attached or downloaded copy takes that field, so an Arabic reader is "
            "handed English the template could have translated:\n" + "\n".join(violations),
        )

    def test_unpinned_formats_take_direction_from_the_reader(self):
        """No pin means the render language varies, so dir may not be hardcoded."""
        violations = [
            f"  {rel}: unpinned but its markup never calls is_rtl()"
            for rel, text, meta in _formats()
            if not meta.get("default_print_language") and "is_rtl()" not in text
        ]
        self.assertEqual(
            violations,
            [],
            "An unpinned print format renders in whatever language the reader has, "
            "so it must set dir from is_rtl(); otherwise Arabic lays out "
            "left-to-right:\n" + "\n".join(violations),
        )

    def test_guard_actually_detects(self):
        """Guard-of-the-guard: an empty glob would pass every assertion above."""
        formats = _formats()
        self.assertGreater(len(formats), 10, "print-format scan returned implausibly few files")
        # Both groups must be non-empty, or one assertion above is vacuous.
        bilingual = [rel for rel, text, _ in formats if _is_bilingual(text)]
        translated = [rel for rel, text, _ in formats if not _is_bilingual(text)]
        self.assertTrue(bilingual, "no bilingual format found -- detection is broken")
        self.assertTrue(translated, "no translated format found -- detection is broken")
        # The detector must split real template lines the way the rule assumes.
        self.assertTrue(_is_bilingual('<td class="ah-lbl">Date <span>التاريخ</span></td>'))
        self.assertFalse(_is_bilingual('<td class="ah-lbl">{{ _("Date") }}</td>'))


if __name__ == "__main__":
    unittest.main()
