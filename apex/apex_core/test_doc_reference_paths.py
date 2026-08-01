# Copyright (c) 2026, AFMCO and contributors
"""Every ``docs/*.md`` path the application source cites must resolve to a shipped file.

Application source points operators at the published guides from three kinds of place: a
DocType JSON help panel, a module docstring, and a patch's COVERED-BY note. Nothing read
those strings, so a documentation reorganisation that moved or renamed a guide would leave
the app naming a file that is not there - and the operator following a cutover runbook is
the worst person to hand a dead path to.

The check is exact and has no baseline: a path either resolves under the repository root
or it does not. Globs are skipped because they name a set, not a file.

Site-free.  Run standalone:  python3 -m unittest apex.apex_core.test_doc_reference_paths -v
"""

import os
import re
import tempfile
import unittest

APP_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
REPO_ROOT = os.path.dirname(APP_ROOT)

SCANNED_SUFFIXES = (".py", ".json", ".js", ".txt", ".md")
DOC_REFERENCE = re.compile(r"\bdocs/[A-Za-z0-9_.*/-]+\.md")


def collect_references(root):
    """Yield (path, line number, cited docs path) for every non-glob citation under root."""
    for directory, _subdirs, filenames in os.walk(root):
        for filename in sorted(filenames):
            if not filename.endswith(SCANNED_SUFFIXES):
                continue
            full = os.path.join(directory, filename)
            with open(full, encoding="utf-8", errors="ignore") as handle:
                for number, line in enumerate(handle, start=1):
                    for cited in DOC_REFERENCE.findall(line):
                        if "*" not in cited:
                            yield full, number, cited


class TestDocReferencePaths(unittest.TestCase):
    def test_every_cited_guide_exists(self):
        missing = [
            f"{os.path.relpath(path, REPO_ROOT)}:{number} -> {cited}"
            for path, number, cited in collect_references(APP_ROOT)
            if not os.path.isfile(os.path.join(REPO_ROOT, cited))
        ]
        self.assertEqual(
            missing,
            [],
            "Application source cites documentation that does not exist at that path.",
        )

    def test_at_least_the_known_guides_are_covered(self):
        """Guards the scanner itself: a regex that stops matching would pass vacuously."""
        cited = {reference[2] for reference in collect_references(APP_ROOT)}
        self.assertIn("docs/INTEGRATION.md", cited)
        self.assertIn("docs/administration/identity-upgrade.md", cited)

    def test_a_dead_reference_is_reported(self):
        # Split so this file does not itself cite the dead path the probe writes.
        dead = "docs/" + "administration/integration.md"
        with tempfile.TemporaryDirectory() as tree:
            with open(os.path.join(tree, "probe.py"), "w", encoding="utf-8") as handle:
                handle.write(f'"""See {dead} for details."""\n')
            found = list(collect_references(tree))
        self.assertEqual([reference[2] for reference in found], [dead])
        self.assertFalse(os.path.isfile(os.path.join(REPO_ROOT, dead)))
