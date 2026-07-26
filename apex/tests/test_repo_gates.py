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
metadata gate. That one is no longer two copies kept in step: `scripts/
check_commit_metadata.py` is its single definition, and the hooks under `.githooks`
and the CI step all invoke it. So the tests below judge the VERDICT each lane
returns rather than comparing one lane's source text with another's.
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
COMMIT_METADATA_GATE = SCRIPTS / "check_commit_metadata.py"

GITHOOKS = REPO_ROOT / ".githooks"
COMMIT_MSG_HOOK = GITHOOKS / "commit-msg"
PRE_COMMIT_HOOK = GITHOOKS / "pre-commit"
PRE_PUSH_HOOK = GITHOOKS / "pre-push"
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


def _git(repo: Path, *args: str, env=None) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True, env={**GIT_ENV, **(env or {})})


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


def _force_commit(repo: Path, message: str, env=None) -> None:
    """Record a commit the way `--no-verify` does, so the after-the-fact lane has
    something to judge. That case is exactly why pre-push and the CI step exist."""
    _write(repo, "payload.txt", os.urandom(8).hex())
    _git(repo, "add", "-A")
    _git(repo, "commit", "--no-verify", "-m", message, env=env)


def _gate(*args: str, cwd: str = "") -> subprocess.CompletedProcess:
    """Drive the shared gate as a process, which is how every caller drives it. The
    exit code is the contract; no string inside the file is."""
    return subprocess.run([sys.executable, str(COMMIT_METADATA_GATE), *args],
                          capture_output=True, text=True, env=GIT_ENV,
                          cwd=cwd or tempfile.gettempdir())


ROBOT = "\U0001F916"
LEAKED_TRAILER = "Co-Authored-By: " + "Claude Opus 5 (1M context) <noreply@anthropic.com>"
CLEAN_SUBJECT = "fix: repoint the dead compliance link"
PROSE_SUBJECT = "fix: correct the maintenance codex reference"

# Refusal follows the SHAPE of attribution - a trailer, a session line, a generation
# notice, a vendor host - not the presence of a vendor word. The old substring pattern
# made PROSE_SUBJECT below unphraseable: it is ordinary English, and no rewording of it
# could have been committed.
MESSAGE_TABLE = (
    ("fix: something real\n\n" + LEAKED_TRAILER, True),
    ("fix: something real\n\nClaude-Session: https://example.invalid/s/1", True),
    ("fix: something real\n\n" + ROBOT
     + " Generated with [Claude Code](https://claude.com/claude-code)", True),
    ("fix: something real\n\nCo-Authored-By: ChatGPT <bot@openai.com>", True),
    ("fix: something real\n\nGenerated with Codex", True),
    ("docs: quote https://claude.ai/code/session_abc in the runbook", True),
    (PROSE_SUBJECT, False),
    ("fix: vent the openair duct above the plant room", False),
    ("docs: cite the anthropic principle in the survey note", False),
    (CLEAN_SUBJECT, False),
    ("chore: credit the reviewer\n\nCo-Authored-By: A Reviewer <" + PUBLIC_EMAIL + ">", False),
)

# The allowlist admits the two forms GitHub hands out for a hidden address and nothing
# else, which is what the retired shell `case` and the retired CI awk both admitted.
ADDRESS_TABLE = (
    ("noreply@github.com", False),
    ("248423400+iabodysa@users.noreply.github.com", False),
    ("@users.noreply.github.com", False),
    ("dev@example.com", True),
    ("noreply@anthropic.com", True),
    ("dev@users.noreply.github.example.com", True),
    ("users.noreply.github.com", True),
)

GATE_INVOCATION = "scripts/check_commit_metadata.py"
# "claude" is deliberately not in this list: an unrelated workflow step greps for a
# `.claude/` path, and a directory name is not a second copy of the rule.
VENDOR_TOKENS = ("anthropic", "chatgpt", "openai")


