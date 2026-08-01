# Copyright (c) 2026, AFMCO and contributors
"""``docs/reference/permissions.md`` must be exactly what the generator emits.

The published permission matrices used to be hand-maintained, one per training page,
and around two hundred cells stated per DocType and per role which rights an operator
held. Nothing read them and they had rotted: six DocTypes were listed under names the
app had not shipped for some time (``Accommodation Assignment`` for
``Housing Assignment``, ``Habitat Safety Incident`` for ``Safety Incident``, and four
more), a role column claimed rights the JSON grants to two different roles, and five
rows described two DocTypes at once whose permissions are not in fact the same.

The page is now derived from the same DocType JSON a site installs
(``scripts/build_permissions_reference.py``), so a stale name or a wrong rights cell is
not a defect that can be introduced. What is left to check is that the copy on disk is
the copy the generator produces — a round trip, not a second implementation of the
comparison. Three checks stand beside it and each covers a distinct way the round trip
could pass while saying nothing:

* the generator must still see the whole app, measured against an independent reader;
* a lesson must not grow its own role matrix again, which is how the rot started;
* the six retired DocType names must stay out of every published page, prose included.

It sits in apex_core because the tables span every module (Habitat, Salis, Logistay) and
the central apex/tests/ directory is closed to new modules (test_colocation_ratchet.py);
apex_core is the shared kernel, so a cross-module published-claim guard has a home here.

Run standalone:  python3 -m unittest apex.apex_core.test_training_doc_parity -v
"""

import importlib.util
import os
import re
import unittest

from apex.tests.shipped_doctypes import shipped_doctypes
from apex.tests.training_charter import role_charters

APP_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
REPO_ROOT = os.path.dirname(APP_ROOT)
GENERATOR = os.path.join(REPO_ROOT, "scripts", "build_permissions_reference.py")
PERMISSIONS_REFERENCE = os.path.join(REPO_ROOT, "docs", "reference", "permissions.md")
TRAINING_DIR = os.path.join(REPO_ROOT, "docs", "training")
PUBLISHED_DOCS = (REPO_ROOT, TRAINING_DIR, os.path.join(REPO_ROOT, "docs", "reference"))

_TABLE_DIVIDER = re.compile(r"^\|[\s:\-|]+\|$")

# The DocType names the pages carried after the app had renamed them. Kept by name
# because this is the incident the guard exists for; the generator cannot emit them,
# so what these assert now is that no page reintroduces one in prose.
RETIRED_DOCTYPE_NAMES = (
    "Accommodation Assignment",
    "Accommodation Checkout",
    "Accommodation Resident Request",
    "Accommodation Lease",
    "Habitat Safety Incident",
    "Salis Portal Theme",
)

# Roles that hold real DocPerms but are not Apex personas, so they have no charter row.
# A lesson table headed by one of these is still a permission matrix.
ROLE_HEADERS_OUTSIDE_THE_CHARTER = {
    "All": (
        "the built-in Frappe role every session holds. It is not an Apex persona, so it "
        "has no Roles at a glance row, but it does carry real DocPerms (the universal "
        "Maintenance Request intake)."
    ),
    "Maintenance Manager": (
        "ERPNext-supplied role. docs/training/README.md states Apex grants it nothing, so "
        "it has no charter row."
    ),
    "System Manager": (
        "the platform administrator role. It holds the widest DocPerm set in the app and "
        "belongs in the generated reference, but it is not an operational persona."
    ),
}


