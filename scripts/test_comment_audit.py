# Copyright (c) 2026, AFMCO and contributors
"""Fixture tests for the comment-policy gate.

Every violation class is PLANTED here, not merely observed absent from the real
tree: a gate that has only ever been seen to pass has not been shown to work.
The detection classes are driven as a subprocess, because the exit code is what
the Lint lane reads; the baseline arithmetic is driven in-process, because its
contract is what it tolerates rather than what it prints.

Stdlib-only, no bench, no site. Run it with:
    python3 -m unittest discover -s scripts -p 'test_*.py'
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parent
GATE = SCRIPTS / "comment_audit.py"

HAVE_GIT = shutil.which("git") is not None

# Neutralise the developer's global git config: a personal core.excludesFile could
# ignore a fixture path and make these results depend on the machine.
GIT_ENV = {**os.environ,
           "GIT_CONFIG_GLOBAL": os.devnull,
           "GIT_CONFIG_SYSTEM": os.devnull}

# The four series the board issues. Split so this file carries no literal id of
# its own -- the gate it tests would flag one, and rightly.
SERIES = ("T", "P", "A", "R")
NUMBER = "-4242"
# Real domain data that LOOKS like a board id. Project codes and room names are
# one- and two-digit; board ids are zero-padded to three. Flagging these would
# make the gate unusable in exactly the test fixtures it has to read.
DOMAIN_LOOKALIKES = ("P-1", "P-2", "R-1", "T-99")


def _load_gate():
    spec = importlib.util.spec_from_file_location("comment_audit", GATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = _load_gate()


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True, env=GIT_ENV)


def _long_docstring_module(span: int) -> str:
    """A module whose docstring occupies exactly `span` source lines."""
    filler = "\n".join(f"reason line {i}" for i in range(span - 2))
    return f'"""Head of the reason.\n{filler}\n"""\nvalue = 1\n'


class _GateCase(unittest.TestCase):
    """Plants files in a throwaway git repo and reads the gate's verdict."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.repo = Path(self.tmp)
        _git(self.repo, "init", "-q")
        (self.repo / "pkg").mkdir()

    def _plant(self, body: str, name: str = "planted.py") -> None:
        (self.repo / "pkg" / name).write_text(body, encoding="utf-8")
        _git(self.repo, "add", f"pkg/{name}")

    def _audit(self, *extra: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(GATE), str(self.repo / "pkg"),
             "--json", "--no-baseline", *extra],
            capture_output=True, text=True, env=GIT_ENV,
            cwd=tempfile.gettempdir(),
        )

    def _kinds(self, result: subprocess.CompletedProcess) -> list[str]:
        return [f["kind"] for f in json.loads(result.stdout)["findings"]]


@unittest.skipUnless(HAVE_GIT, "git is required to resolve the ignore rules")
class TestTheGateIsNotVacuous(_GateCase):
    def test_a_clean_module_passes(self):
        """Guards every refusal below from passing because the gate rejects all."""
        self._plant('"""One honest line of why."""\nvalue = 1\n')
        result = self._audit()

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(self._kinds(result), [])


@unittest.skipUnless(HAVE_GIT, "git is required to resolve the ignore rules")
class TestDocstringCeiling(_GateCase):
    def test_a_docstring_at_the_ceiling_fails(self):
        self._plant(_long_docstring_module(gate.DOCSTRING_LIMIT))
        result = self._audit()

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(gate.KIND_LONG_DOCSTRING, self._kinds(result))

    def test_a_docstring_one_line_under_the_ceiling_passes(self):
        self._plant(_long_docstring_module(gate.DOCSTRING_LIMIT - 1))
        result = self._audit()

        self.assertEqual(result.returncode, 0, result.stdout)

    def test_a_function_docstring_is_measured_too(self):
        """Not only the module docstring: the ceiling is per docstring."""
        filler = "\n".join(f"    reason {i}" for i in range(gate.DOCSTRING_LIMIT - 2))
        self._plant(f'def f():\n    """Head.\n{filler}\n    """\n    return 1\n')
        result = self._audit()

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(gate.KIND_LONG_DOCSTRING, self._kinds(result))


