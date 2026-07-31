"""A print format may not print a record name the rename retired.

A-288: the checkout clearance slip -- a sheet physically handed to a worker at
checkout -- titled itself "Accommodation Checkout Clearance" for the whole life
of the rename, and every gate stayed green. scripts/check_translations.py owns
the retired-name check, but it runs on the extractor's own harvest of _() CALLS
(see its module docstring), so a name written as a BARE template literal is
invisible to it. That is exactly how a print format hides: its headings are
plain HTML text, not translate calls, so the one surface a worker physically
holds was the one surface with no retired-name coverage at all.

This guard closes that hole by scanning the template TEXT instead of the call
harvest. It is colocated with the print formats rather than living in
apex/tests/ because the central directory is a shrink-only ratchet.

Scope is the template body only. The Print Format RECORD name (the JSON `name`)
is a stored identifier that other records point at, so retiring it needs a
rename patch rather than an edit; _RECORD_NAME_DEBT tracks any that still carry
a retired name so the exemption stays visible instead of silent. The last entry
was drained by patches/v2_0/rename_checkout_clearance_print_format.py, so the set
is empty and test_no_undeclared_retired_record_name now covers every shipped
print format with no exemption at all.
"""

from __future__ import annotations

import glob
import importlib.util
import json
import os
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
# apex/habitat/print_format -> apex/habitat -> apex -> repo root
_APP_ROOT = os.path.dirname(os.path.dirname(_HERE))
_REPO_ROOT = os.path.dirname(_APP_ROOT)
_GATE = os.path.join(_REPO_ROOT, "scripts", "check_translations.py")

# Mirrors scripts/check_translations.py RETIRED_NAMES; test_matches_the_shipped_gate
# fails if the two drift, so neither list can be updated alone.
_RETIRED_NAMES = {
    "Accommodation Assignment": "Housing Assignment",
    "Accommodation Building": "Building",
    "Accommodation Checkout": "Housing Checkout",
    "Accommodation Lease": "Lease",
    "Accommodation Resident Request": "Resident Request",
    "Habitat Safety Incident": "Safety Incident",
    "Salis Portal Theme": "Driver Portal Theme",
}

# Print Format record names still carrying a retired name. A record name is a
# link target, so draining one needs a rename patch -- not a text edit. Staff
# read these in the print dropdown; no worker reads them on paper. Now EMPTY: keep
# it that way by shipping the patch, never by adding an entry here.
_RECORD_NAME_DEBT = frozenset()


def _templates() -> list:
    """(relative path, text) for every print-format template in the app."""
    pattern = os.path.join(_APP_ROOT, "*", "print_format", "*", "*.html")
    found = []
    for path in sorted(glob.glob(pattern)):
        with open(path, encoding="utf-8") as fh:
            found.append((os.path.relpath(path, _APP_ROOT), fh.read()))
    return found


def _metadata() -> list:
    pattern = os.path.join(_APP_ROOT, "*", "print_format", "*", "*.json")
    found = []
    for path in sorted(glob.glob(pattern)):
        with open(path, encoding="utf-8") as fh:
            found.append((os.path.relpath(path, _APP_ROOT), json.load(fh)))
    return found


def _hits(text: str) -> list:
    return [(old, new) for old, new in _RETIRED_NAMES.items() if old in text]


class TestPrintFormatRetiredNames(unittest.TestCase):
    def test_no_retired_name_in_any_template(self):
        """The text a worker reads on paper names only records that still ship."""
        violations = [
            f"  {rel}: {old!r} -> {new!r}"
            for rel, text in _templates()
            for old, new in _hits(text)
        ]
        self.assertEqual(
            violations,
            [],
            "A print format prints a record name the rename retired, so the "
            "worker holding the sheet reads a record that no longer exists. "
            "Use the replacement name:\n" + "\n".join(violations),
        )

    def test_no_print_format_is_exempt(self):
        """The exemption set must stay empty.

        A rename patch and the record's JSON are ONE change -- import_doc resolves the
        record by the JSON's ``name`` and delete+inserts it, so a JSON left on the old
        key is undone by the next migrate. That makes "queue the patch later" an
        unshippable plan, and an entry here would be the way to ship it anyway.
        """
        self.assertEqual(
            set(_RECORD_NAME_DEBT),
            set(),
            "a print format record name was exempted instead of renamed. Ship the "
            "rename patch and the JSON name in the SAME change; there is no valid "
            "intermediate state to record here.",
        )

    def test_record_name_debt_is_real(self):
        """A debt entry names a print format that exists and is still in debt.

        Without this the exemption outlives the defect: the rename patch lands,
        the record name is clean, and the entry silently keeps blessing a name
        nobody ships anymore.
        """
        names = {meta.get("name") for _, meta in _metadata()}
        for entry in sorted(_RECORD_NAME_DEBT):
            self.assertIn(
                entry, names, f"_RECORD_NAME_DEBT names no shipped print format: {entry!r}"
            )
            self.assertTrue(
                _hits(entry),
                f"{entry!r} no longer carries a retired name -- drop it from _RECORD_NAME_DEBT.",
            )

    def test_no_undeclared_retired_record_name(self):
        """Any NEW print format whose record name is retired must be caught."""
        violations = [
            f"  {rel}: {meta.get('name')!r} -> {new!r}"
            for rel, meta in _metadata()
            if meta.get("name") not in _RECORD_NAME_DEBT
            for _old, new in _hits(meta.get("name") or "")
        ]
        self.assertEqual(
            violations,
            [],
            "A print format RECORD name carries a retired name. Renaming a "
            "record needs a patch; add it to _RECORD_NAME_DEBT with that patch "
            "queued:\n" + "\n".join(violations),
        )

    def test_matches_the_shipped_gate(self):
        """One retired-name list, two enforcement points -- they may not drift."""
        if not os.path.exists(_GATE):
            self.skipTest("scripts/check_translations.py is not part of an installed package")
        spec = importlib.util.spec_from_file_location("_apex_translation_gate", _GATE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(
            _RETIRED_NAMES,
            module.RETIRED_NAMES,
            "_RETIRED_NAMES drifted from scripts/check_translations.py RETIRED_NAMES. "
            "Update both, or this guard stops covering a name the gate retired.",
        )

    def test_guard_actually_detects(self):
        """Guard-of-the-guard: prove the scan reaches files and the match works.

        An empty glob makes every assertion above pass vacuously, which is the
        failure mode that let A-288 ship in the first place.
        """
        templates = _templates()
        self.assertGreater(len(templates), 10, "template scan returned implausibly few files")
        self.assertEqual(len(templates), len(_metadata()), "every template needs its JSON")
        # The exact A-288 defect, as a bare literal, must be reported.
        planted = '<h1>Accommodation Checkout Clearance</h1>'
        self.assertEqual(_hits(planted), [("Accommodation Checkout", "Housing Checkout")])
        # A clean heading must not be.
        self.assertEqual(_hits('<h1>{{ _("Housing Checkout Clearance") }}</h1>'), [])


if __name__ == "__main__":
    unittest.main()
