#!/usr/bin/env python3
"""Commit metadata gate: no automated attribution, no session metadata, no private
address and no description of the tooling in anything that becomes public history.

This file is the ONLY definition of that rule. The commit-msg hook, the pre-commit
hook, the pre-push hook and the CI step "No automated attribution or private commit
email" all invoke it, so a workstation verdict and a CI verdict cannot come to mean
different things. It replaced a grep in the workflow and a second grep in the hook,
which were byte-identical only for as long as someone kept them so, and which could
not use a word boundary at all: GNU grep on the runner and BSD grep on macOS do not
agree on one, so adding it would have manufactured the very divergence the gate
exists to prevent. Python's `re` is the same engine on both.

Stdlib-only on purpose: the maintainer's toolbox is not installable on a CI runner,
so the gate has to live in the repo to run there.

Usage:
    check_commit_metadata.py message <file>               a prepared message (commit-msg)
    check_commit_metadata.py email <author> <committer>   two addresses (pre-commit)
    check_commit_metadata.py range <git-log-options...>   recorded commits (CI, pre-push)
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

VENDORS = ("claude", "anthropic", "codex", "openai", "chatgpt")
VENDOR = "|".join(VENDORS)
ROBOT = "\U0001f916"

# Attribution is a SHAPE - a trailer, a generation notice, a vendor host - not a
# vocabulary. Matching the bare vendor word refused `fix: correct the maintenance codex
# reference`, an ordinary English sentence that no rephrasing could have got past.
ATTRIBUTION_RULES = (
    (
        "automated author in a commit trailer",
        re.compile(
            r"^[ \t]*(?:co-authored-by|co-committed-by|authored-by|assisted-by"
            r"|generated-by|created-by|written-by|on-behalf-of)[ \t]*:"
            rf"[^\n]*(?:{VENDOR})",
            re.I | re.M,
        ),
    ),
    (
        "session metadata trailer",
        re.compile(r"^[ \t]*[a-z0-9_-]*session[ \t]*:", re.I | re.M),
    ),
    (
        "machine-generation notice",
        re.compile(
            rf"{ROBOT}"
            rf"|\b(?:generated|co-?authored)[ \t]+(?:with|by)\b[^\n]*(?:{VENDOR})",
            re.I | re.M,
        ),
    ),
    (
        "vendor host, product URL or address",
        re.compile(rf"\b(?:{VENDOR})\.(?:ai|com|org|net|io)\b", re.I),
    ),
)

# A message describes what the CODE does for a user of the application. It never
# describes the tooling that found the problem, the process around it, or a path the
# published tree does not contain: a reader who clones this repo can open none of
# those, so the sentence is noise at best, and at worst it publishes the shape of a
# private toolbox to everyone who reads the log.
#
# Declared ONCE, here, beside the attribution rules that already work this way. Every
# entry is a snake_case identifier - none is an English phrase, so a bare mention is
# always a reference to the tool and never ordinary prose. That is exactly why these
# may be matched as whole words where a bare vendor word could not be: `codex` is a
# word, `check_translations` is a filename.
TOOL_NAMES = (
    "all_py_files",
    "check_commit_metadata",
    "check_doctype_dates",
    "check_translations",
    "comment_audit",
    "run_guards",
)

# Multi-word on purpose. A single word - "guard", "gate", "lane", "hook" - is ordinary
# product vocabulary here: the app itself ships report_role_guard and a workflow guard,
# and refusing those would repeat the mistake the attribution rules already learned.
# Only phrases that cannot be anything but a sentence about this repository's own
# machinery are listed.
GUARD_PHRASES = (
    r"\bCI\b[^\n]{0,20}?\b(?:stayed|was|went|turned|remained)\s+(?:green|red)",
    r"\b(?:redden(?:ed|s)?|red)\s+the\s+trunk\b",
    r"\btrunk\s+(?:went|stayed|turned|was)\s+(?:red|green)\b",
    r"\b(?:pre-push|pre-commit|commit-msg)\s+hook\b",
    r"--no-verify",
    r"\bgitleaks\b",
    r"\b(?:Lint|Tests)\s+(?:lane|job|workflow)\b",
    r"\bdead-(?:function|code)\s+guard\b",
)

TOOLING_RULES = (
    (
        "owner tool or guard script named",
        re.compile(r"\b(?:" + "|".join(TOOL_NAMES) + r")\b"),
    ),
    (
        "internal guard or CI process narrated",
        re.compile("|".join(GUARD_PHRASES), re.I),
    ),
)

# A slash-bearing token is the only shape worth asking git about. A bare word is not a
# path, and handing git every word would make the verdict depend on what happens to sit
# on this disk rather than on what the repository publishes.
PATH_TOKEN = re.compile(r"(?<![\w./-])((?:[\w.@-]+/)+[\w.@-]*)")

# Prose separates alternatives with slashes too: `.py/.json/.js/.html/.md` is a list of
# extensions, not a directory five deep. One leading-dot segment is an ordinary path
# (.github/workflows/lint.yml); two or more in a row is a list, and reading it as a path
# refused an honest message.
EXTENSION_SEGMENT = re.compile(r"^\.\w+$")

PUBLIC_EMAIL = "noreply@github.com"
PUBLIC_SUFFIX = "@users.noreply.github.com"

# `git commit -v` appends a diff below this marker; it is not part of the message and
# would match on unrelated code.
SCISSORS = re.compile(r"^#.*>8", re.M)

FIELD = "\x1f"
RECORD = "\x00"
# Spelled as git's own escapes, never as the bytes: a literal NUL cannot be passed in
# argv at all. Both separators are control characters a commit message cannot carry.
LOG_FORMAT = "--format=%H%x1f%ae%x1f%ce%x1f%B%x00"

USAGE = (
    "usage: check_commit_metadata.py message <file>\n"
    "       check_commit_metadata.py email <author> <committer>\n"
    "       check_commit_metadata.py range <git-log-options...>\n"
)


def email_is_public(email: str) -> bool:
    """The two forms GitHub hands out for a hidden address, and nothing else: any other
    value is a real mailbox that a public history would publish forever."""
    return email == PUBLIC_EMAIL or email.endswith(PUBLIC_SUFFIX)


def ignored_paths(message: str) -> list[str]:
    """The paths a message names that git says a clone does not receive.

    Derived from git, never from a list here: .gitignore already IS the declaration of
    what stays unpublished, and only git resolves its negations correctly - `docs/*`
    hides the directory and a later `!docs/INTEGRATION.md` publishes one file back out
    of it, which no second copy of the rules in this file would get right for long."""
    # Ask about BOTH shapes of every token, and remember which one the message wrote.
    # A directory-only rule (`apex/demo/`) matches the trailing-slash form only, and git
    # cannot infer directoryness for a path that is absent here - which it always is,
    # because a path being absent is precisely what makes it worth refusing.
    asked: dict[str, str] = {}
    for match in PATH_TOKEN.finditer(message):
        # Trailing sentence punctuation belongs to the prose, not to the path.
        written = match.group(1).rstrip(".,;:")
        bare = written.rstrip("/")
        if not bare:
            continue
        segments = bare.split("/")
        if sum(1 for part in segments if EXTENSION_SEGMENT.match(part)) > 1:
            continue
        asked.setdefault(bare, written)
        asked.setdefault(bare + "/", written)
    if not asked:
        return []
    # --no-index judges the RULES, not whether the path is tracked: without it git
    # declines to answer for anything in the index, so a published file could never be
    # distinguished from an unpublished one.
    code, out = _git(["check-ignore", "--no-index", "--stdin"], "\n".join(asked) + "\n")
    if code not in (0, 1):
        # Never silent: a rule that stops running without saying so is the failure this
        # whole file exists to prevent.
        sys.stderr.write("commit-metadata: WARNING - git could not resolve the ignore "
                         "rules, so the ignored-path rule DID NOT RUN\n")
        return []
    hits: dict[str, None] = {}
    for line in out.splitlines():
        answer = line.strip()
        if answer in asked:
            hits[asked[answer]] = None
    return list(hits)


def scan_tooling(message: str) -> list[str]:
    """Every "this describes the tooling, not the change" finding in one message.

    Reports the matched TOKEN, never the line. The attribution rules above quote the
    whole line and are right to: their offending text is a trailer the author deletes
    verbatim. Here the offending text is the commit's own prose, so echoing the line
    would reprint into the refusal - and into any log that captures it - the very
    sentence the rule exists to keep out of public sight."""
    findings: dict[str, None] = {}
    for kind, rule in TOOLING_RULES:
        for match in rule.finditer(message):
            number = message.count("\n", 0, match.start()) + 1
            # A phrase may be wrapped across the message's own line break; report it as
            # the phrase it is, so the reader can search for it.
            token = " ".join(match.group(0).split())
            findings[f"{number}: {kind}: {token!r}"] = None
    for token in ignored_paths(message):
        findings[f"git-ignored path named: {token!r}"] = None
    return list(findings)


def scan_message(message: str) -> list[str]:
    """Every attribution finding in one message, as `<line>: <kind>: <text>`."""
    lines = message.splitlines()
    # A line can satisfy one rule twice (a generation notice carrying a vendor URL);
    # report the line once per rule so the refusal reads as a list of problems.
    findings: dict[str, None] = {}
    for kind, rule in ATTRIBUTION_RULES:
        for match in rule.finditer(message):
            number = message.count("\n", 0, match.start()) + 1
            text = lines[number - 1].strip() if number <= len(lines) else ""
            findings[f"{number}: {kind}: {text}"] = None
    findings.update(dict.fromkeys(scan_tooling(message)))
    return list(findings)


def scan_emails(author: str, committer: str) -> list[str]:
    return [
        f"private {role} email: {email!r}"
        for role, email in (("author", author), ("committer", committer))
        if not email_is_public(email)
    ]


def _git(args: list[str], stdin: str | None = None) -> tuple[int, str]:
    try:
        proc = subprocess.run(["git", *args], input=stdin, capture_output=True,
                              text=True, errors="replace")
    except OSError as exc:
        return 127, str(exc)
    return proc.returncode, proc.stdout if proc.returncode == 0 else proc.stderr


def prepared_message(raw: str) -> str:
    """What git will STORE, not the editor buffer: the scissors block goes, then the
    comment lines, leaving what `--format=%s%n%b` would report.

    Comment stripping is delegated to git so the answer matches git's own idea of a
    comment (core.commentChar is configurable); the fallback keeps the hook working on
    a machine where git cannot be executed rather than passing an unjudged message."""
    cut = SCISSORS.search(raw)
    if cut:
        raw = raw[: cut.start()]
    code, out = _git(["stripspace", "--strip-comments"], raw)
    if code == 0:
        return out
    return "\n".join(line for line in raw.splitlines() if not line.startswith("#"))


def scan_range(log_options: list[str]) -> list[str]:
    """Judge recorded commits, message and identity together. This is the CI lane and
    the pre-push lane: it catches what --no-verify, or an uninstalled hook, let past."""
    code, out = _git(["log", LOG_FORMAT, *log_options])
    if code != 0:
        sys.stderr.write(out)
        raise SystemExit(2)

    findings: list[str] = []
    for record in out.split(RECORD):
        record = record.strip("\n")
        if not record:
            continue
        parts = record.split(FIELD, 3)
        if len(parts) != 4:
            findings.append(f"unreadable git log record, refusing to pass it: {record!r}")
            continue
        sha, author, committer, message = parts
        found = scan_message(message) + scan_emails(author, committer)
        findings.extend(f"{sha[:12]} {item}" for item in found)
    return findings


def main(argv: list[str]) -> int:
    # Hand-rolled instead of argparse: a first push is judged as `range -1 <sha>`, and
    # argparse would read that leading -1 as an unknown option and refuse to start.
    mode = argv[0] if argv else ""
    if mode == "message" and len(argv) == 2:
        raw = Path(argv[1]).read_text(encoding="utf-8", errors="replace")
        findings = scan_message(prepared_message(raw))
    elif mode == "email" and len(argv) == 3:
        findings = scan_emails(argv[1], argv[2])
    elif mode == "range" and len(argv) >= 2:
        findings = scan_range(argv[1:])
    else:
        sys.stderr.write(USAGE)
        return 2

    if not findings:
        print("commit-metadata: clean - describes the code, not the tooling; "
              "no automated attribution, no private address.")
        return 0

    sys.stderr.write("commit-metadata: this message carries automated attribution, "
                     "session metadata, a private address, or a description of the "
                     "tooling rather than of the change:\n")
    for item in findings:
        sys.stderr.write(f"  {item}\n")
    sys.stderr.write(
        "commit-metadata: this is the same gate CI runs, so pushing it would turn the "
        "Tests workflow red.\n"
        "commit-metadata: say what the change does for a user of the application - not "
        "which tool found it, not what the build did, and not a path a clone never\n"
        "commit-metadata: receives. Drop the trailer, or fix the address with\n"
        "  git config user.email '<id>+<user>@users.noreply.github.com'\n")
    return 1


if __name__ == "__main__":
    # A finding can quote a robot emoji; a runner with a non-UTF-8 locale must still be
    # able to print the refusal instead of dying inside the gate.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    sys.exit(main(sys.argv[1:]))
