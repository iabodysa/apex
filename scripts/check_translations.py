#!/usr/bin/env python3
"""Arabic coverage gate: every user-facing English string the app ships must have
a row in apex/translations/ar.csv.

MISSING (a live source string with no CSV row) is a hard failure — the user sees
raw English. STALE (a CSV row whose English source is gone) is held against a
recorded SET instead of zero: the extractor cannot see every live string (HTML
fragments, framework labels this app overrides), so a stale row is a *candidate*
for deletion, not proof of death. Deleting one needs the manual cross-check.

The set, not a count, is what makes a stale failure actionable. A count says a
threshold moved but not by whom, so the row a rename just stranded arrives buried
in a hundred identical-looking lines. Holding the SET means a failure lists only
the rows stale since it was recorded — normally the one label someone just
renamed — and the fix belongs with that rename, not with whoever wrote the Arabic
months earlier. Rows drained legitimately are re-recorded with
--update-stale-baseline, which the failure message spells out: a ratchet nobody
can advance is a ratchet everybody overrides.

Strings come from two sources and are judged differently. A DECLARED string is
one the framework or the author already committed to translating — an explicit
_()/__() msgid, or a DocType/field `description`, which Frappe harvests
(translate.py) and renders through __() verbatim at any length. Everything else
is GUESSED from a JSON key, and only guesses get the shape heuristics below.

Also lints static schema labels for {placeholders}: a label is rendered verbatim,
so a brace in one is a bug — placeholders belong only to code _()/__() calls.

Stdlib-only and self-contained ON PURPOSE: the maintainer's local toolbox is not
installable on a CI runner, so the gate has to live in the repo to run there.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from pathlib import Path

SKIP_DIRS = {".git", ".venv", "__pycache__", "node_modules", "translations",
             "locale", "public", "private"}
SCAN_EXTS = {".json", ".py", ".js", ".ts", ".vue", ".html"}

JSON_TEXT_KEYS = {"label", "title", "subtitle", "description", "message",
                  "success_message", "subject", "options", "action_label",
                  "action_name", "button_label", "card_name", "chart_name", "column"}
# Subset that is a STATIC label shown verbatim, so it must never interpolate.
LABEL_KEYS = {"label", "title", "subtitle", "options", "action_label",
              "button_label", "card_name", "chart_name", "column"}
# Keys Frappe itself declares translatable, so the shape heuristics must not judge them.
DECLARED_KEYS = {"description"}

# Start of a translate call; the first literal (plus adjacently concatenated ones)
# is the msgid. Matching the start, not the whole call, keeps __("Saved {0}", [n]).
# The callee must be BARE. Without the lookbehind this also matches the TAIL of an
# attribute call whose name ends in `_` — `sle.item.as_("article")` — and of
# `def __init__(`, so query-builder column aliases were harvested as msgids and 23
# of them (`article`, `bed`, `cnt`, `n`, `total_cost`, ...) were translated. A `.`
# is still a legal preceding character, so `frappe._()` keeps matching; only a word
# character immediately before the name disqualifies it.
_CALL_START = re.compile(r"(?<![A-Za-z0-9_])(?:(?:frappe\.)?_(?:lt)?|__)\(")
_NEXT_LITERAL = re.compile(r"""\s*\+?\s*(['"])((?:\\.|(?!\1).)*?)\1""")
# A guard that keeps its message in a module constant and throws `_(_MESSAGE)` puts
# no literal at the call site, so the msgid has to be resolved from the constant.
# Column 0 only: a module constant is a fixed msgid, while an indented local is not
# — `_(doctype)` on a function parameter has no one string to harvest.
_CONST_ASSIGN = re.compile(r"^(?:(?:const|let|var)\s+)?([A-Za-z_$][\w$]*)\s*=\s*\(?", re.M)
_IDENT_ARG = re.compile(r"\s*([A-Za-z_$][\w$]*)\s*[,)]")
_HTML_TAG = re.compile(r"<[^>]+>")


def clean_text(value: str) -> str:
    """Decode backslash escapes without mangling real multibyte UTF-8."""
    if "\\" not in value:
        return value.strip()
    try:
        return value.encode("latin-1", "backslashreplace").decode("unicode_escape").strip()
    except (UnicodeDecodeError, UnicodeEncodeError):
        return value.strip()


def is_candidate_text(value: str, declared: bool = False) -> bool:
    """`declared` marks a string already committed to translation by the framework
    or the author, so only Frappe's own is_translatable rules apply. The heuristics
    below exist to stop a JSON *guess* slurping prose that is not a msgid; applied
    to a declared string they hide real gaps instead — a 182-char description was
    invisible to MISSING, and translating it landed the row in STALE."""
    text = value.strip()
    if not text:
        return False
    if not re.search(r"[A-Za-z]", text):
        return False
    if not declared:
        if len(text) > 180:
            return False
        if re.search(r"[<>]", text):  # HTML fragment, not a msgid
            return False
        if "#" in text:  # naming-series / autoname placeholder, an identifier
            return False
        if re.search(r"[{}]", text):  # a format-string only a real msgid may carry
            return False
    return not text.startswith(("http://", "https://", "/", "#"))


def is_auto_translatable(text: str) -> bool:
    """'&' becomes an HTML entity and corrupts CSV round-tripping, so those rows
    are translated by hand: kept in `used` (never stale) but never reported missing."""
    return "&" not in text


def add_candidate(found: set, text: str, declared: bool = False) -> None:
    for part in text.splitlines():
        cleaned = part.strip()
        if is_candidate_text(cleaned, declared=declared):
            found.add(cleaned)


def string_constants(content: str) -> dict:
    """Module-level ``NAME = "text"`` bindings, so ``_(NAME)`` resolves to a msgid.

    Adjacent literals are joined exactly as at a call site, which is what makes a
    parenthesised multi-line constant one string. A name bound to something that
    does not start with a literal is simply absent, and an absent name is ignored."""
    constants: dict = {}
    for assign in _CONST_ASSIGN.finditer(content):
        pos = assign.end()
        parts: list[str] = []
        while True:
            literal = _NEXT_LITERAL.match(content, pos)
            if literal is None:
                break
            parts.append(literal.group(2))
            pos = literal.end()
        if parts:
            constants[assign.group(1)] = clean_text("".join(parts))
    return constants


def scan_calls(content: str, found: set, constants: dict | None = None) -> None:
    for call in _CALL_START.finditer(content):
        pos = call.end()
        parts: list[str] = []
        while True:
            literal = _NEXT_LITERAL.match(content, pos)
            if literal is None:
                break
            parts.append(literal.group(2))
            pos = literal.end()
        if parts:
            add_candidate(found, clean_text("".join(parts)), declared=True)
            continue
        # No literal here: the msgid may be held in a module constant, _(_MESSAGE).
        # Same standing as a literal — the author already committed to translating
        # it — so it is declared too, which is what lets a long braced guard message
        # through the shape heuristics.
        if not constants:
            continue
        ident = _IDENT_ARG.match(content, pos)
        if ident is not None and ident.group(1) in constants:
            add_candidate(found, constants[ident.group(1)], declared=True)


def extract_workspace_content(content_str: str, found: set) -> None:
    """Workspace.content is serialized editor JSON; pull the header/paragraph prose."""
    if not content_str:
        return
    try:
        blocks = json.loads(content_str)
    except ValueError:
        return
    if not isinstance(blocks, list):
        return
    for block in blocks:
        if not isinstance(block, dict) or block.get("type") not in {"header", "paragraph", "markdown"}:
            continue
        text = (block.get("data") or {}).get("text", "")
        if isinstance(text, str):
            plain = _HTML_TAG.sub("", text).strip()
            if plain:
                add_candidate(found, plain)


def git_files(package: Path) -> list[Path] | None:
    """Files git accounts for under `package`, or None when git cannot answer.

    Tracked plus not-yet-added files, never ignored ones. An ignored file cuts
    both ways here: its strings inflate MISSING (a local-only red) and they also
    keep dead ar.csv rows out of STALE, which would hide a real CI failure.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(package), "ls-files", "-z",
             "--cached", "--others", "--exclude-standard"],
            capture_output=True, check=False,
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    names = proc.stdout.decode("utf-8", "surrogateescape").split("\0")
    return [package / name for name in names if name]


def walk_files(package: Path):
    # Fall back to a raw walk outside a work tree (an sdist or tarball) so a
    # missing git degrades to the old behaviour, not to an empty scan.
    candidates = git_files(package)
    if candidates is None:
        candidates = package.rglob("*")
    for path in candidates:
        if not path.is_file() or path.suffix.lower() not in SCAN_EXTS:
            continue
        if set(path.relative_to(package).parts[:-1]) & SKIP_DIRS:
            continue
        yield path


def extract(package: Path) -> tuple[set, list[tuple[str, str, str]]]:
    """Return (used source strings, static-label placeholder warnings)."""
    found: set = set()
    warnings: list[tuple[str, str, str]] = []

    for path in walk_files(package):
        rel = str(path.relative_to(package))
        if path.suffix.lower() != ".json":
            try:
                content = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            scan_calls(content, found, string_constants(content))
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeDecodeError):
            continue

        def visit(obj, key=None):
            if isinstance(obj, dict):
                # A Dynamic Link's `options` names a fieldname, not UI text.
                skip_options = obj.get("fieldtype") == "Dynamic Link"
                for child_key, child in obj.items():
                    if child_key == "options" and skip_options:
                        continue
                    visit(child, child_key)
            elif isinstance(obj, list):
                for item in obj:
                    visit(item, key)
            elif isinstance(obj, str):
                if key in JSON_TEXT_KEYS:
                    scan_calls(obj, found)  # Notification subject/message hold Jinja _()
                    add_candidate(found, obj, declared=key in DECLARED_KEYS)
                if key in LABEL_KEYS and re.search(r"[{}]", obj) and re.search(r"[A-Za-z]", obj):
                    entry = (rel, key, obj.strip())
                    if entry not in warnings:
                        warnings.append(entry)

        if isinstance(payload, dict):
            if payload.get("doctype") == "DocType" and payload.get("name"):
                add_candidate(found, str(payload["name"]))
            if payload.get("doctype") == "Workspace":
                extract_workspace_content(payload.get("content", ""), found)
        visit(payload)
    return found, warnings


def read_csv_keys(path: Path) -> set:
    if not path.exists():
        return set()
    with path.open(encoding="utf-8", newline="") as handle:
        return {row[0] for row in csv.reader(handle) if len(row) >= 2 and row[0].strip()}


def stale_baseline_path(package: Path, lang: str) -> Path:
    # Beside the CSV it records, so the set is scoped to the package under test
    # rather than to wherever this script happens to live.
    return package / "translations" / f"{lang}.stale-baseline.txt"


def read_stale_baseline(path: Path) -> set:
    """Recorded stale rows, or an empty set when nothing is recorded yet.

    A missing file records nothing, so every stale row reads as new. That is the
    safe direction: a lost or unwritten set over-reports, it never hides a row.
    A leading '#' is a comment: a source string starting with one is not a msgid
    the extractor would ever match (is_candidate_text rejects it), so a row keyed
    on one could never leave STALE and has no business being recorded.
    """
    if not path.exists():
        return set()
    lines = path.read_text(encoding="utf-8").splitlines()
    return {line for line in lines if line.strip() and not line.startswith("#")}


def write_stale_baseline(path: Path, stale: list, lang: str, regen: str) -> None:
    header = (
        f"# {lang}.csv rows whose English source string was already gone when this set\n"
        "# was recorded. The gate fails only on stale rows NOT listed here, so its\n"
        "# output names the row a change just stranded instead of all of them.\n"
        f"# Regenerate after deleting drained rows:\n#   {regen}\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header + "".join(f"{text}\n" for text in stale), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", default="apex", help="App package directory")
    parser.add_argument("--lang", default="ar", help="Target language")
    parser.add_argument("--max-missing", type=int, default=0)
    parser.add_argument("--max-stale", type=int, default=0,
                        help="Stale rows allowed BEYOND the recorded set, not in total")
    parser.add_argument("--update-stale-baseline", action="store_true",
                        help="Re-record the stale set, then report against it")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    package = Path(args.package).resolve()
    csv_path = package / "translations" / f"{args.lang}.csv"
    baseline_path = stale_baseline_path(package, args.lang)
    regen = ("python3 scripts/check_translations.py "
             f"--package {args.package} --lang {args.lang} --update-stale-baseline")
    used, warnings = extract(package)
    existing = read_csv_keys(csv_path)

    missing = sorted({t for t in used if is_auto_translatable(t)} - existing)
    stale = sorted(existing - used)
    recorded = read_stale_baseline(baseline_path)
    new_stale = sorted(set(stale) - recorded)
    # Recorded rows that are live or deleted again. Never a failure: the set names
    # rows, so a spent entry can only ever excuse itself, never a different row.
    drained = sorted(recorded - set(stale))

    if args.update_stale_baseline:
        write_stale_baseline(baseline_path, stale, args.lang, regen)
        recorded, new_stale, drained = set(stale), [], []

    passed = (len(missing) <= args.max_missing
              and len(new_stale) <= args.max_stale
              and not warnings)

    if args.json:
        print(json.dumps({"missing_count": len(missing), "stale_count": len(stale),
                          "new_stale_count": len(new_stale),
                          "label_warning_count": len(warnings),
                          "max_missing": args.max_missing, "max_stale": args.max_stale,
                          "passed": passed}, ensure_ascii=False, separators=(",", ":")))
        return 0 if passed else 1

    if args.update_stale_baseline:
        print(f"recorded {len(stale)} stale rows in {baseline_path.name}")
    print(f"translations ({args.lang}): {len(missing)} missing, {len(stale)} stale "
          f"({len(new_stale)} newly stale), "
          f"{len(warnings)} label placeholder warnings "
          f"(allowed: {args.max_missing} missing, {args.max_stale} newly stale, 0 warnings)")
    if missing:
        print(f"\nMISSING — add an Arabic row to {csv_path.name} for each:")
        for text in missing:
            print(f"  {text}")
    if len(new_stale) > args.max_stale:
        print(f"\nNEWLY STALE ({len(new_stale)}) — these {csv_path.name} rows lost their "
              f"English source since {baseline_path.name} was recorded. Deleting or "
              "renaming a source string is what strands a row, so the fix belongs with "
              "that change: re-key the row to the new source string, or delete the row "
              "if the string is gone for good, then re-record the set with\n"
              f"    {regen}")
        for text in new_stale:
            print(f"  {text}")
    if drained:
        noun = "row is" if len(drained) == 1 else "rows are"
        print(f"\n{len(drained)} recorded stale {noun} no longer stale. Not a failure — "
              "a spent entry excuses only itself — but re-record to keep the set honest:\n"
              f"    {regen}")
    for rel, key, text in warnings:
        print(f"\nLABEL PLACEHOLDER — {rel} ({key}): {text}")
        print("  A static label renders verbatim; move the placeholder into a code _() call.")
    print("\n" + ("PASS" if passed else "FAIL"))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
