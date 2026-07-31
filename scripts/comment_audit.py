#!/usr/bin/env python3
"""Comment-policy gate: prose in the source says WHY, never who filed it.

Flags the mechanically-detectable violations in comments, in Python docstrings,
and in the strings a reader sees without opening the file (assertion messages,
throw/msgprint text, translated strings): decorative dividers, over-long comment
runs and docstrings, and board ids (T-/P-/A-/R-) that rot the moment the board
moves on. Board ids rank by WHO READS THEM -- a message reaches someone who
never opens the source, so it is the worst place for one.

Stdlib-only and self-contained ON PURPOSE: the maintainer's local toolbox is not
installable on a CI runner, so the gate has to live in the repo to run there.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from pathlib import Path

CONSEC_LIMIT = 8  # a run of >= this many full-line comments is an essay
# A docstring may carry real rationale, so this ceiling sits well above a normal
# one; it exists to catch the essay, not to evict a reason. Calibrated 2026-07-27
# against every docstring under apex/ -- see _BASELINE for what it caught.
DOCSTRING_LIMIT = 45
# Board ids are zero-padded to three digits (205 of them, none shorter), and the
# padding is what separates them from domain data: `P-1`/`P-2` are project codes
# and `R-1` is a room, all of them legitimate test fixtures.
_TASK_ID = re.compile(r"\b[TPAR]-\d{3,5}\b")
_BANNER = re.compile(r"(={6,}|-{6,}|#{4,}|\*{6,}|/{4,})")
# Tool directives, not prose: they are allowed to look like anything.
_PY_SKIP = re.compile(
    r"noqa|type:|pragma|pyright|ruff|isort|nosec|mypy|bandit|fmt:\s*(off|on|skip)|coding[:=]|^#!"
)
_EXCLUDED = ("/node_modules/", "/__pycache__/", "/.git/", "/dist/", "/build/",
             "/public/dist/", "/.ruff_cache/")
_EXTS = {".py", ".js", ".ts", ".jsx", ".tsx", ".mjs"}

# Calls whose string arguments reach a human who never opens the file.
_MESSAGE_CALLS = ("throw", "msgprint", "log_error", "print", "_", "__", "_lt")

KIND_COMMENT_ID = "task-id"
KIND_DOCSTRING_ID = "docstring-task-id"
KIND_MESSAGE_ID = "message-task-id"
KIND_LONG_DOCSTRING = "long-docstring"


# The declared tolerances, measured 2026-07-27 over the whole package. Exact and
# per file, so one MORE fails and a drained entry fails until it is pruned;
# padding it names a file with no such finding, which is the same failure.
_BASELINE: dict[str, dict[str, int]] = {
    # A DEFERRAL, the only one here: 1 of the 32 assertion-message ids survived
    # the drain because another agent holds this file under an active
    # reservation. It goes when the reservation lifts.
    "tests/test_workspace_role_docperm_guard.py": {"message-task-id": 1},

    # DECLARED, not deferred: the essay-length docstrings, each one a guard's
    # rationale sitting beside the guard. There is nowhere lossless to drain
    # them to -- docs/ is reserved, and deleting a real reason to satisfy a line
    # ceiling was ruled out. Named one per line so the next one cannot arrive
    # unnoticed; the ceiling's job on this class is forward-only. The list IS the
    # count -- a total written out beside it is a second copy that drifts, and the
    # one this replaced already had.
    "apex_core/test_routed_payment_serialization.py": {"long-docstring": 1},
    "apex_core/utils/report_role_guard.py": {"long-docstring": 1},
    "apex_core/utils/request_ip_trust.py": {"long-docstring": 1},
    "apex_core/utils/workflow_guard.py": {"long-docstring": 1},
    "change_log/test_release_note_claims.py": {"long-docstring": 1},
    "habitat/doctype/facility_asset_movement/"
    "test_facility_asset_movement_reachability.py": {"long-docstring": 1},
    "salis/report/test_report_row_scope.py": {"long-docstring": 1},
    "salis/report/test_workspace_report_runnable.py": {"long-docstring": 1},
    "salis/workspace/test_salis_root_persona_content.py": {"long-docstring": 1},
    "templates/__init__.py": {"long-docstring": 1},
    "tests/test_apps_screen_gate_wiring.py": {"long-docstring": 1},
    "tests/test_colocation_ratchet.py": {"long-docstring": 1},
    "tests/test_duplicate_and_dead_code_guard.py": {"long-docstring": 1},
    "tests/test_sql_interpolation_guard.py": {"long-docstring": 1},
    "tests/test_unit_test_coverage_guard.py": {"long-docstring": 1},
    "tests/test_workspace_doc_parity.py": {"long-docstring": 1},
    "www/masar_supervisor.py": {"long-docstring": 1},
    "www/test_www_no_external_cdn_assets.py": {"long-docstring": 1},
}

# The legacy volume that was deliberately NOT swept: 444 board ids in comments and
# docstrings over 189 files (re-measured 2026-07-31). Sweeping changes no
# behaviour, conflicts with every open branch, and costs provenance a maintainer
# uses; what it would buy is that a public reader stops meeting ids they can never
# resolve.
#
# That is its own card, drained per module. Until then these can only FALL: an
# added id fails, and each module drained lowers the number. EXACT, never rounded
# up: a ceiling one above the count is one free id, and the gate's own slack note
# is the standing instruction to close that gap.
_KIND_CEILING: dict[str, int] = {
    KIND_DOCSTRING_ID: 367,
    KIND_COMMENT_ID: 77,
}


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


def _docstring_nodes(tree: ast.AST):
    """Every node that can carry a docstring, paired with its docstring Constant."""
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef)):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            yield first.value


def _message_strings(tree: ast.AST):
    """String constants a reader meets without opening the file.

    An assert's message, and the arguments of the calls that put text in front of
    a person -- assertions, frappe.throw/msgprint, translate. A board id here is
    the worst case the gate covers: the reader cannot even see the code it names.
    """
    for node in ast.walk(tree):
        holder = None
        if isinstance(node, ast.Assert) and node.msg is not None:
            holder = node.msg
        elif isinstance(node, ast.Call):
            name = node.func.attr if isinstance(node.func, ast.Attribute) else \
                getattr(node.func, "id", "")
            if name.startswith("assert") or name in _MESSAGE_CALLS:
                holder = node
        if holder is None:
            continue
        for child in ast.walk(holder):
            if isinstance(child, ast.Constant) and isinstance(child.value, str):
                yield child


def _ast_findings(text: str) -> tuple[list[dict], set[int]]:
    """(findings, line numbers owned by a docstring).

    The second value lets the line scanner skip docstring bodies: a `#` inside a
    docstring is prose, not a comment, and counting it as one both mis-attributes
    the finding and pads a consecutive-comment run.
    """
    findings: list[dict] = []
    covered: set[int] = set()
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return findings, covered
    lines = text.splitlines()
    seen: set[tuple[int, str]] = set()

    def add(lineno: int, kind: str, detail: str) -> None:
        if (lineno, kind) in seen:
            return
        seen.add((lineno, kind))
        findings.append({"line": lineno, "kind": kind, "detail": detail})

    for const in _docstring_nodes(tree):
        start = const.lineno
        end = const.end_lineno or start
        covered.update(range(start, end + 1))
        span = end - start + 1
        if span >= DOCSTRING_LIMIT:
            add(start, KIND_LONG_DOCSTRING,
                f"{span}-line docstring (ceiling {DOCSTRING_LIMIT}) — keep the WHY, "
                "cut the narrative")
        for lineno in range(start, min(end, len(lines)) + 1):
            found = _TASK_ID.search(lines[lineno - 1])
            if found:
                add(lineno, KIND_DOCSTRING_ID,
                    f"board id in docstring: {found.group()}")

    for const in _message_strings(tree):
        found = _TASK_ID.search(const.value)
        if found:
            add(const.lineno, KIND_MESSAGE_ID,
                f"board id in an assertion/throw call: {found.group()} — this one "
                "reaches a reader who never opens the source")
    return findings, covered


def scan_file(path: Path) -> list[dict]:
    findings: list[dict] = []
    ext = path.suffix.lower()
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return findings
    lines = text.splitlines()
    covered: set[int] = set()
    if ext == ".py":
        ast_findings, covered = _ast_findings(text)
        findings.extend(ast_findings)
    in_block = False
    run_start = run_len = 0

    def flush() -> None:
        if run_len >= CONSEC_LIMIT:
            findings.append({
                "line": run_start,
                "kind": "long-block",
                "detail": f"{run_len} consecutive comment lines (condense the WHY)",
            })

    for lineno, raw in enumerate(lines, 1):
        if lineno in covered:
            flush()
            run_len = 0
            continue
        text_, is_full, in_block = _comment(raw, ext, in_block)
        if is_full:
            if run_len == 0:
                run_start = lineno
            run_len += 1
        else:
            flush()
            run_len = 0
        if text_ is None:
            continue
        if ext == ".py" and _PY_SKIP.search(text_):
            continue
        task_id = _TASK_ID.search(text_)
        if task_id:
            findings.append({"line": lineno, "kind": KIND_COMMENT_ID,
                             "detail": f"board id in comment: {task_id.group()}"})
        if _BANNER.search(text_):
            findings.append({"line": lineno, "kind": "banner",
                             "detail": "decorative divider — noise that drifts from the code"})
    flush()
    return sorted(findings, key=lambda f: (f["line"], f["kind"]))


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


def is_baselined_root(root: Path) -> bool:
    """True only for the package the baseline was measured against.

    The counts below are facts about `apex/` and nothing else. Applied to any
    other root — a fixture repo, a second package — they would silently tolerate
    79 comment ids and 376 docstring ids that were never counted there, which is
    a gate that passes a tree it has never read.
    """
    return (root.name == "apex" and (root / "hooks.py").is_file()
            and (root / "modules.txt").is_file())


def apply_baseline(findings: list[dict]) -> tuple[list[dict], list[str], list[str]]:
    """Split findings into (still failing, hard errors, advisory notes).

    Per-file allowances are spent first; whatever is left of a kind is judged
    against that kind's frozen ceiling. A per-file entry that has shrunk is a
    hard error — prune it with the drain, or the gap is headroom nobody reviewed.
    A kind that has shrunk is only a note: many branches remove one of those in
    passing, and reddening the shared lint lane for a good deed buys nothing.
    """
    errors: list[str] = []
    notes: list[str] = []
    groups: dict[tuple[str, str], list[dict]] = {}
    for finding in findings:
        groups.setdefault((finding["file"], finding["kind"]), []).append(finding)

    failing: list[dict] = []
    residual: dict[str, list[dict]] = {}
    for (file, kind), group in sorted(groups.items()):
        allowed = _BASELINE.get(file, {}).get(kind, 0)
        for finding in group[allowed:]:
            residual.setdefault(kind, []).append(finding)

    for kind, leftover in sorted(residual.items()):
        ceiling = _KIND_CEILING.get(kind, 0)
        if len(leftover) > ceiling:
            if ceiling == 0:
                failing.extend(leftover)
            else:
                errors.append(
                    f"{kind}: {len(leftover)} findings against a frozen ceiling of "
                    f"{ceiling}. Run with --no-baseline and diff your branch: this "
                    "gate only ever lets that number fall."
                )
    for kind, ceiling in sorted(_KIND_CEILING.items()):
        slack = ceiling - len(residual.get(kind, []))
        if slack > 0:
            notes.append(
                f"{kind}: {slack} under its ceiling of {ceiling} — lower "
                "_KIND_CEILING to lock the drain in."
            )
    for file, kinds in sorted(_BASELINE.items()):
        for kind, allowed in sorted(kinds.items()):
            actual = len(groups.get((file, kind), []))
            if actual < allowed:
                errors.append(
                    f"stale baseline entry {file} [{kind}]: declares {allowed}, "
                    f"found {actual}. Prune it — a drain that leaves its entry "
                    "behind buys silent headroom."
                )
    return failing, errors, notes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default="apex", help="Directory to scan")
    parser.add_argument("--json", action="store_true", help="Machine output")
    parser.add_argument("--no-baseline", action="store_true",
                        help="Report every finding, including the declared ones "
                             "(the baseline applies to the apex package only)")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    findings = scan_tree(root)
    errors: list[str] = []
    notes: list[str] = []
    if not args.no_baseline and is_baselined_root(root):
        findings, errors, notes = apply_baseline(findings)
    if args.json:
        print(json.dumps({"root": str(root), "count": len(findings),
                          "findings": findings, "baseline_errors": errors,
                          "baseline_notes": notes},
                         ensure_ascii=False, indent=2))
        return 1 if findings or errors else 0
    for note in notes:
        print(f"  baseline note: {note}")
    for error in errors:
        print(f"  baseline: {error}")
    if not findings and not errors:
        print("comment-audit: clean — no policy violations.")
        return 0
    by_kind: dict[str, int] = {}
    for finding in findings:
        by_kind[finding["kind"]] = by_kind.get(finding["kind"], 0) + 1
        print(f'  {finding["file"]}:{finding["line"]}  [{finding["kind"]}]  {finding["detail"]}')
    print(f"\ncomment-audit: {len(findings)} violations, {len(errors)} baseline errors"
          + ("" if not by_kind else " — " + " · ".join(f"{k}={n}" for k, n in sorted(by_kind.items()))))
    print("Fix: comments and docstrings say WHY in as few lines as it takes. Drop "
          "dividers, keep the reason next to the code it explains, and keep board "
          "ids out of source — hardest out of anything a reader sees as a message.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
