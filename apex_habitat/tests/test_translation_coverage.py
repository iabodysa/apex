# Copyright (c) 2026, AFMCO and contributors
"""Arabic-coverage guard for the desk + www surfaces.

`frappectl translates` enforces ar.csv coverage of every ``_()``/``__()`` call,
but it runs locally — CI does not, and its missing-report also skips paren/`&`
strings. A desk-JS or www string added without an ar.csv row therefore renders
English inside the Arabic UI with nothing to catch it. This test locks every
Salis / Habitat / Apex-Core desk page and the www pages: each translate-call
string literal must have a non-empty ar.csv entry.

Guards the class fixed in 1.54.19 (``__("Exported {0} vehicles", [n])`` on the
Fleet Control page had no Arabic — a multi-arg call the scanner skipped) and
extended app-wide in 1.54.20.
"""

import csv
import glob
import re

import frappe
from frappe.tests.utils import FrappeTestCase

APP = frappe.get_app_path("apex_habitat")

# Start of a translate call: _( , frappe._( , __(  — then one or more string
# literals concatenated to it (Python "a" "b" or JS "a" + "b"), which is the
# runtime msgid. Mirrors the frappectl translates scanner so the two agree.
_CALL = re.compile(r"(?:frappe\.)?_\(|__\(")
_NEXT_LITERAL = re.compile(r"""\s*\+?\s*(['"])((?:\\.|(?!\1).)*?)\1""")


def _translate_strings(text):
    out = []
    for call in _CALL.finditer(text):
        pos = call.end()
        parts = []
        while (lit := _NEXT_LITERAL.match(text, pos)) is not None:
            parts.append(lit.group(2))
            pos = lit.end()
        if parts:
            out.append("".join(parts))
    return out


def _is_ui_text(s):
    # Skip empty / pure-placeholder / punctuation-only literals (e.g. "{0}", "—").
    return bool(re.search(r"[A-Za-z]", s))


class TestTranslationCoverage(FrappeTestCase):
    def _ar(self):
        rows = {}
        with open(f"{APP}/translations/ar.csv", encoding="utf-8", newline="") as h:
            for r in csv.reader(h):
                if len(r) >= 2 and r[0].strip():
                    rows[r[0]] = r[1]
        return rows

    def test_desk_surfaces_have_arabic(self):
        ar = self._ar()
        files = (
            glob.glob(f"{APP}/salis/**/*.js", recursive=True)
            + glob.glob(f"{APP}/habitat/**/*.js", recursive=True)
            + glob.glob(f"{APP}/apex_core/**/*.js", recursive=True)
            + glob.glob(f"{APP}/www/*.html")
            + glob.glob(f"{APP}/www/*.py")
        )
        missing = []
        for f in files:
            try:
                text = open(f, encoding="utf-8").read()
            except OSError:
                continue
            for s in _translate_strings(text):
                if _is_ui_text(s) and not (ar.get(s) or "").strip():
                    rel = f.split("/apex_habitat/", 1)[-1]
                    missing.append(f"{rel}: {s!r}")
        self.assertEqual(
            sorted(set(missing)),
            [],
            f"desk/www UI strings with no Arabic translation: {sorted(set(missing))}",
        )
