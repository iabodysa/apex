# Copyright (c) 2026, AFMCO and contributors
"""Guard: every patch module on disk is accounted for in patches.txt.

A patch module that is on disk but in no patches.txt section never runs on a
migrate. That is sometimes correct (a demo seeder that must never touch a
customer site) and sometimes a shipped bug (a backfill everyone assumed was
wired). Nothing in the repo could previously tell the two apart, so this guard
forces every unregistered module to say WHY in its own docstring.

Four checks:

  1. TestPatchRegistration.test_every_module_is_registered_or_documented — every
     ``apex/patches/**/*.py`` (bar ``__init__.py``) is either an active entry in
     patches.txt or carries BOTH docstring markers:

         UNREGISTERED-PATCH: <why registering it would be wrong>
         COVERED-BY:         <what provides that state instead>

     A bare marker is not enough. Each reason must be real prose (length + word
     count floors, and a filler blacklist), so the exception cannot be granted by
     pasting a label. The markers must sit in the module DOCSTRING — a comment
     anywhere else does not count, because the reason has to be visible to anyone
     reading or ``help()``-ing the module.

  2. test_documented_exceptions_stay_rare — at most MAX_UNREGISTERED modules may
     claim the exception. The marker is an escape hatch for a handful of modules
     with a real reason, not a second, unreviewed way to ship patches.

  3. test_registered_modules_exist_on_disk — the reverse orphan: an entry in
     patches.txt with no module behind it. Frappe raises at migrate time on the
     import, so this catches a bad rename before a customer's migrate does.

  4. test_registered_module_carries_no_exception_marker — a module cannot be both
     registered AND documented-as-unregistered. Catches the marker being
     copy-pasted into a live patch, where it would read as a lie.

patches.txt is parsed with the SAME ``configparser`` call frappe uses
(``frappe/modules/patch_handler.py`` ``parse_as_configfile``) rather than a
hand-rolled line scanner, so "active entry" here means exactly what it means to
``bench migrate`` — a dotted path inside a comment is not a registration, and a
duplicate entry raises rather than silently double-counting.

Pure stdlib — no live site needed.
Run standalone:  python3 -m unittest tests.test_patch_registration_guard -v
"""

import ast
import configparser
import glob
import os
import re
import unittest

APP_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
REPO_ROOT = os.path.dirname(APP_ROOT)
PATCHES_DIR = os.path.join(APP_ROOT, "patches")
PATCHES_TXT = os.path.join(APP_ROOT, "patches.txt")

# [#pq4m7t] The escape hatch stays small on purpose: three modules earn it today
# (one no-op kept alive by after_install + a by-path test read, two demo seeders
# held out of the migrate path). Raising this ceiling is a reviewed decision, not
# a way to make a failing guard pass.
MAX_UNREGISTERED = 5

MARKER_WHY = "UNREGISTERED-PATCH:"
MARKER_COVERED_BY = "COVERED-BY:"

# [#w0e3hn] Anti-rubber-stamp floors. A reason short enough to fail these is a
# label, not an explanation.
_MIN_REASON_CHARS = 40
_MIN_REASON_WORDS = 6
_FILLER = re.compile(
    r"^(n/?a|none|nothing|tbd|todo|fixme|xxx|wip|see above|see below|see the docstring"
    r"|as above|obvious|not needed|no reason|by design|intentional|deliberate)\W*$",
    re.IGNORECASE,
)


def _registered_patches():
    """Active patches.txt entries, parsed exactly as frappe does.

    Mirrors frappe.modules.patch_handler.parse_as_configfile: allow_no_value (an
    entry is a bare path, not a key/value pair) and delimiters="\\n" (so a `:` in
    an `execute:` line is not read as a delimiter). Raises on a duplicate entry.
    """
    parser = configparser.ConfigParser(allow_no_value=True, delimiters="\n")
    parser.optionxform = str  # preserve case
    parser.read(PATCHES_TXT)
    entries = []
    for section in parser.sections():
        entries.extend(parser[section])
    return parser.sections(), entries


def _modules_on_disk():
    """{dotted path: filesystem path} for every patch module apex ships."""
    found = {}
    pattern = os.path.join(PATCHES_DIR, "**", "*.py")
    for path in sorted(glob.glob(pattern, recursive=True)):
        if os.path.basename(path) == "__init__.py":
            continue
        rel = os.path.relpath(path, REPO_ROOT)[: -len(".py")]
        found[rel.replace(os.sep, ".")] = path
    return found


def _docstring(path):
    with open(path, encoding="utf-8") as fh:
        try:
            tree = ast.parse(fh.read(), filename=path)
        except SyntaxError:
            return None
    return ast.get_docstring(tree)