UNGUARDED_PUBLISHED_CLASSES = (
    # In priority order. Each entry states the size measured when this guard landed and
    # whether the class is worth a guard AS PUBLISHED, because the deciding question is
    # never the cell count — it is whether the page states a fact a machine can resolve.
    (
        "README.md served-portal-routes table",
        "28 cells across 7 routes, plus 4 role-set constants and 2 endpoint counts named "
        "in the surrounding prose. WORTH A GUARD, and the highest-value one left: it is "
        "the published access-control record for every portal surface, nothing under "
        "apex/ reads it, and it is unusually checkable — FLEET_ROLES, HOUSING_ROLES, "
        "SAFETY_ROLES and SUPERVISOR_ROLES are real Python sets, and '(4 endpoints)' and "
        "'(13 endpoints)' are countable from the api modules. The parenthesised-list and "
        "number-word techniques this guard uses apply unchanged."
    ),
    (
        "docs/TRAINING.md index",
        "11 page links and one 'seven portal routes' count, read by nothing. WORTH A "
        "GUARD, and a cheap one: link targets either resolve on disk or they do not, and "
        "the count is the same number-word claim made in two other published files, so "
        "all three can be tied together. Small, but a renamed page breaks it silently."
    ),
    (
        "DocType names in training prose",
        "80 bold spans outside any table, of which 34 resolve to a shipped DocType. NOT "
        "WORTH A GUARD AS PUBLISHED: bold marks emphasis, roles, desk pages and DocTypes "
        "alike, so a guard would need a suppression list roughly as long as the class it "
        "checks. Normalise first — write DocType names in prose as `Backticked Name` and "
        "the same name axis this module already implements covers them for free."
    ),
    (
        "Key-field bullets in the training guides",
        "about 70 names across the per-area pages. NOT WORTH A GUARD AS PUBLISHED: they "
        "are human phrases ('employee/resident', 'start date'), not fieldnames, so "
        "matching them to the schema needs fuzzy comparison. A fuzzy guard over prose "
        "fires on rewording rather than on drift, which is worse than a recorded gap."
    ),
    (
        "Background-job list in settings.md",
        "about 22 job descriptions. NOT WORTH A GUARD AS PUBLISHED: they are English "
        "descriptions, not the scheduler keys in hooks.py, so a guard needs a "
        "phrase-to-dotted-path alias map — and that map would itself be an unread copy "
        "of the page, which is the exact failure this card was opened to remove."
    ),
)