@unittest.skipUnless(HAVE_GIT, "git is required to run the hooks")
@unittest.skipUnless(COMMIT_MSG_HOOK.exists(), ".githooks is not present in this install")
@unittest.skipUnless(TEST_WORKFLOW.exists(), ".github is not present in this install")
@unittest.skipUnless(COMMIT_METADATA_GATE.exists(), "scripts/ is not present in this install")
class TestCommitMetadataGate(unittest.TestCase):
    """One rule, one file, three lanes that have to reach the same verdict.

    Commit 43955b8f reached origin carrying an attribution trailer and a session
    URL. CI caught it, but only after the push, and the red landed on a job named
    Tests — which reads as "a test failed" when it means "the metadata guard fired
    and this job's tests never ran". The hooks under .githooks move that refusal to
    before the commit exists.

    Those hooks used to hold their own copy of the pattern and this class compared the
    two strings. Comparing strings stops proving anything once there is only one
    string, so what is tested now is the decision itself, taken through each caller:
    the gate directly, a real commit through the installed hooks, and the recorded
    range the CI step judges.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.repo = Path(self.tmp)
        _init_hooked_repo(self.repo)
        self.scratch = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.scratch, True)

    def _judge_as_hook(self, message: str) -> bool:
        """The commit-msg lane: one prepared message file, judged before any commit."""
        path = self.scratch / "message.txt"
        path.write_text(message, encoding="utf-8")
        return _gate("message", str(path)).returncode != 0

    def test_the_rule_has_exactly_one_definition(self):
        """Every caller points at the one file, and no caller carries a copy of the
        vocabulary. This is what the retired byte-identity test was really protecting."""
        gate_body = COMMIT_METADATA_GATE.read_text(encoding="utf-8").lower()
        for token in VENDOR_TOKENS:
            self.assertIn(token, gate_body, "the single definition lost part of its rule")

        for path in (COMMIT_MSG_HOOK, PRE_COMMIT_HOOK, PRE_PUSH_HOOK, TEST_WORKFLOW):
            with self.subTest(path=path.name):
                body = path.read_text(encoding="utf-8")
                self.assertIn(GATE_INVOCATION, body,
                              f"{path.name} no longer reaches the one definition of the rule")
                for token in VENDOR_TOKENS:
                    self.assertNotIn(
                        token, body.lower(),
                        f"{path.name} carries a second copy of the rule, which is what "
                        "collapsing the two greps into one script removed",
                    )

    def test_every_lane_decides_the_message_table_alike(self):
        """The three lanes on one table. A disagreement here is the failure the old
        mirror test existed to catch, proven by verdict instead of by string."""
        for message, refused in MESSAGE_TABLE:
            with self.subTest(subject=message.splitlines()[0], refused=refused):
                self.assertEqual(self._judge_as_hook(message), refused,
                                 "the gate decided this message wrongly")

                real = _attempt_commit(self.repo, message)
                self.assertEqual(real.returncode != 0, refused,
                                 f"the installed hook disagreed: {real.stderr}")

                if real.returncode != 0:
                    _force_commit(self.repo, message)
                ci = _gate("range", "-1", "HEAD", cwd=str(self.repo))
                self.assertEqual(ci.returncode != 0, refused,
                                 f"the CI lane disagreed: {ci.stdout}{ci.stderr}")

    def test_a_vendor_word_in_ordinary_prose_still_commits(self):
        """The trap this collapse was for: `codex` is an English word, and under a
        substring pattern this sentence could not be phrased at all."""
        result = _attempt_commit(self.repo, PROSE_SUBJECT)

        self.assertEqual(result.returncode, 0, f"ordinary prose was refused: {result.stderr}")
        self.assertEqual(_git_log_count(self.repo), 1)

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

    def test_every_lane_classifies_the_same_addresses_alike(self):
        """The address allowlist used to be a shell `case` in the hook and an awk
        function in the workflow, and this test ran both to prove they agreed. There is
        now one allowlist, so the table below also pins WHAT it must decide."""
        for address, refused in ADDRESS_TABLE:
            with self.subTest(address=address, refused=refused):
                self.assertEqual(_gate("email", address, address).returncode != 0, refused,
                                 "the gate classified this address wrongly")

                env = {"GIT_AUTHOR_EMAIL": address, "GIT_COMMITTER_EMAIL": address}
                real = _attempt_commit(self.repo, CLEAN_SUBJECT, env=env)
                self.assertEqual(real.returncode != 0, refused,
                                 f"the installed hook disagreed about {address!r}: {real.stderr}")

                if real.returncode != 0:
                    _force_commit(self.repo, CLEAN_SUBJECT, env=env)
                ci = _gate("range", "-1", "HEAD", cwd=str(self.repo))
                self.assertEqual(ci.returncode != 0, refused,
                                 f"the CI lane disagreed about {address!r}: {ci.stdout}{ci.stderr}")

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