@unittest.skipUnless(HAVE_GIT, "git is required to resolve the ignore rules")
class TestEveryBoardIdSeriesIsCaught(_GateCase):
    """T-, P-, A- and R-, in each of the three places prose can hide."""

    def test_in_a_comment(self):
        for series in SERIES:
            with self.subTest(series=series):
                self._plant(f"# {series}{NUMBER} left in the source\nvalue = 1\n")
                result = self._audit()

                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn(gate.KIND_COMMENT_ID, self._kinds(result))

    def test_in_a_docstring(self):
        for series in SERIES:
            with self.subTest(series=series):
                self._plant(f'"""Why this exists ({series}{NUMBER})."""\nvalue = 1\n')
                result = self._audit()

                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn(gate.KIND_DOCSTRING_ID, self._kinds(result))

    def test_in_an_assert_statement_message(self):
        for series in SERIES:
            with self.subTest(series=series):
                self._plant(
                    "def check(x):\n"
                    f'    assert x, "the {series}{NUMBER} regression must stay fixed"\n'
                )
                result = self._audit()

                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn(gate.KIND_MESSAGE_ID, self._kinds(result))

    def test_in_a_unittest_assertion_message(self):
        """The class this gate exists for: it reaches a reader with no source."""
        for series in SERIES:
            with self.subTest(series=series):
                self._plant(
                    "def check(case, a, b):\n"
                    f'    case.assertEqual(a, b, "{series}{NUMBER} must stay fixed")\n'
                )
                result = self._audit()

                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn(gate.KIND_MESSAGE_ID, self._kinds(result))

    def test_in_a_thrown_message(self):
        for series in SERIES:
            with self.subTest(series=series):
                self._plant(
                    "def check():\n"
                    f'    frappe.throw("blocked by {series}{NUMBER}")\n'
                )
                result = self._audit()

                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn(gate.KIND_MESSAGE_ID, self._kinds(result))


@unittest.skipUnless(HAVE_GIT, "git is required to resolve the ignore rules")
class TestDomainDataIsNotABoardId(_GateCase):
    """The false positive that would have made this gate unshippable."""

    def test_project_codes_and_room_names_pass(self):
        for token in DOMAIN_LOOKALIKES:
            with self.subTest(token=token):
                self._plant(
                    f'"""Scoped to {token}."""\n'
                    f"# fixture project {token}\n"
                    "def check(case, a):\n"
                    f'    case.assertEqual(a, "{token}", "wrong project {token}")\n'
                )
                result = self._audit()

                self.assertEqual(result.returncode, 0, result.stdout)


@unittest.skipUnless(HAVE_GIT, "git is required to resolve the ignore rules")
class TestADocstringIsNotReadAsAComment(_GateCase):
    """A `#` inside a docstring is prose. Reading it as a comment both
    mis-attributes the finding and pads a consecutive-comment run."""

    def test_a_hash_inside_a_docstring_raises_no_comment_finding(self):
        body = "\n".join(f"# note {i}" for i in range(gate.CONSEC_LIMIT + 2))
        self._plant(f'"""Head.\n{body}\n"""\nvalue = 1\n')
        result = self._audit()

        self.assertEqual(result.returncode, 0, result.stdout)


