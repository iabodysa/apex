# Copyright (c) 2026, AFMCO and contributors
"""Read the published role charters out of ``docs/training/README.md``.

Three guards cited that page as their source of truth in prose while none of them
opened it, each keeping its own copy of the charter it claimed to enforce. A
one-way citation reds on nothing: the doc could be reworded, or the DocPerm JSON
re-granted, and every assertion stayed green. That is how the charters rotted in
the first place.

Prose cannot be parsed into a permission schema, so these readers target the
machine-readable islands the page already contains — the ``Roles at a glance``
table, the parenthesised oversight list, and the counts written as number words.
A guard binds itself to one of those islands and asserts the property it implies;
if the island moves or its wording changes, the guard fails and forces a human to
re-read both sides.

Deliberately NOT named ``test_*``: ``tests/test_no_cross_test_imports.py`` bans a
test module importing a sibling test module, and this is the sanctioned shape for
shared test logic (same reason ``shipped_doctypes.py`` carries a plain name).
"""

import os
import re

APP_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
REPO_ROOT = os.path.dirname(APP_ROOT)
TRAINING_README = os.path.join(REPO_ROOT, "docs", "training", "README.md")

# A "Roles at a glance" row: | **Role** | Module | Typical user |
_CHARTER_ROW = re.compile(r"^\|\s*\*\*(?P<role>[^*]+)\*\*\s*\|(?P<module>[^|]*)\|(?P<charter>.*)\|\s*$")

# The Salis project-scoping note names its oversight set in parentheses.
_OVERSIGHT = re.compile(r"Oversight roles \((?P<roles>[^)]+)\) see all")

# Small counts are written as words in the charter prose, never as digits.
_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}


def role_charters(path=TRAINING_README):
    """role -> its ``Typical user`` cell, verbatim, from the Roles at a glance table."""
    charters = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            match = _CHARTER_ROW.match(line.rstrip("\n"))
            if match and match.group("module").strip():
                charters[match.group("role").strip()] = match.group("charter").strip()
    return charters


def documented_oversight_roles(path=TRAINING_README):
    """The Salis oversight set the project-scoping note lists in parentheses."""
    with open(path, encoding="utf-8") as fh:
        match = _OVERSIGHT.search(fh.read())
    if not match:
        raise AssertionError(
            f"{os.path.basename(path)} no longer contains an 'Oversight roles (...) see all' "
            "sentence; the scope guard reads its expected set from it"
        )
    return {role.strip() for role in match.group("roles").split(",") if role.strip()}


def charter_count(role, pattern, path=TRAINING_README):
    """The number word captured by `pattern` inside `role`'s charter cell, as an int.

    `pattern` must expose exactly one group and match against the charter text.
    """
    charter = role_charters(path).get(role)
    if charter is None:
        raise AssertionError(f"{role} has no row in the Roles at a glance table")
    match = re.search(pattern, charter)
    if not match:
        raise AssertionError(f"{role}'s charter no longer matches {pattern!r}: {charter!r}")
    word = match.group(1).strip().lower()
    if word not in _NUMBER_WORDS:
        raise AssertionError(f"{role}'s charter says {word!r}, which is not a number word")
    return _NUMBER_WORDS[word]
