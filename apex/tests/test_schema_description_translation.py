# Copyright (c) 2026, AFMCO and contributors
"""Arabic-coverage guard for DocType ``description`` prose, field and doctype-level.

A description is body text rendered under the input (or in the list-view empty
state), so an untranslated one shows English under an Arabic label.

``scripts/check_translations.py`` used to miss these entirely: ``is_candidate_text``
dropped any string over 180 characters, and a description is the one schema key that
routinely runs past that. The cap cut both ways — a long description was invisible to
MISSING, so it shipped untranslated on a green gate, and it was equally absent from
``used``, so translating it landed the row in STALE. That is fixed: ``description``
is now a DECLARED key there, exempt from the shape heuristics, because Frappe itself
harvests it (translate.py) and renders it through ``__()`` at any length.

This guard still earns its place beyond that gate: the gate drops ``&`` strings from
MISSING (``is_auto_translatable``), and it never checks a description for a ``{0}``
placeholder, which would reach the user unfilled.

REMAINDER is the tracked backlog, keyed by (schema path, fieldname) rather than by
the English text so that rewording a description does not false-red the suite. It is
now drained — every shipped description has an Arabic row. The set may only shrink.
"""

import csv
import glob
import json
import re

import frappe
from frappe.tests.utils import FrappeTestCase

APP = frappe.get_app_path("apex")

# Drained: the 28 entries tracked here all carry an Arabic row as of the cap fix.
REMAINDER: set[tuple[str, str | None]] = set()


def _descriptions():
    """Yield (relative schema path, fieldname, description) for every shipped DocType.

    A fieldname of None is the DocType's own description, which list_view.js renders
    through ``__()`` in the empty state and so needs Arabic just as much."""
    for path in sorted(glob.glob(f"{APP}/**/doctype/*/*.json", recursive=True)):
        try:
            payload = json.loads(open(path, encoding="utf-8").read())
        except (OSError, ValueError, UnicodeDecodeError):
            continue
        if not isinstance(payload, dict) or payload.get("doctype") != "DocType":
            continue
        rel = path[len(APP) + 1:]
        own = payload.get("description")
        if isinstance(own, str) and own.strip():
            yield rel, None, own.strip()
        for field in payload.get("fields") or []:
            if not isinstance(field, dict):
                continue
            text = field.get("description")
            if isinstance(text, str) and text.strip():
                yield rel, field.get("fieldname"), text.strip()


class TestSchemaDescriptionTranslation(FrappeTestCase):
    def _ar(self):
        rows = {}
        with open(f"{APP}/translations/ar.csv", encoding="utf-8", newline="") as handle:
            for row in csv.reader(handle):
                if len(row) >= 2 and row[0].strip():
                    rows[row[0]] = row[1]
        return rows

    def test_field_descriptions_have_arabic(self):
        ar = self._ar()
        untranslated = {
            (rel, fieldname)
            for rel, fieldname, text in _descriptions()
            if not (ar.get(text) or "").strip()
        }
        # key=str: a doctype-level entry sorts a None fieldname against a str one.
        new = sorted(untranslated - REMAINDER, key=str)
        self.assertEqual(
            new,
            [],
            "DocType descriptions with no Arabic row — an Arabic user sees "
            f"English body text under an Arabic label: {new}",
        )

    def test_remainder_entries_are_still_live(self):
        """Stops the backlog rotting: a removed or renamed field must leave REMAINDER."""
        live = {(rel, fieldname) for rel, fieldname, _ in _descriptions()}
        dead = sorted(REMAINDER - live, key=str)
        self.assertEqual(
            dead, [], f"REMAINDER names descriptions that no longer exist: {dead}"
        )

    def test_descriptions_carry_no_static_placeholder(self):
        """A description renders verbatim, so an unfilled {0} would reach the user."""
        braced = sorted(
            f"{rel}:{fieldname or '<doctype>'}"
            for rel, fieldname, text in _descriptions()
            if re.search(r"\{\d+\}", text)
        )
        self.assertEqual(braced, [], f"descriptions with a format placeholder: {braced}")