class TestTheBaselineArithmetic(unittest.TestCase):
    """What the baseline tolerates, and what it refuses to tolerate."""

    FILE = "pkg/declared.py"
    KIND = gate.KIND_MESSAGE_ID

    def _finding(self, line: int, file: str | None = None, kind: str | None = None):
        return {"file": file or self.FILE, "line": line,
                "kind": kind or self.KIND, "detail": "planted"}

    def _apply(self, findings, baseline, ceilings=None):
        with mock.patch.dict(gate._BASELINE, baseline, clear=True), \
                mock.patch.dict(gate._KIND_CEILING, ceilings or {}, clear=True):
            return gate.apply_baseline(findings)

    def test_a_declared_finding_is_tolerated(self):
        failing, errors, _notes = self._apply(
            [self._finding(1)], {self.FILE: {self.KIND: 1}})

        self.assertEqual(failing, [])
        self.assertEqual(errors, [])

    def test_one_more_than_declared_still_fails(self):
        """The property a bare count baseline does not have."""
        failing, errors, _notes = self._apply(
            [self._finding(1), self._finding(2)], {self.FILE: {self.KIND: 1}})

        self.assertEqual(len(failing), 1, failing)
        self.assertEqual(errors, [])

    def test_the_same_violation_in_another_file_still_fails(self):
        failing, _errors, _notes = self._apply(
            [self._finding(1, file="pkg/other.py")], {self.FILE: {self.KIND: 1}})

        self.assertEqual(len(failing), 1, failing)

    def test_a_drained_entry_must_be_pruned(self):
        """A baseline is a promise to drain. An entry left behind after the drain
        is headroom nobody reviewed, so it fails until it is removed."""
        _failing, errors, _notes = self._apply([], {self.FILE: {self.KIND: 1}})

        self.assertEqual(len(errors), 1, errors)
        self.assertIn("stale baseline entry", errors[0])

    def test_an_invented_entry_cannot_buy_headroom(self):
        """Padding names a file with no such finding, which IS the stale failure."""
        _failing, errors, _notes = self._apply(
            [self._finding(1)],
            {self.FILE: {self.KIND: 1}, "pkg/invented.py": {self.KIND: 5}})

        self.assertEqual(len(errors), 1, errors)
        self.assertIn("pkg/invented.py", errors[0])

    def test_a_kind_ceiling_refuses_growth(self):
        findings = [self._finding(n, kind=gate.KIND_DOCSTRING_ID) for n in (1, 2, 3)]
        _failing, errors, _notes = self._apply(
            findings, {}, {gate.KIND_DOCSTRING_ID: 2})

        self.assertEqual(len(errors), 1, errors)
        self.assertIn(gate.KIND_DOCSTRING_ID, errors[0])

    def test_a_kind_ceiling_tolerates_its_own_count(self):
        findings = [self._finding(n, kind=gate.KIND_DOCSTRING_ID) for n in (1, 2)]
        failing, errors, notes = self._apply(
            findings, {}, {gate.KIND_DOCSTRING_ID: 2})

        self.assertEqual((failing, errors, notes), ([], [], []))

    def test_slack_under_a_kind_ceiling_is_reported_but_does_not_fail(self):
        """Many branches remove one of these in passing; reddening the shared lint
        lane for a good deed buys nothing, but the slack must still be visible."""
        _failing, errors, notes = self._apply(
            [self._finding(1, kind=gate.KIND_DOCSTRING_ID)], {},
            {gate.KIND_DOCSTRING_ID: 4})

        self.assertEqual(errors, [])
        self.assertEqual(len(notes), 1, notes)
        self.assertIn("3 under its ceiling", notes[0])

    def test_a_kind_with_no_ceiling_fails_outright(self):
        failing, _errors, _notes = self._apply([self._finding(1)], {}, {})

        self.assertEqual(len(failing), 1, failing)


@unittest.skipUnless(HAVE_GIT, "git is required to resolve the ignore rules")
class TestTheBaselineAppliesToApexOnly(_GateCase):
    """The counts are facts about one package. Anywhere else they would tolerate
    455 board ids that were never counted there — a gate passing an unread tree."""

    def test_a_foreign_root_gets_no_allowance(self):
        self._plant(f"# {SERIES[0]}{NUMBER} left in the source\nvalue = 1\n")
        result = subprocess.run(
            [sys.executable, str(GATE), str(self.repo / "pkg"), "--json"],
            capture_output=True, text=True, env=GIT_ENV, cwd=tempfile.gettempdir(),
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(gate.KIND_COMMENT_ID,
                      [f["kind"] for f in json.loads(result.stdout)["findings"]])

    def test_the_apex_package_is_recognised(self):
        pkg = self.repo / "apex"
        pkg.mkdir()
        (pkg / "hooks.py").write_text("app_name = 'apex'\n", encoding="utf-8")
        (pkg / "modules.txt").write_text("Apex Core\n", encoding="utf-8")

        self.assertTrue(gate.is_baselined_root(pkg))
        self.assertFalse(gate.is_baselined_root(self.repo / "pkg"))


class TestTheShippedBaselineIsHonest(unittest.TestCase):
    def test_every_declared_kind_is_a_kind_the_gate_can_emit(self):
        """A typo in a kind name would silently tolerate nothing and hide nothing,
        which reads as a working entry."""
        known = {gate.KIND_COMMENT_ID, gate.KIND_DOCSTRING_ID, gate.KIND_MESSAGE_ID,
                 gate.KIND_LONG_DOCSTRING, "banner", "long-block"}
        declared = {k for kinds in gate._BASELINE.values() for k in kinds}
        declared |= set(gate._KIND_CEILING)

        self.assertEqual(declared - known, set())

    def test_the_baseline_is_small_enough_to_read(self):
        """The point of naming paths rather than counting: a reader can check it."""
        entries = sum(len(kinds) for kinds in gate._BASELINE.values())

        self.assertLessEqual(entries, 25, "the per-file baseline has become a cupboard")


if __name__ == "__main__":
    unittest.main()
