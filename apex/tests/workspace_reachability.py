# Copyright (c) 2026, AFMCO and contributors
"""Shared workspace parent-chain reachability scan.

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
module (the pattern that produced ``tests/factories.py``) instead of being
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

# The INSTALLED package, never this file's own neighbourhood: `dirname(__file__)/..`
# resolves against wherever this module's copy sits, and the maintainer mirror at
# `.claude/tests/apex` (source_tree.py's SUITE_PACKAGE) holds no workspace JSON at all —
# a glob rooted there goes quiet and every sidebar guard reading through here grades an
# empty set while reporting green.
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






def blocks(forebear, role):
    """True if this ancestor stops a holder of ``role`` from ever seeing the child.

    A hidden ancestor drops its whole subtree for every non-``Workspace Manager``;
    an ancestor with a non-empty roles list that omits ``role`` is not permitted, so
    it is never rendered and its children never get nested under it. An EMPTY roles
    list is world-visible and blocks nobody."""
    return forebear["hidden"] or (bool(forebear["roles"]) and role not in forebear["roles"])




