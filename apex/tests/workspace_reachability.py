# Copyright (c) 2026, AFMCO and contributors

import glob
import json
import os
from pathlib import Path

import apex

_APP = str(Path(apex.__file__).resolve().parent)
_WORKSPACE_GLOB = os.path.join(_APP, "*", "workspace", "*", "*.json")

def workspaces():
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
    return forebear["hidden"] or (bool(forebear["roles"]) and role not in forebear["roles"])

