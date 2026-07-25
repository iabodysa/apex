# Copyright (c) 2026, AFMCO and contributors
"""The repo lint gates must judge the same tree CI checks out.

`scripts/comment_audit.py` and `scripts/check_translations.py` used to walk the
working directory, so a gitignored file could set the exit code. CI runs on a
fresh checkout where that file does not exist, so the same command gave a
different verdict on a developer's machine than in the Lint lane, which teaches
people to wave a local red through.

The gates live outside the `apex` package (they exist because the maintainer's
toolbox cannot run on a CI runner), so these tests drive them as subprocesses
rather than importing them. That keeps the real contract under test — the
process exit code the Lint job reads — with no sys.path surgery and no second
copy of the walking logic here.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"
COMMENT_AUDIT = SCRIPTS / "comment_audit.py"
CHECK_TRANSLATIONS = SCRIPTS / "check_translations.py"

HASH = "#"
BANNER_COMMENT = HASH + " " + "=" * 12
TASKID_COMMENT = HASH + " T" + "-4242 kept in the source by mistake"
# Two banner hits and one task id: a file the gate must reject when it can see it.
VIOLATING_SOURCE = "\n".join([BANNER_COMMENT, TASKID_COMMENT, BANNER_COMMENT, "value = 1", ""])

SENTINEL = "Gate Fixture Sentinel Phrase"
TRANSLATING_SOURCE = "value = {0}({1!r})\n".format("_", SENTINEL)

HAVE_GIT = shutil.which("git") is not None

# Neutralise the developer's global/system git config: a personal core.excludesFile
# could ignore a fixture path and make these results depend on the machine, which
# is the very failure being guarded against.
GIT_ENV = {**os.environ,
           "GIT_CONFIG_GLOBAL": os.devnull,
           "GIT_CONFIG_SYSTEM": os.devnull}


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True, env=GIT_ENV)


def _init_repo(repo: Path, ignore: str) -> None:
    _git(repo, "init", "-q")
    (repo / ".gitignore").write_text(ignore, encoding="utf-8")


def _write(repo: Path, rel: str, body: str) -> Path:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _run(script: Path, *args: str) -> subprocess.CompletedProcess:
    """Run a gate from an unrelated cwd: the gates must not depend on where they
    are invoked from, only on the root they are pointed at."""
    return subprocess.run([sys.executable, str(script), *args],
                          capture_output=True, text=True, env=GIT_ENV,
                          cwd=tempfile.gettempdir())


@unittest.skipUnless(HAVE_GIT, "git is required to resolve the ignore rules")
@unittest.skipUnless(COMMENT_AUDIT.exists(), "scripts/ is not present in this install")
class TestCommentAuditIgnoresGitignoredFiles(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.repo = Path(self.tmp)
        _init_repo(self.repo, "demo/\n")
        _write(self.repo, "pkg/clean.py", "value = 1\n")
        _git(self.repo, "add", "pkg/clean.py")

    def test_violation_in_an_ignored_file_does_not_change_the_exit_code(self):
        before = _run(COMMENT_AUDIT, str(self.repo / "pkg"))
        _write(self.repo, "pkg/demo/generated.py", VIOLATING_SOURCE)
        after = _run(COMMENT_AUDIT, str(self.repo / "pkg"))

        self.assertEqual(before.returncode, 0, f"clean tree should pass: {before.stdout}")
        self.assertEqual(
            after.returncode, 0,
            "a gitignored file changed the gate's verdict, so the local run "
            f"disagrees with CI: {after.stdout}",
        )
        self.assertNotIn("generated.py", after.stdout)

    def test_the_same_content_in_a_tracked_file_still_fails(self):
        """Guards the test above from passing vacuously."""
        _write(self.repo, "pkg/real.py", VIOLATING_SOURCE)
        _git(self.repo, "add", "pkg/real.py")
        result = _run(COMMENT_AUDIT, str(self.repo / "pkg"))

        self.assertEqual(result.returncode, 1, f"tracked violation must fail: {result.stdout}")
        self.assertIn("real.py", result.stdout)
        self.assertIn("task-id", result.stdout)

    def test_a_tracked_file_is_audited_even_if_a_pattern_would_ignore_it(self):
        """Force-added files ship, so they must stay audited: the gate follows what
        git tracks, not what the ignore patterns say in isolation."""
        _write(self.repo, "pkg/demo/forced.py", VIOLATING_SOURCE)
        _git(self.repo, "add", "-f", "pkg/demo/forced.py")
        result = _run(COMMENT_AUDIT, str(self.repo / "pkg"))

        self.assertEqual(result.returncode, 1, f"tracked file must be audited: {result.stdout}")
        self.assertIn("forced.py", result.stdout)


@unittest.skipUnless(HAVE_GIT, "git is required to resolve the ignore rules")
@unittest.skipUnless(CHECK_TRANSLATIONS.exists(), "scripts/ is not present in this install")
class TestTranslationGateIgnoresGitignoredFiles(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.repo = Path(self.tmp)
        _init_repo(self.repo, "demo/\n")
        _write(self.repo, "pkg/translations/ar.csv", "")
        _write(self.repo, "pkg/clean.py", "value = 1\n")
        _git(self.repo, "add", "pkg/clean.py")

    def _check(self):
        return _run(CHECK_TRANSLATIONS, "--package", str(self.repo / "pkg"),
                    "--lang", "ar", "--max-missing", "0", "--max-stale", "0", "--json")

    def test_untranslated_string_in_an_ignored_file_does_not_change_the_exit_code(self):
        _write(self.repo, "pkg/demo/generated.py", TRANSLATING_SOURCE)
        result = self._check()

        self.assertEqual(
            result.returncode, 0,
            "a gitignored file's string was reported MISSING, so the local run "
            f"disagrees with CI: {result.stdout}",
        )
        self.assertIn('"missing_count":0', result.stdout)

    def test_the_same_string_in_a_tracked_file_is_still_reported_missing(self):
        """Guards the test above from passing vacuously."""
        _write(self.repo, "pkg/real.py", TRANSLATING_SOURCE)
        _git(self.repo, "add", "pkg/real.py")
        result = self._check()

        self.assertEqual(result.returncode, 1, f"tracked string must be missing: {result.stdout}")
        self.assertIn('"missing_count":1', result.stdout)

    def test_an_ignored_file_cannot_mask_a_stale_row(self):
        """The dangerous direction: an ignored file that uses a string keeps a dead
        ar.csv row out of STALE, which would hide a failure CI still sees."""
        _write(self.repo, "pkg/translations/ar.csv", f'"{SENTINEL}","ترجمة"\n')
        _write(self.repo, "pkg/demo/generated.py", TRANSLATING_SOURCE)
        result = self._check()

        self.assertEqual(result.returncode, 1, f"stale row must surface: {result.stdout}")
        self.assertIn('"stale_count":1', result.stdout)


if __name__ == "__main__":
    unittest.main()
