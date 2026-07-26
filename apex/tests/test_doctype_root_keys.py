# Copyright (c) 2026, AFMCO and contributors
"""Every root-level key in a shipped DocType JSON must be one Frappe actually reads.

Twenty-two engine ledgers once shipped ``"hidden": 1`` at the root of their DocType
JSON, to keep operational users from finding them. ``hidden`` is not a DocType
property: it is absent from frappe's own core/doctype/doctype/doctype.json, so it is
not a column on ``tabDocType``, and ``BaseDocument.get_valid_dict`` writes only
``meta.get_valid_columns()``. The key parsed, imported, and was dropped on the floor
-- 22 records carried a concealment flag that concealed nothing, and no gate said so.

An unknown root key is silently inert exactly like that one, so the failure mode is
always a placebo that reads as shipped policy. This guard is the alarm: it derives the
legal key set from the INSTALLED frappe rather than a vendored list, so a Frappe
upgrade that adds or removes a DocType property moves the guard with it instead of
turning it into a second stale claim.

Frappe-free by construction (locates frappe's doctype.json, never imports frappe),
so it runs without a site -- which is what let the planted-key proof run at all.
"""

import glob
import importlib.util
import json
import os
import subprocess
import unittest

from apex.tests.source_tree import APP_ROOT, REPO_ROOT, rel

# Written by DocType.export_doc (core/doctype/doctype/doctype.py:791) and consumed by
# import_doc (:825-843) to restore field order. A real export artifact, not a field.
EXPORT_ONLY_KEYS = {"field_order"}

# frappe.model.default_fields -- present on every exported document, not DocType props.
DOCUMENT_KEYS = {"doctype", "name", "owner", "creation", "modified", "modified_by",
                 "docstatus", "idx"}

FRAPPE_DOCTYPE_JSON = os.path.join(
    "frappe", "core", "doctype", "doctype", "doctype.json"
)


def _frappe_root():
    """Directory holding the installed ``frappe`` package, without importing it.

    Import would need a configured site; this guard only needs one JSON file off
    disk. APEX_FRAPPE_PATH exists so the guard is runnable outside a bench venv.
    """
    override = os.environ.get("APEX_FRAPPE_PATH")
    if override:
        return override

    spec = importlib.util.find_spec("frappe")
    if spec and spec.origin:
        return os.path.dirname(os.path.dirname(spec.origin))

    # Bench layout: <bench>/apps/apex and <bench>/apps/frappe are siblings.
    sibling = os.path.join(os.path.dirname(REPO_ROOT), "frappe")
    if os.path.isdir(sibling):
        return sibling
    return None


def supported_root_keys():
    """Every root key Frappe honours on a DocType, read from the installed frappe.

    Deliberately NOT a vendored constant: a hand-copied list is the same category of
    artifact as the ``hidden`` key it exists to catch -- true when written, silently
    wrong later, with nothing to notice.
    """
    root = _frappe_root()
    if not root:
        raise unittest.SkipTest(
            "installed frappe not found; set APEX_FRAPPE_PATH to its parent directory"
        )
    path = os.path.join(root, FRAPPE_DOCTYPE_JSON)
    with open(path, encoding="utf-8") as handle:
        meta = json.load(handle)
    fieldnames = {f["fieldname"] for f in meta["fields"] if f.get("fieldname")}
    return fieldnames | EXPORT_ONLY_KEYS | DOCUMENT_KEYS


def _tracked_json_files():
    """apex/**/*.json as CI receives it, or None when git cannot answer.

    CI grades a fresh clone, so a gitignored JSON exists only on a developer's disk.
    A guard that walks the filesystem judges it anyway and reds locally while CI
    stays green.
    """
    try:
        out = subprocess.run(
            ["git", "-C", REPO_ROOT, "ls-files", "-z", "--cached", "--others",
             "--exclude-standard", "--", "*.json"],
            capture_output=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    prefix = os.path.basename(APP_ROOT) + "/"
    return sorted(
        os.path.join(REPO_ROOT, entry)
        for entry in out.decode().split("\0")
        if entry.startswith(prefix)
    )


def doctype_json_files():
    """Every shipped DocType definition under ``apex/**/doctype/<name>/<name>.json``.

    Identified by shape rather than by filename: the same directory also holds
    dashboard/list-view settings JSONs, which are not DocType documents.
    """
    candidates = _tracked_json_files()
    if candidates is None:
        candidates = sorted(
            glob.glob(os.path.join(APP_ROOT, "**", "doctype", "*", "*.json"), recursive=True)
        )
    found = []
    for path in candidates:
        if os.sep + "doctype" + os.sep not in path:
            continue
        with open(path, encoding="utf-8") as handle:
            try:
                doc = json.load(handle)
            except ValueError:
                continue
        if isinstance(doc, dict) and "fields" in doc and "module" in doc:
            found.append((path, doc))
    return found


class TestDocTypeRootKeys(unittest.TestCase):
    def test_no_unsupported_root_key(self):
        """A root key Frappe does not read is a claim the product does not keep."""
        supported = supported_root_keys()
        files = doctype_json_files()
        self.assertTrue(files, "no DocType JSONs found -- the scan universe is empty")

        offenders = []
        for path, doc in files:
            for key in sorted(set(doc) - supported):
                offenders.append(f"{rel(path)}: {key!r}")

        self.assertEqual(
            offenders,
            [],
            "DocType JSON root keys that Frappe silently ignores (they are dropped by "
            "BaseDocument.get_valid_dict, so they change nothing at runtime):\n  "
            + "\n  ".join(offenders),
        )

    def test_hidden_key_stays_gone(self):
        """The specific inert key this tree once shipped, named so its return is legible.

        Kept beside the general check because the general one only says "unsupported";
        a reader re-adding ``hidden`` to conceal a ledger needs to be told that THIS
        key was already tried and does nothing, and that root ``read_only`` (labelled
        "User Cannot Search" in frappe's doctype.json) is the honoured mechanism.
        """
        carriers = [rel(p) for p, doc in doctype_json_files() if "hidden" in doc]
        self.assertEqual(
            carriers,
            [],
            "root 'hidden' is not a DocType field and conceals nothing; use root "
            "'read_only' (frappe labels it \"User Cannot Search\") -- but note it is "
            "role-blind and also drops the doctype from can_read, hiding its workspace "
            f"links for every non-Administrator: {carriers}",
        )

    def test_guard_reads_the_installed_frappe(self):
        """The allowlist must come from frappe, not from this file.

        Without this, a resolver regression would silently shrink ``supported`` to the
        two vendored sets and the guard would red on every legitimate DocType property
        -- or, if someone 'fixed' that by vendoring the full list, quietly rot.
        """
        supported = supported_root_keys()
        self.assertIn("read_only", supported)
        self.assertIn("istable", supported)
        self.assertNotIn("hidden", supported)
        self.assertGreater(len(supported), 50)
