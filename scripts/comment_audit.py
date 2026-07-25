#!/usr/bin/env python3
"""Comment-policy gate: comments are 1-2 lines of WHY, never banner art, never a
process/task id. Flags the mechanically-detectable violations — decorative
dividers, over-long comment blocks (essays that belong in a design note), and
T-#### ids that rot the moment the board moves on.

Stdlib-only and self-contained ON PURPOSE: the maintainer's local toolbox is not
installable on a CI runner, so the gate has to live in the repo to run there.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

CONSEC_LIMIT = 8  # a run of >= this many full-line comments is an essay
_TASK_ID = re.compile(r"\bT-\d{1,5}\b")
_BANNER = re.compile(r"(={6,}|-{6,}|#{4,}|\*{6,}|/{4,})")
# Tool directives, not prose: they are allowed to look like anything.
_PY_SKIP = re.compile(
    r"noqa|type:|pragma|pyright|ruff|isort|nosec|mypy|bandit|fmt:\s*(off|on|skip)|coding[:=]|^#!"
)
_EXCLUDED = ("/node_modules/", "/__pycache__/", "/.git/", "/dist/", "/build/",
             "/public/dist/", "/.ruff_cache/")
_EXTS = {".py", ".js", ".ts", ".jsx", ".tsx", ".mjs"}


def _find_marker(line: str, marker: str) -> int:
    """Index of `marker` (# or //) that is NOT inside a quoted string; -1 if none.
    Quote-aware so a trailing comment is found and a marker inside a literal isn't."""
    i, n, quote = 0, len(line), None
    while i < n:
        char = line[i]
        if quote:
            if char == "\\":
                i += 2
                continue
            if char == quote:
                quote = None
        elif char in "'\"":
            quote = char
        elif line.startswith(marker, i):
            return i
        i += 1
    return -1


def _comment(line: str, ext: str, in_block: bool) -> tuple[str | None, bool, bool]:
    """Return (comment_text|None, is_full_line_comment, still_in_block)."""
    if ext == ".py":
        idx = _find_marker(line, "#")
        if idx < 0:
            return None, False, False
        return line[idx + 1:].strip(), line[:idx].strip() == "", False
    if in_block:
        if "*/" in line:
            return line.split("*/")[0].strip(" *\t"), True, False
        return line.strip(" *\t"), True, True
    idx = _find_marker(line, "//")
    bidx = _find_marker(line, "/*")
    if bidx >= 0 and (idx < 0 or bidx < idx):
        if "*/" in line[bidx:]:
            return line[bidx + 2:].split("*/")[0].strip(" *\t"), line[:bidx].strip() == "", False
        return line[bidx + 2:].strip(" *\t"), line[:bidx].strip() == "", True
    if idx >= 0:
        return line[idx + 2:].strip(), line[:idx].strip() == "", False
    return None, False, False


def scan_file(path: Path) -> list[dict]:
    findings: list[dict] = []
    ext = path.suffix.lower()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return findings
    in_block = False
    run_start = run_len = 0

    def flush() -> None:
        if run_len >= CONSEC_LIMIT:
            findings.append({
                "line": run_start,
                "kind": "long-block",
                "detail": f"{run_len} consecutive comment lines (move rationale to a design note)",
            })

    for lineno, raw in enumerate(lines, 1):
        text, is_full, in_block = _comment(raw, ext, in_block)
        if is_full:
            if run_len == 0:
                run_start = lineno
            run_len += 1
        else:
            flush()
            run_len = 0
        if text is None:
            continue
        if ext == ".py" and _PY_SKIP.search(text):
            continue
        task_id = _TASK_ID.search(text)
        if task_id:
            findings.append({"line": lineno, "kind": "task-id",
                             "detail": f"process/task id in comment: {task_id.group()}"})
        if _BANNER.search(text):
            findings.append({"line": lineno, "kind": "banner",
                             "detail": "decorative divider — noise that drifts from the code"})
    flush()
    return findings


def git_files(root: Path) -> list[Path] | None:
    """Files git accounts for under `root`, or None when git cannot answer.

    Tracked plus not-yet-added files, never ignored ones. CI audits a fresh
    checkout, so a gitignored file exists only on a developer's disk; letting one
    set the exit code makes the local verdict disagree with the CI lane.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z",
             "--cached", "--others", "--exclude-standard"],
            capture_output=True, check=False,
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    names = proc.stdout.decode("utf-8", "surrogateescape").split("\0")
    return [root / name for name in names if name]


def iter_files(root: Path) -> list[Path]:
    """Auditable source files. Falls back to a raw walk outside a work tree (an
    sdist or tarball), so a missing git degrades to the old behaviour, never to a
    silent empty set that would pass everything."""
    candidates = git_files(root)
    if candidates is None:
        candidates = root.rglob("*")
    return sorted(
        path for path in candidates
        if path.suffix.lower() in _EXTS
        and not any(part in str(path) for part in _EXCLUDED)
        and path.is_file()
    )


def scan_tree(root: Path) -> list[dict]:
    out: list[dict] = []
    for path in iter_files(root):
        for finding in scan_file(path):
            out.append({"file": str(path.relative_to(root)), **finding})
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default="apex", help="Directory to scan")
    parser.add_argument("--json", action="store_true", help="Machine output")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    findings = scan_tree(root)
    if args.json:
        print(json.dumps({"root": str(root), "count": len(findings), "findings": findings},
                         ensure_ascii=False, indent=2))
        return 1 if findings else 0
    if not findings:
        print("comment-audit: clean — no policy violations.")
        return 0
    by_kind: dict[str, int] = {}
    for finding in findings:
        by_kind[finding["kind"]] = by_kind.get(finding["kind"], 0) + 1
        print(f'  {finding["file"]}:{finding["line"]}  [{finding["kind"]}]  {finding["detail"]}')
    print(f"\ncomment-audit: {len(findings)} violations — "
          + " · ".join(f"{k}={n}" for k, n in sorted(by_kind.items())))
    print("Fix: comments are 1-2 lines of WHY. Drop dividers, move essays to docs/, "
          "and keep board ids out of source.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
