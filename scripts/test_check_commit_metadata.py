#!/usr/bin/env python3
"""The commit metadata gate must refuse a message that describes the tooling.

Run it directly; it needs no bench and no site:

    python3 scripts/test_check_commit_metadata.py

The published message this covers is NOT copied in here. It is read back out of
git by sha, so the repository keeps exactly one copy of it -- pasting the text
into a tracked file to test a rule against it would publish the leak a second
time, which is the thing the rule exists to prevent.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GATE = REPO_ROOT / "scripts" / "check_commit_metadata.py"
COMMIT_MSG_HOOK = REPO_ROOT / ".githooks" / "commit-msg"

# The commit whose message the owner flagged: it names a shared helper, three
# maintenance scripts, an unpublished directory, and what the build did.
LEAKY_SHA = "12d4e745"

HAVE_GIT = shutil.which("git") is not None

# A personal core.excludesFile would change which paths git calls ignored, and the
# ignored-path rule asks git. Neutralise it so a verdict is the repository's, not
# the machine's.
GIT_ENV = {**os.environ,
           "GIT_CONFIG_GLOBAL": os.devnull,
           "GIT_CONFIG_SYSTEM": os.devnull}

# One shape per rule, written out rather than derived, so a rule that stops firing
# fails here instead of quietly narrowing.
SHAPES = {
    "owner tool or guard script named": "Stop comment_audit walking untracked files\n",
    "internal guard or CI process narrated": "Fix the list\n\nThe trunk went red.\n",
    "git-ignored path named": "Fix the list\n\nRows under apex/demo/ were counted.\n",
}

# Describes the same change as LEAKY_SHA -- what the code now does for whoever reads
# the result -- without naming a tool, the build, or a path a clone never receives.
CLEAN_REWRITE = """Grade the source list the way a fresh clone receives it

Source enumeration walked the filesystem, so a file that is never published could
still decide the outcome on one machine while a published checkout saw something
else. Enumeration now comes from the tracked file list, and the filesystem walk
survives only for a tree kept outside version control.
"""


def run_gate(message: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Judge a message through the real process boundary the hooks use."""
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                     encoding="utf-8") as handle:
        handle.write(message)
        path = handle.name
    try:
        return subprocess.run(
            [sys.executable, str(GATE), "message", path],
            capture_output=True, text=True, cwd=str(cwd or REPO_ROOT), env=GIT_ENV)
    finally:
        os.unlink(path)


@unittest.skipUnless(GATE.exists(), "the gate is not part of this install")
class TestToolingRules(unittest.TestCase):
    def test_refuses_every_shape_and_names_its_rule(self):
        for rule, message in SHAPES.items():
            with self.subTest(rule=rule):
                result = run_gate(message)
                self.assertEqual(result.returncode, 1,
                                 f"{rule} was not refused: {result.stdout}")
                self.assertIn(rule, result.stderr)

    def test_accepts_a_clean_rewrite_of_the_same_change(self):
        """The rule must leave a way to describe the work, or it just teaches bypassing."""
        result = run_gate(CLEAN_REWRITE)
        self.assertEqual(result.returncode, 0,
                         f"a clean rewrite was refused:\n{result.stderr}")

    def test_a_slash_separated_extension_list_is_not_a_path(self):
        """Prose separates alternatives with slashes too. Reading `.py/.json/.js` as a
        directory five deep refused an honest message when this rule first ran over
        the existing history."""
        result = run_gate("Validate more file kinds\n\n"
                          "The check now covers .py/.json/.js/.html/.md inputs.\n")
        self.assertEqual(result.returncode, 0,
                         f"an extension list was read as a path:\n{result.stderr}")

    def test_a_published_path_is_not_treated_as_ignored(self):
        """`docs/*` hides the directory and a later `!` line publishes one file back
        out of it. Asking git is what gets that pair right; a list here would not."""
        result = run_gate("Document the integration surface\n\n"
                          "Expanded docs/INTEGRATION.md with the callback contract.\n")
        self.assertEqual(result.returncode, 0,
                         f"a published path was refused:\n{result.stderr}")


