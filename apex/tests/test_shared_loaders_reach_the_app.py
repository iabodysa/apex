# Copyright (c) 2026, AFMCO and contributors
"""Every shared loader must read a NON-EMPTY population off the installed app.

This is the guard for the defect class A-370 and A-376 were opened over. The suite moved
out of the app package on 2026-08-02 and each loader kept deriving its root from its own
``__file__``, which now names ``.claude/tests/apex`` — a tree of test modules and nothing
else. The globs went quiet, the loops they feed had no iterations, and roughly a third of
the maintainer suite reported green while asserting nothing at all.

A loader is the worst place for that failure because it is shared: one wrong root takes
every consumer down with it, silently. So the population itself is asserted here, once
per loader, and a root that stops naming the product reds immediately instead of turning
a dozen unrelated guards into false greens.

The counts are floors, not equalities — a real deletion in the app must not red this file,
only a root that stops resolving. Each floor is far below today's count and far above zero.
"""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import apex
from apex.tests import source_tree, workspace_reachability
from apex.tests.shipped_doctypes import DOCTYPE_GLOB, shipped_doctypes
from apex.tests.shipped_notifications import shipped_notifications


class TestSharedLoadersReachTheApp(unittest.TestCase):
    """Each loader answers about the installed package, never about the suite mirror."""

    def _app_root(self):
        """The installed app directory, resolved the one way that cannot drift."""
        return Path(apex.__file__).resolve().parent

    def test_no_loader_is_rooted_in_the_suite(self):
        """A root under .claude/ is the exact bug: it names test modules, not product."""
        # Named by what it is, not by where this file sits. Walking up from __file__ made
        # the anchor move with the module: from the mirror it resolved to `.claude/tests`,
        # and from `apex/tests/` it resolves to the repo root, which every loader legally
        # starts with — so the check inverted and failed all three.
        suite = Path(apex.__file__).resolve().parents[1] / ".claude" / "tests"
        for label, root in (
            ("source_tree.APP_ROOT", source_tree.APP_ROOT),
            ("workspace_reachability._APP", workspace_reachability._APP),
            ("shipped_doctypes.DOCTYPE_GLOB", DOCTYPE_GLOB),
        ):
            with self.subTest(loader=label):
                self.assertFalse(
                    str(root).startswith(str(suite)),
                    f"{label} is rooted in the maintainer suite, not the app",
                )
                self.assertTrue(
                    str(root).startswith(str(self._app_root())),
                    f"{label} does not resolve inside the installed apex package",
                )

    def test_shipped_doctypes_reads_the_app(self):
        """The DocType loader every permission and schema guard reads through."""
        self.assertGreater(len(shipped_doctypes()), 100, "no shipped DocType JSON was read")

    def test_shipped_notifications_reads_the_app(self):
        """The Notification loader the alert-reach guards read through."""
        self.assertGreater(len(shipped_notifications()), 5, "no shipped Notification was read")

    def test_workspace_reachability_reads_the_app(self):
        """The sidebar scan: nine workspaces ship, so an empty map is a broken root."""
        self.assertGreater(len(workspace_reachability.workspaces()), 5, "no workspace was read")

    def test_source_tree_reads_the_app(self):
        """The source scan every static guard walks."""
        self.assertGreater(len(source_tree.all_py_files()), 200, "no app source file was read")
        self.assertGreater(
            len(source_tree.production_py_files()), 200, "no production source file was read"
        )
        self.assertTrue(Path(source_tree.AR_CSV).is_file(), "the shipped ar.csv was not found")
        self.assertGreater(len(source_tree.translations()), 100, "ar.csv read as empty")

    def test_source_tree_reads_the_suite_for_the_test_corpus(self):
        """The two readers whose subject IS the suite must NOT follow the app root.

        Rooting these on the app would score the whole corpus as zero test files, which
        is the same false green in the opposite direction.
        """
        self.assertGreater(len(source_tree.test_py_files()), 300, "no test module was read")
        self.assertGreater(len(source_tree.test_support_files()), 3, "no shared helper was read")

    def test_the_corpus_floor_can_actually_fail(self):
        """The positive control for the floor above: point the readers at an empty
        directory and they must answer zero.

        A floor over a population that no longer moves is not a guard. This one passed
        through the whole of A-550 while ``SUITE_ROOT`` resolved to the repo root and
        the mirror was invisible, because the shipped count had risen past 300 on its
        own — the right number for the wrong population. Proving the readers go empty
        when handed an empty root is what tells a real pass from that.
        """
        with tempfile.TemporaryDirectory() as empty:
            with mock.patch.object(source_tree, "APP_ROOT", empty), mock.patch.object(
                source_tree, "SUITE_ROOT", empty
            ):
                self.assertEqual(source_tree.test_py_files(), [])
                self.assertEqual(source_tree.test_support_files(), [])

    def test_the_corpus_spans_both_roots(self):
        """Each root contributes, so a collapse of one onto the other reds here.

        The A-550 defect was exactly that collapse: ``SUITE_PACKAGE`` came out equal to
        ``APP_ROOT``, so the mirror's share was zero and every consumer scanned the app
        twice instead of the corpus once. A count alone cannot see it; a per-root count
        can.
        """
        self.assertNotEqual(source_tree.SUITE_ROOT, source_tree.APP_ROOT)
        self.assertNotEqual(source_tree.SUITE_PACKAGE, source_tree.APP_ROOT)
        corpus = source_tree.test_py_files()
        shipped = [p for p in corpus if p.startswith(source_tree.APP_ROOT)]
        mirrored = [p for p in corpus if p.startswith(source_tree.SUITE_ROOT)]
        self.assertGreater(len(shipped), 100, "no shipped test module was read")
        self.assertGreater(len(mirrored), 50, "no mirror test module was read")
        self.assertEqual(len(shipped) + len(mirrored), len(corpus))


if __name__ == "__main__":
    unittest.main()
