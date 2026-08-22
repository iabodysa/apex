# Copyright (c) 2026, AFMCO and contributors
"""Read the app's shipped DocType JSON straight off disk, for site-free guards.

Two permission guards written in the same wave each grew their own copy of this
loader, and the widened copy-paste detector caught it on its first day. One home
instead, so the parse rules cannot drift apart between guards that compare their
results to each other.

Deliberately NOT named ``test_*``: ``tests/test_no_cross_test_imports.py`` bans a
test module importing a sibling test module, and this is the sanctioned shape for
shared test logic (the same reason ``factories.py`` and ``workspace_reachability.py``
carry plain names).
"""

import glob
import json
import os
from pathlib import Path

import apex

APP_ROOT = str(Path(apex.__file__).resolve().parent)
DOCTYPE_GLOB = os.path.join(APP_ROOT, "*", "doctype", "*", "*.json")

def shipped_doctypes():
    """DocType name -> its shipped JSON, for every DocType in the app.

    A directory holds more than the DocType definition (its child-table and
    dashboard JSONs sit alongside), so the ``doctype == "DocType"`` check is what
    keeps siblings out. An unparseable file is skipped rather than raised on: a
    guard's job is to report what ships, not to die on one malformed neighbour.
    """
    out = {}
    for path in sorted(glob.glob(DOCTYPE_GLOB)):
        with open(path, encoding="utf-8") as fh:
            try:
                data = json.load(fh)
            except json.JSONDecodeError:
                continue
        if isinstance(data, dict) and data.get("doctype") == "DocType" and data.get("name"):
            out[data["name"]] = data
    return out