def _marker_reason(docstring, label):
    """Text following `label` on its own docstring line, or None if absent."""
    if not docstring:
        return None
    for line in docstring.splitlines():
        stripped = line.strip()
        if stripped.startswith(label):
            return stripped[len(label) :].strip()
    return None


def _marker_problem(docstring, label):
    """Why `label` does not count as a documented exception, or None if it does."""
    reason = _marker_reason(docstring, label)
    if reason is None:
        return f"no `{label}` line in the module docstring"
    if _FILLER.match(reason):
        return f"`{label}` reason is filler, not an explanation: {reason!r}"
    if len(reason) < _MIN_REASON_CHARS or len(reason.split()) < _MIN_REASON_WORDS:
        return (
            f"`{label}` reason is too thin to review "
            f"(needs >={_MIN_REASON_CHARS} chars and >={_MIN_REASON_WORDS} words "
            f"on the marker line): {reason!r}"
        )
    return None


def _unregistered_modules():
    _, registered = _registered_patches()
    registered = set(registered)
    return {
        dotted: path
        for dotted, path in _modules_on_disk().items()
        if dotted not in registered
    }


class TestPatchRegistration(unittest.TestCase):
    def test_patches_txt_parses_with_the_expected_sections(self):
        """The guard is only meaningful if patches.txt parses the way migrate
        reads it. A duplicate entry or a mangled header raises here first."""
        sections, entries = _registered_patches()
        self.assertEqual(
            sections,
            ["pre_model_sync", "post_model_sync"],
            "patches.txt must keep exactly the two frappe patch-type sections, in "
            f"order; got {sections}",
        )
        self.assertTrue(entries, "patches.txt parsed to zero active entries")

    def test_every_module_is_registered_or_documented(self):
        """Either patches.txt runs it on migrate, or the module states why not."""
        offenders = []
        for dotted, path in sorted(_unregistered_modules().items()):
            docstring = _docstring(path)
            problems = [
                p
                for p in (
                    _marker_problem(docstring, MARKER_WHY),
                    _marker_problem(docstring, MARKER_COVERED_BY),
                )
                if p
            ]
            if problems:
                rel = os.path.relpath(path, REPO_ROOT)
                offenders.append(f"  {rel} ({dotted}):\n" + "\n".join(f"      - {p}" for p in problems))

        self.assertEqual(
            offenders,
            [],
            "Patch module on disk that no patches.txt section registers and that "
            "does not document why. It will never run on a migrate — which is a "
            "silent bug unless it is deliberate. Either add it to the right "
            f"patches.txt section, or add both markers to its docstring:\n"
            f"    {MARKER_WHY} <why registering it would be wrong>\n"
            f"    {MARKER_COVERED_BY} <what provides that state instead>\n"
            + "\n".join(offenders),
        )

    def test_documented_exceptions_stay_rare(self):
        """The marker is a narrow escape hatch, not a parallel delivery path."""
        unregistered = sorted(_unregistered_modules())
        self.assertLessEqual(
            len(unregistered),
            MAX_UNREGISTERED,
            f"{len(unregistered)} patch modules now claim the documented-exception "
            f"marker (ceiling {MAX_UNREGISTERED}). Unregistered patches are meant to "
            "be a handful of reviewed cases; raising MAX_UNREGISTERED is a decision, "
            "not a fix:\n" + "\n".join(f"  {m}" for m in unregistered),
        )

    def test_registered_modules_exist_on_disk(self):
        """The reverse orphan: a patches.txt entry with no module behind it would
        raise on import partway through a customer's migrate."""
        _, registered = _registered_patches()
        on_disk = _modules_on_disk()
        missing = [
            entry
            for entry in registered
            if entry.startswith("apex.") and entry not in on_disk
        ]
        self.assertEqual(
            missing,
            [],
            "patches.txt registers a module that is not on disk — migrate would "
            "fail on the import. Fix the entry or restore the module:\n"
            + "\n".join(f"  {m}" for m in missing),
        )

    def test_registered_module_carries_no_exception_marker(self):
        """A registered patch DOES run on migrate, so an UNREGISTERED-PATCH marker
        on it is a false statement — usually a copy-paste of the exception."""
        _, registered = _registered_patches()
        on_disk = _modules_on_disk()
        contradictions = [
            entry
            for entry in registered
            if entry in on_disk
            and _marker_reason(_docstring(on_disk[entry]), MARKER_WHY) is not None
        ]
        self.assertEqual(
            contradictions,
            [],
            f"Module is an active patches.txt entry but its docstring carries the "
            f"`{MARKER_WHY}` marker. It DOES run on migrate — drop the marker, or "
            "drop the registration:\n" + "\n".join(f"  {m}" for m in contradictions),
        )


if __name__ == "__main__":
    unittest.main()
