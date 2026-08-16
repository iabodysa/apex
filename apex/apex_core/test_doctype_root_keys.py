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

# Machine-written engine records kept out of Desk search: the SAME 22 that once shipped
# the inert root ``hidden`` key, re-expressed as root ``read_only``, which frappe honours.
# A SET rather than a count, because a count cannot tell a swap from a no-op.
# Concealment is search and link only, never access — see the reach and the zero-exposure
# report audit in ``test_engine_ledgers_stay_out_of_search``.
SEARCH_CONCEALED = frozenset({
    "Boarding Scan Log",
    "Driver Attendance",
    "Fuel Daily Log",
    "Operational Depreciation Snapshot",
    "Safety Inspection Report",
    "Scheduled Task Instance",
    "Trip Boarding State",
    "Trip Start Log",
})

# Concealing a linked record COSTS THE LINK: frappe drops it from ``can_read`` too for a
# read-without-write grant (frappe/utils/user.py:139-142, :181-183) and a workspace link
# gates on can_read (desk/desktop.py:150). Measured live: 12 links plus the Accommodation
# Engine and Safety Engine cards died on Backend Engines, 2 more on Compliance and
# Rentals. These 14 therefore keep their links; the 8 above are linked by no workspace.
LINKED_SO_NOT_CONCEALED = frozenset({
    "Accommodation Ledger",
    "Accommodation Stock Ledger",
    "Cleaning Compliance Ledger",
    "Facility Asset Movement Ledger",
    "Fuel Consumption Ledger",
    "Maintenance Cost Ledger",
    "Movement Cost Recovery",
    "Movement Cost Transfer",
    "Occupancy Snapshot",
    "Rental Accrual Ledger",
    "Safety Finding Ledger",
    "Trip Boarding Ledger",
    "Trip Fulfilment Ledger",
    "Vehicle Utilisation Snapshot",
})

# Both branches that read root ``read_only`` are guarded on ``not istable``
# (frappe/utils/user.py:130 and :162), so on a child table the flag is inert. It is set
# anyway so the set above reads without an exception, and the guard tolerates it rather
# than calling it a defect -- see the child-table test for why that stays honest.
INERT_ON_CHILD_TABLE = frozenset({"Trip Boarding State"})


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
        if not os.path.exists(path):
            # `_tracked_json_files` asks git, which still lists a file deleted in the
            # working tree but not yet committed. That file is no longer shipped, so it
            # is not a candidate — and opening it would fail the whole scan.
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
            "'read_only' (frappe labels it \"User Cannot Search\") -- but note what that "
            "does and does not do: it drops the doctype from can_search for everyone, and "
            "moves can_read to all_read only for a read-without-write grant. It keeps the "
            f"records out of search, it does not hide them: {carriers}",
        )

    def test_engine_ledgers_stay_out_of_search(self):
        """The POSITIVE of the concealment policy: the flag is still on, on exactly these.

        Every other check in this file is negative -- it catches a key that should not be
        there. Nothing asserted that the honoured key is still PRESENT, so any edit could
        drop ``read_only`` from a ledger and no gate would say a word. This set already
        shipped a concealment flag that was wrong for months; the positive is the half
        that would have caught it.

        What root ``read_only`` does, precisely (frappe labels it "User Cannot Search"):
        it drops the doctype from ``can_search`` unconditionally
        (frappe/utils/user.py:162-164), and it suppresses the list-view and workspace LINK
        via ``no_list_view_link``, removed from ``can_read`` at (:139-142, :181-183). It
        diverts ``can_read`` to ``all_read`` only for a read-WITHOUT-write-or-create grant.
        It does not hide the data: a role with write or create is untouched, and every row
        stays reachable through list views, reports, links, and the API.

        This fact is fixed here rather than re-derived by inspection: ``read_only`` appears
        ZERO times in ``frappe/permissions.py`` and ``frappe/model/db_query.py``, so
        ``has_permission`` and the query builder never consult it. Report access is
        roles-only by design -- ``can_get_report`` is built from the ``report`` DocPerm
        alone (:155-157), with no ``read_only`` branch. An audit of all 18 Script Reports,
        14 Number Cards and 14 Dashboard Charts over these doctypes found ZERO exposures:
        ``report_roles - doctype_permlevel0_read_roles`` is empty for every one, so each
        audience already holds the access and none of them is a defect to "fix".

        Asserted as set EQUALITY in both directions, so the tree cannot drift from the
        declared policy in either one: dropping the flag from a member fails, and adding
        it to a new doctype fails until that doctype is named here deliberately. A new
        ledger that ships with no flag at all is caught the moment its author has to
        decide whether it belongs in this list.
        """
        files = doctype_json_files()
        where = {doc.get("name"): rel(path) for path, doc in files}
        carriers = {doc.get("name") for _p, doc in files if doc.get("read_only")}

        def _named(names):
            # Name the JSON, not just the DocType: the reader has to go edit a file.
            return [f"{n} -> {where.get(n, 'no DocType JSON in tree')}" for n in sorted(names)]

        self.assertEqual(
            carriers,
            set(SEARCH_CONCEALED),
            "the set of DocTypes carrying root 'read_only' has drifted.\n"
            "  lost the flag (now searchable):\n    "
            + "\n    ".join(_named(SEARCH_CONCEALED - carriers) or ["-"])
            + "\n  newly carrying it (undeclared):\n    "
            + "\n    ".join(_named(carriers - SEARCH_CONCEALED) or ["-"])
            + "\n  Restore the flag, or update SEARCH_CONCEALED in this file and say why.",
        )

    def test_child_table_member_is_knowingly_inert(self):
        """The one member the flag cannot act on, pinned so the tolerance stays truthful.

        Both branches reading root ``read_only`` sit under ``not istable``, so on a child
        table it changes nothing. That is tolerated, not a defect -- but the tolerance is
        only honest while the record really is a child table. If it ever stops being one
        the flag becomes live and its effect needs a fresh decision, so this pins the
        premise instead of leaving it as a comment nobody rechecks.
        """
        istable = {doc.get("name") for _p, doc in doctype_json_files() if doc.get("istable")}
        self.assertLessEqual(
            INERT_ON_CHILD_TABLE,
            set(SEARCH_CONCEALED),
            "a doctype listed as inert-on-child-table is not in the concealed set",
        )
        self.assertEqual(
            set(SEARCH_CONCEALED) & istable,
            set(INERT_ON_CHILD_TABLE),
            "the child tables inside the concealed set changed; root 'read_only' is inert "
            "on a child table (guarded by 'not istable'), so review whether the flag now "
            f"acts -- expected {sorted(INERT_ON_CHILD_TABLE)}, "
            f"found {sorted(set(SEARCH_CONCEALED) & istable)}",
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
