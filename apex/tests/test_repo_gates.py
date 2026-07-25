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

The same "local verdict must equal the CI verdict" contract covers the commit
hooks under `.githooks`, which are driven here as real commits for the same reason.
"""

import os
import re
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

GITHOOKS = REPO_ROOT / ".githooks"
COMMIT_MSG_HOOK = GITHOOKS / "commit-msg"
PRE_COMMIT_HOOK = GITHOOKS / "pre-commit"
TEST_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "test.yml"
PRE_COMMIT_CONFIG = REPO_ROOT / ".pre-commit-config.yaml"

INSTALL_COMMAND = "git config core.hooksPath .githooks"
PUBLIC_EMAIL = "1+dev@users.noreply.github.com"

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


def _extract(pattern: str, path: Path, flags: int = 0) -> str:
    """The single capture of `pattern` in `path`, or a failure that names the file.

    Both sides of the mirror are read out of their real homes rather than restated
    here: a copy in this file would be a third pattern to keep in step."""
    found = re.findall(pattern, path.read_text(encoding="utf-8"), flags)
    if len(found) != 1:
        raise AssertionError(
            f"expected exactly one {pattern!r} in {path}, found {len(found)}. "
            "The mirror check cannot run until that is unambiguous again."
        )
    return found[0]


def _init_hooked_repo(repo: Path) -> None:
    _git(repo, "init", "-q")
    # Absolute, because the temp repo has no checkout of .githooks of its own.
    _git(repo, "config", "core.hooksPath", str(GITHOOKS))
    _git(repo, "config", "user.name", "Apex Bot")
    _git(repo, "config", "user.email", PUBLIC_EMAIL)


def _attempt_commit(repo: Path, message: str, env=None) -> subprocess.CompletedProcess:
    # Fresh content every attempt: an unchanged tree would fail the commit for the
    # wrong reason and read as a hook refusal.
    _write(repo, "payload.txt", os.urandom(8).hex())
    _git(repo, "add", "-A")
    return subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", message],
        capture_output=True, text=True, env={**GIT_ENV, **(env or {})},
    )


HAVE_AWK = shutil.which("awk") is not None
LEAKED_TRAILER = "Co-Authored-By: " + "Claude Opus 5 (1M context) <noreply@anthropic.com>"


@unittest.skipUnless(HAVE_GIT, "git is required to run the hooks")
@unittest.skipUnless(COMMIT_MSG_HOOK.exists(), ".githooks is not present in this install")
@unittest.skipUnless(TEST_WORKFLOW.exists(), ".github is not present in this install")
class TestCommitMetadataHooksMirrorCI(unittest.TestCase):
    """The local commit gate must reject exactly what the CI step rejects.

    Commit 43955b8f reached origin carrying an attribution trailer and a session
    URL. CI caught it, but only after the push, and the red landed on a job named
    Tests — which reads as "a test failed" when it means "the metadata guard fired
    and this job's tests never ran". The hooks under .githooks move that refusal to
    before the commit exists; these tests exist so the local copy can never come to
    disagree with the CI step it mirrors, which would be worse than no hook at all.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.repo = Path(self.tmp)
        _init_hooked_repo(self.repo)

    def test_attribution_pattern_is_byte_identical_to_the_ci_step(self):
        ci = _extract(r"grep -niE\s*\\?\s*'([^']+)'", TEST_WORKFLOW)
        local = _extract(r"^ATTRIBUTION_PATTERN='([^']+)'", COMMIT_MSG_HOOK, re.M)

        self.assertEqual(
            local, ci,
            "the commit-msg hook and the CI guard no longer grep the same pattern, "
            "so a local pass stopped meaning a CI pass",
        )

    def test_a_message_carrying_an_attribution_trailer_is_refused(self):
        result = _attempt_commit(self.repo, "fix: something real\n\n" + LEAKED_TRAILER)

        self.assertNotEqual(result.returncode, 0, "the trailer was allowed to commit")
        self.assertIn("attribution", result.stderr.lower())
        self.assertEqual(_git_log_count(self.repo), 0, "a refused commit still landed")

    def test_a_message_carrying_a_session_url_is_refused(self):
        result = _attempt_commit(
            self.repo, "fix: something real\n\nClaude-Session: https://example.invalid/s/1"
        )

        self.assertNotEqual(result.returncode, 0, "the session URL was allowed to commit")
        self.assertEqual(_git_log_count(self.repo), 0, "a refused commit still landed")

    def test_a_clean_commit_succeeds(self):
        """Guards every refusal above from passing because the hook rejects
        everything, which would be indistinguishable from a working gate."""
        result = _attempt_commit(self.repo, "fix: repoint the dead compliance link")

        self.assertEqual(result.returncode, 0, f"a clean commit was refused: {result.stderr}")
        self.assertEqual(_git_log_count(self.repo), 1)

    def test_a_private_author_email_is_refused(self):
        _git(self.repo, "config", "user.email", "dev@example.com")
        result = _attempt_commit(self.repo, "fix: repoint the dead compliance link")

        self.assertNotEqual(result.returncode, 0, "a private author email was allowed")
        self.assertIn("dev@example.com", result.stderr)
        self.assertEqual(_git_log_count(self.repo), 0)

    def test_a_private_committer_email_is_refused(self):
        """The CI step reads %ce as well as %ae, so the hook has to check both."""
        result = _attempt_commit(
            self.repo, "fix: repoint the dead compliance link",
            env={"GIT_COMMITTER_EMAIL": "dev@example.com"},
        )

        self.assertNotEqual(result.returncode, 0, "a private committer email was allowed")
        self.assertEqual(_git_log_count(self.repo), 0)

    @unittest.skipUnless(HAVE_AWK, "awk is required to run the CI classifier")
    def test_the_hook_and_the_ci_awk_classify_the_same_addresses_alike(self):
        """Byte-equality is impossible here — CI expresses the allowlist as awk and
        the hook as a shell `case` — so agreement is proven by running both."""
        addresses = [
            "noreply@github.com",
            "248423400+iabodysa@users.noreply.github.com",
            "@users.noreply.github.com",
            "dev@example.com",
            "noreply@anthropic.com",
            "dev@users.noreply.github.example.com",
            "users.noreply.github.com",
        ]
        awk_program = _extract(r"awk -F '\\t' '(.*?)'", TEST_WORKFLOW, re.S)

        for address in addresses:
            with self.subTest(address=address):
                ci = subprocess.run(
                    ["awk", "-F", "\\t", awk_program], capture_output=True, text=True,
                    input=f"0000000\t{address}\t{address}\n",
                )
                self.assertEqual(ci.returncode, 0, ci.stderr)
                ci_rejects = bool(ci.stdout.strip())

                _git(self.repo, "config", "user.email", address or "x")
                env = {"GIT_AUTHOR_EMAIL": address, "GIT_COMMITTER_EMAIL": address}
                local = _attempt_commit(self.repo, f"fix: address {len(address)}", env=env)
                local_rejects = local.returncode != 0

                self.assertEqual(
                    local_rejects, ci_rejects,
                    f"the hook and the CI awk disagree about {address!r}: "
                    f"hook rejects={local_rejects}, CI rejects={ci_rejects}",
                )

    def test_the_hooks_are_executable(self):
        """git skips a non-executable hook without a word, which is the quietest way
        for this gate to stop existing."""
        for hook in (COMMIT_MSG_HOOK, PRE_COMMIT_HOOK):
            with self.subTest(hook=hook.name):
                self.assertTrue(os.access(hook, os.X_OK), f"{hook} is not executable")

    def test_the_install_command_is_recorded_where_a_developer_will_look(self):
        """A hook nobody installs protects nobody, so the one-line install command has
        to be readable from the files a developer already opens."""
        for path in (PRE_COMMIT_CONFIG, TEST_WORKFLOW, COMMIT_MSG_HOOK, PRE_COMMIT_HOOK):
            with self.subTest(path=path.name):
                self.assertIn(INSTALL_COMMAND, path.read_text(encoding="utf-8"))


def _git_log_count(repo: Path) -> int:
    result = subprocess.run(["git", "-C", str(repo), "rev-list", "--count", "--all"],
                            capture_output=True, text=True, env=GIT_ENV)
    return int(result.stdout.strip() or 0)


if __name__ == "__main__":
    unittest.main()
