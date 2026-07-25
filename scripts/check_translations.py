#!/usr/bin/env python3
"""Arabic coverage gate: every user-facing English string the app ships must have
a row in apex/translations/ar.csv.

MISSING (a live source string with no CSV row) is a hard failure — the user sees
raw English. STALE (a CSV row whose English source is gone) is capped at a
baseline instead: the extractor cannot see every live string (HTML fragments,
long text, framework labels this app overrides), so a stale row is a *candidate*
for deletion, not proof of death. Deleting one needs the manual cross-check.

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

# Start of a translate call; the first literal (plus adjacently concatenated ones)
# is the msgid. Matching the start, not the whole call, keeps __("Saved {0}", [n]).
_CALL_START = re.compile(r"(?:frappe\.)?_\(|__\(")
_NEXT_LITERAL = re.compile(r"""\s*\+?\s*(['"])((?:\\.|(?!\1).)*?)\1""")
_HTML_TAG = re.compile(r"<[^>]+>")


def clean_text(value: str) -> str:
    """Decode backslash escapes without mangling real multibyte UTF-8."""
    if "\\" not in value:
        return value.strip()
    try:
        return value.encode("latin-1", "backslashreplace").decode("unicode_escape").strip()
    except (UnicodeDecodeError, UnicodeEncodeError):
        return value.strip()


def is_candidate_text(value: str, allow_placeholders: bool = False) -> bool:
    text = value.strip()
    if not text or len(text) > 180:
        return False
    if not re.search(r"[A-Za-z]", text):
        return False
    if re.search(r"[<>]", text):  # HTML fragment, not a msgid
        return False
    if "#" in text:  # naming-series / autoname placeholder, an identifier
        return False
    # Braces are valid in an explicit _()/__() msgid only; rejecting them for
    # heuristic JSON extraction keeps translated format-strings out of stale.
    if not allow_placeholders and re.search(r"[{}]", text):
        return False
    return not text.startswith(("http://", "https://", "/", "#"))


def is_auto_translatable(text: str) -> bool:
    """'&' becomes an HTML entity and corrupts CSV round-tripping, so those rows
    are translated by hand: kept in `used` (never stale) but never reported missing."""
    return "&" not in text


def add_candidate(found: set, text: str, allow_placeholders: bool = False) -> None:
    for part in text.splitlines():
        cleaned = part.strip()
        if is_candidate_text(cleaned, allow_placeholders=allow_placeholders):
            found.add(cleaned)


def scan_calls(content: str, found: set) -> None:
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
            add_candidate(found, clean_text("".join(parts)), allow_placeholders=True)


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
                scan_calls(path.read_text(encoding="utf-8"), found)
            except (OSError, UnicodeDecodeError):
                pass
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
                    add_candidate(found, obj)
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", default="apex", help="App package directory")
    parser.add_argument("--lang", default="ar", help="Target language")
    parser.add_argument("--max-missing", type=int, default=0)
    parser.add_argument("--max-stale", type=int, default=0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    package = Path(args.package).resolve()
    csv_path = package / "translations" / f"{args.lang}.csv"
    used, warnings = extract(package)
    existing = read_csv_keys(csv_path)

    missing = sorted({t for t in used if is_auto_translatable(t)} - existing)
    stale = sorted(existing - used)
    passed = (len(missing) <= args.max_missing
              and len(stale) <= args.max_stale
              and not warnings)

    if args.json:
        print(json.dumps({"missing_count": len(missing), "stale_count": len(stale),
                          "label_warning_count": len(warnings),
                          "max_missing": args.max_missing, "max_stale": args.max_stale,
                          "passed": passed}, ensure_ascii=False, separators=(",", ":")))
        return 0 if passed else 1

    print(f"translations ({args.lang}): {len(missing)} missing, {len(stale)} stale, "
          f"{len(warnings)} label placeholder warnings "
          f"(allowed: {args.max_missing} missing, {args.max_stale} stale, 0 warnings)")
    if missing:
        print(f"\nMISSING — add an Arabic row to {csv_path.name} for each:")
        for text in missing:
            print(f"  {text}")
    if len(stale) > args.max_stale:
        print(f"\nSTALE over baseline ({len(stale)} > {args.max_stale}). Either the rows are "
              "dead (verify no live source key, then delete and lower the baseline) or a "
              "source string changed and its translation needs re-keying:")
        for text in stale:
            print(f"  {text}")
    for rel, key, text in warnings:
        print(f"\nLABEL PLACEHOLDER — {rel} ({key}): {text}")
        print("  A static label renders verbatim; move the placeholder into a code _() call.")
    print("\n" + ("PASS" if passed else "FAIL"))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