def load_generator():
    """Import ``scripts/build_permissions_reference.py`` by path.

    ``scripts/`` is a directory of runnable tools, not an importable package, so the
    guard reaches the one the operator runs rather than a copy of its logic.
    """
    spec = importlib.util.spec_from_file_location("build_permissions_reference", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _cell(text):
    return text.replace("*", "").strip()


def _tables(path):
    """Yield (line number of the header, header cells) for each pipe table."""
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    for index, line in enumerate(lines):
        if not line.startswith("|"):
            continue
        if index + 1 < len(lines) and _TABLE_DIVIDER.match(lines[index + 1]):
            yield index + 1, [_cell(c) for c in line.strip().strip("|").split("|")]


def lesson_role_matrices(root=TRAINING_DIR, roles=None):
    """``file:line`` for every lesson table headed by DocType and then only roles."""
    known = set(roles if roles is not None else role_charters()) | set(
        ROLE_HEADERS_OUTSIDE_THE_CHARTER
    )
    found = []
    for name in sorted(os.listdir(root)):
        if not name.endswith(".md"):
            continue
        for line, header in _tables(os.path.join(root, name)):
            if len(header) < 2 or header[0] != "DocType":
                continue
            if all(column in known for column in header[1:]):
                found.append(f"{name}:{line}")
    return found


def published_pages():
    """Every published Markdown page, so a prose check reaches all of them."""
    pages = []
    for directory in PUBLISHED_DOCS:
        if not os.path.isdir(directory):
            continue
        for name in sorted(os.listdir(directory)):
            if name.endswith(".md"):
                pages.append(os.path.join(directory, name))
    return pages


class TestPermissionReferenceIsGenerated(unittest.TestCase):
    """The round trip, and the three ways it could pass while proving nothing."""

    def setUp(self):
        self.generator = load_generator()

    def test_the_published_page_is_what_the_generator_emits(self):
        with open(PERMISSIONS_REFERENCE, encoding="utf-8") as fh:
            published = fh.read()
        self.assertEqual(
            published,
            self.generator.render(),
            "docs/reference/permissions.md is not what the shipped DocPerm JSON produces. "
            "It is a generated page: rerun `python3 scripts/build_permissions_reference.py` "
            "and commit the result rather than editing the page.",
        )

    def test_the_generator_sees_every_shipped_doctype(self):
        """An independent reader, so a broken walker cannot green the round trip."""
        independent = shipped_doctypes()
        emitted = {record["name"] for record in self.generator.shipped_doctypes()}
        self.assertEqual(
            sorted(set(independent) - emitted),
            [],
            "the permissions generator no longer reads every shipped DocType JSON",
        )
        self.assertGreater(len(emitted), 50, "DocType JSON scan found nothing")
        for landmark in ("Housing Assignment", "Salis Vehicle", "Cleaning Log"):
            self.assertIn(landmark, independent)

    def test_the_page_carries_the_docperm_rows_that_ship(self):
        """Non-vacuity on the output: an empty render would round-trip against itself."""
        rows = sum(len(record["rows"]) for record in self.generator.shipped_doctypes())
        self.assertGreater(rows, 400, "the DocPerm scan collapsed")
        with open(PERMISSIONS_REFERENCE, encoding="utf-8") as fh:
            published = fh.read().splitlines()
        emitted = [line for line in published if line.startswith("| ") and " | 0 | " in line]
        self.assertGreater(len(emitted), 400, "the published page states almost no grants")


class TestLessonsDoNotRepeatThePermissionMatrices(unittest.TestCase):
    """The matrices are centralised because a per-page copy is what rotted."""

    def test_no_lesson_carries_a_role_matrix(self):
        repeated = lesson_role_matrices()
        self.assertEqual(
            repeated,
            [],
            "a training lesson repeats a DocType/role permission matrix. Those are "
            "generated into docs/reference/permissions.md; link to the module anchor "
            f"instead so the page cannot drift from the JSON: {repeated}",
        )

    def test_the_lesson_scan_reads_the_pages(self):
        """A broken listing would report no matrix because it saw no file."""
        seen = [os.path.basename(p) for p in published_pages() if TRAINING_DIR in p]
        for expected in ("custody.md", "safety.md", "settings.md"):
            self.assertIn(expected, seen, "the lesson scan no longer reaches the guides")

    def test_the_retired_doctype_names_stay_out_of_every_page(self):
        """The original rot, asserted over prose as well as tables."""
        offenders = []
        for path in published_pages():
            with open(path, encoding="utf-8") as fh:
                for number, line in enumerate(fh, start=1):
                    for stale in RETIRED_DOCTYPE_NAMES:
                        if stale in line:
                            offenders.append(f"{os.path.relpath(path, REPO_ROOT)}:{number} {stale}")
        self.assertEqual(
            offenders,
            [],
            f"published page names a DocType the app renamed: {offenders}",
        )


class TestTheRemainingUnguardedClassesStayRecorded(unittest.TestCase):
    def test_declared_role_headers_all_carry_a_reason(self):
        for role, reason in ROLE_HEADERS_OUTSIDE_THE_CHARTER.items():
            with self.subTest(entry=role):
                self.assertTrue(reason and reason.strip(), f"'{role}' has no reason")

    def test_the_register_keeps_a_written_verdict(self):
        """The gaps this card chose not to close must keep a written verdict, not vanish.

        An unguarded published claim that nobody has written a decision about is how the
        training tables rotted in the first place; the register is the ratchet against
        repeating that, so an entry may be removed only when the gap is actually closed.
        """
        self.assertGreaterEqual(len(UNGUARDED_PUBLISHED_CLASSES), 5, "the register shrank")
        for name, verdict in UNGUARDED_PUBLISHED_CLASSES:
            with self.subTest(published_class=name):
                self.assertTrue(name.strip(), "register entry has no name")
                self.assertTrue(verdict.strip(), f"'{name}' records no verdict")
                self.assertIn(
                    "WORTH A GUARD",
                    verdict,
                    f"'{name}' does not state a WORTH A GUARD / NOT WORTH A GUARD verdict",
                )


if __name__ == "__main__":
    unittest.main()
