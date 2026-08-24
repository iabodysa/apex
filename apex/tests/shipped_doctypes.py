# Copyright (c) 2026, AFMCO and contributors

import glob
import json
import os
from pathlib import Path

import apex

APP_ROOT = str(Path(apex.__file__).resolve().parent)
DOCTYPE_GLOB = os.path.join(APP_ROOT, "*", "doctype", "*", "*.json")

def shipped_doctypes():
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