@unittest.skipUnless(HAVE_GIT, "git is required to read the message back")
@unittest.skipUnless(GATE.exists(), "the gate is not part of this install")
class TestThePublishedMessage(unittest.TestCase):
    """The regression fixture: the real text, read from git, never copied here."""

    @classmethod
    def setUpClass(cls):
        found = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "log", "-1", "--format=%B", LEAKY_SHA],
            capture_output=True, text=True, env=GIT_ENV)
        if found.returncode != 0 or not found.stdout.strip():
            raise unittest.SkipTest(f"{LEAKY_SHA} is not in this clone")
        cls.message = found.stdout

    def test_it_is_refused(self):
        result = run_gate(self.message)
        self.assertEqual(result.returncode, 1,
                         f"the flagged message passed:\n{result.stdout}")

    def test_every_rule_it_breaks_is_named(self):
        stderr = run_gate(self.message).stderr
        for rule in SHAPES:
            self.assertIn(rule, stderr, f"{rule} went unreported")

    def test_the_message_body_is_not_echoed(self):
        """A refusal that reprints the prose republishes it into every log that
        captures the refusal. Findings carry the matched token, never the line."""
        stderr = run_gate(self.message).stderr
        body = [line.strip() for line in self.message.splitlines() if line.strip()]
        for line in body:
            self.assertNotIn(line, stderr, f"the refusal echoed the message: {line!r}")


@unittest.skipUnless(HAVE_GIT, "git is required to run the hook")
@unittest.skipUnless(COMMIT_MSG_HOOK.exists(), "the hook is not part of this install")
class TestTheHookRefusesARealCommit(unittest.TestCase):
    """Judging the gate directly proves the rule. Only a real commit attempt proves
    the hook is wired to it, which is the thing that actually stops a leak."""

    def setUp(self):
        self.repo = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.repo, ignore_errors=True)
        # The hook resolves the gate relative to ITSELF, so the fixture has to carry
        # both in the same shape the repository does.
        (self.repo / ".githooks").mkdir()
        (self.repo / "scripts").mkdir()
        shutil.copy2(COMMIT_MSG_HOOK, self.repo / ".githooks" / "commit-msg")
        shutil.copy2(GATE, self.repo / "scripts" / "check_commit_metadata.py")
        self._git("init", "-q")
        self._git("config", "core.hooksPath", ".githooks")
        self._git("config", "user.email", "1+dev@users.noreply.github.com")
        self._git("config", "user.name", "Dev")
        (self.repo / "value.py").write_text("value = 1\n", encoding="utf-8")
        self._git("add", "-A")

    def _git(self, *args, check=True):
        return subprocess.run(["git", "-C", str(self.repo), *args], check=check,
                              capture_output=True, text=True, env=GIT_ENV)

    def _log(self):
        return self._git("log", "--oneline", check=False).stdout

    def test_the_hook_refuses_and_records_nothing(self):
        before = self._log()
        attempt = self._git("commit", "-m", SHAPES["owner tool or guard script named"],
                            check=False)
        self.assertNotEqual(attempt.returncode, 0,
                            f"the hook allowed the commit:\n{attempt.stdout}")
        self.assertIn("owner tool or guard script named", attempt.stderr)
        self.assertEqual(self._log(), before, "a refused commit was still recorded")

    def test_the_same_hook_admits_a_clean_message(self):
        """Guard of the guard: a hook that refuses everything proves nothing above."""
        attempt = self._git("commit", "-m", CLEAN_REWRITE, check=False)
        self.assertEqual(attempt.returncode, 0,
                         f"the hook refused a clean message:\n{attempt.stderr}")
        self.assertNotEqual(self._log(), "", "the clean commit was not recorded")


if __name__ == "__main__":
    unittest.main(verbosity=2)
