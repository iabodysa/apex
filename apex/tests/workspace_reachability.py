# Copyright (c) 2026, AFMCO and contributors
"""Shared workspace parent-chain reachability scan (A-122 / A-127).

Frappe draws the desk sidebar in two stages. ``get_workspace_sidebar_items``
(frappe/desk/desktop.py) drops any workspace the session user is not permitted on,
then the client seeds the sidebar from ROOT pages alone and nests each child under
an ALREADY RENDERED parent
(frappe/public/js/frappe/views/workspace/workspace.js, ``make_sidebar``).

So a child whose parent the user cannot see is never drawn, and because the
permitted list is not empty the ``Welcome Workspace`` fallback never fires either.
Reachability is therefore a property of the WHOLE ancestor chain, never of the
child's own roles child table — which is exactly the gap two separate sidebar
regressions fell through.

This module is the single home of that scan. It is a non-``test_`` module on
purpose: ``tests/test_no_cross_test_imports.py`` forbids a ``test_*`` module from
importing a sibling ``test_*`` module, so shared logic is promoted into a plain
module (the P-135 pattern that produced ``tests/factories.py``) instead of being
copied into each caller.

Stdlib-only and file-level on purpose: the invariant is a property of the shipped
is_standard JSON, so it has to fail on the change that writes the bad JSON rather
than on a site that has already migrated it.

Note ``parent_page`` is matched against the parent's TITLE by the client, so this
scan keys workspaces by title, not by record name.
"""

import glob
import json
import os
from pathlib import Path

import apex

# The INSTALLED package, never this file's own neighbourhood. The suite moved out of the
# app on 2026-08-02, so `dirname(__file__)/..` named `.claude/tests/apex`, which holds no
# workspace JSON at all — the glob went quiet and every sidebar guard reading through here
# graded an empty set while reporting green.
_APP = str(Path(apex.__file__).resolve().parent)
_WORKSPACE_GLOB = os.path.join(_APP, "*", "workspace", "*", "*.json")


def workspaces():
    """title -> {roles, parent, hidden, path} for every is_standard workspace on disk."""
    pages = {}
    for path in sorted(glob.glob(_WORKSPACE_GLOB)):
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        title = data.get("title") or data.get("name")
        pages[title] = {
            "roles": {row["role"] for row in data.get("roles", []) if row.get("role")},
            "parent": data.get("parent_page") or "",
            "hidden": bool(data.get("is_hidden")),
            "path": os.path.relpath(path, _APP),
        }
    return pages


def workspace_titles():
    """Every workspace title on disk, WITH duplicates, so a collision stays visible."""
    titles = []
    for path in sorted(glob.glob(_WORKSPACE_GLOB)):
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        titles.append(data.get("title") or data.get("name"))
    return titles


def ancestors(pages, title):
    """Parent chain from the immediate parent up to the root; None if the chain is broken."""
    chain = []
    seen = {title}
    parent = pages[title]["parent"]
    while parent:
        if parent not in pages or parent in seen:
            return None
        chain.append(parent)
        seen.add(parent)
        parent = pages[parent]["parent"]
    return chain


def blocks(forebear, role):
    """True if this ancestor stops a holder of ``role`` from ever seeing the child.

    A hidden ancestor drops its whole subtree for every non-``Workspace Manager``;
    an ancestor with a non-empty roles list that omits ``role`` is not permitted, so
    it is never rendered and its children never get nested under it. An EMPTY roles
    list is world-visible and blocks nobody."""
    return forebear["hidden"] or (bool(forebear["roles"]) and role not in forebear["roles"])


def orphan_pairs(pages):
    """(workspace, role) pairs whose sidebar node no holder of that role can ever reach."""
    orphans = set()
    for title, page in pages.items():
        chain = ancestors(pages, title)
        if chain is None:
            continue
        for ancestor in chain:
            for role in page["roles"]:
                if blocks(pages[ancestor], role):
                    orphans.add((title, role))
    return orphans


def blocking_ancestors(pages, title, role):
    """Ancestors of ``title`` that hide it from a holder of ``role``, nearest first.

    Empty means reachable. Raises KeyError if ``title`` is not on disk and returns
    None when the parent chain is broken or cyclic, so a caller can report that
    distinct failure with its own message instead of mislabelling it a role gap."""
    chain = ancestors(pages, title)
    if chain is None:
        return None
    return [a for a in chain if blocks(pages[a], role)]
