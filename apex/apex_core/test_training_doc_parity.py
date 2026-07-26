# Copyright (c) 2026, AFMCO and contributors
"""The permission tables in ``docs/training/*.md`` must match the shipped DocPerm JSON.

Those tables were the largest unguarded published claim in the repo — around two hundred
cells stating, per DocType and per role, exactly which rights an operator holds. Nothing
read them, and they had rotted: six DocTypes were listed under names the app has not
shipped for some time (``Accommodation Assignment`` for ``Housing Assignment``,
``Habitat Safety Incident`` for ``Safety Incident``, and four more), a role column claimed
rights the JSON grants to two different roles, and five rows described two DocTypes at
once whose permissions are not in fact the same.

This is the workspace-parity guard (``tests/test_workspace_doc_parity.py``) applied one
layer down, and it checks two axes:

* NAME — every DocType a training table names must be shipped by apex, or be declared in
  ``EXTERNAL_DOCTYPES`` with a reason. This axis is exact and has no baseline: a wrong
  name makes the whole row meaningless, so there is nothing to freeze.
* RIGHTS — for each cell that spells out a rights list, the documented set must equal the
  permlevel-0 DocPerms the JSON grants that role. ``KNOWN_TABLE_DIVERGENCES`` freezes what
  was already out of step when this guard landed, each with a reason; the assertion is
  exact equality, so a NEW divergence fails and a CLOSED one fails until it is pruned.

Deliberately NOT a whole-table rewrite to match the JSON. Several frozen entries look like
the APP being wrong rather than the page — a master DocType whose only DocPerm row is
System Manager, for instance — and silently editing the page to agree would launder a
permission gap into documented behaviour. Freezing states the disagreement instead.

Cells that do not spell out rights (``scoped``, ``Read (own)``, a child table's row) are
listed in ``NON_SCHEMA_CELLS`` with a written reason. Declaring them is what keeps the
skip honest: an undeclared prose cell fails ``test_every_cell_is_parseable_or_declared``
rather than being silently dropped from the comparison.

The parsers take their roots as arguments so the falsifiability class can point them at a
temporary tree — proving a flipped cell is reported must not require editing shipped files.

It sits in apex_core because the tables span every module (Habitat, Salis, Logistay) and
the central apex/tests/ directory is closed to new modules (test_colocation_ratchet.py);
apex_core is the shared kernel, so a cross-module published-claim guard has a home here.

Run standalone:  python3 -m unittest apex.apex_core.test_training_doc_parity -v
"""

import json
import os
import re
import shutil
import tempfile
import unittest

from apex.tests.shipped_doctypes import shipped_doctypes
from apex.tests.training_charter import role_charters

APP_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
REPO_ROOT = os.path.dirname(APP_ROOT)
TRAINING_DIR = os.path.join(REPO_ROOT, "docs", "training")

# The six rights the published tables use. Frappe stores more (report, export, print,
# email, share, amend); the tables never spell those out, so comparing them would fail on
# every row for a claim the page does not make.
DOCUMENTED_FLAGS = ("read", "write", "create", "submit", "cancel", "delete")

_TABLE_DIVIDER = re.compile(r"^\|[\s:\-|]+\|$")
# A trailing "(master)" / "(submittable)" / "(workflow)" annotation on a DocType cell.
_ANNOTATION = re.compile(r"\((master|masters|submittable|workflow|child table|native [^)]*)\)")

EXTERNAL_DOCTYPES = {
    "Issue": (
        "native ERPNext DocType. Apex ships no JSON for it and the Driver role holds no "
        "Issue DocPerm at all — the portal creates and reads the ticket on the driver's "
        "behalf. Its rights cells are declared below for the same reason."
    ),
}

ROLE_HEADERS_OUTSIDE_THE_CHARTER = {
    "All": (
        "the built-in Frappe role every session holds. It is not an Apex persona, so it "
        "has no Roles at a glance row, but it does carry real DocPerms (the universal "
        "Maintenance Request intake) and belongs in the table."
    ),
    "Maintenance Manager": (
        "ERPNext-supplied role. docs/training/README.md states Apex grants it nothing, so "
        "it has no charter row; the column is published empty to record exactly that."
    ),
}

_CHILD_TABLE = (
    "Salis Vehicle Compliance is a child table. Frappe stores no DocPerms on a child "
    "table — its rows are governed by the embedding parent, Salis Vehicle, whose row is "
    "checked one line above. The cell says so instead of restating the parent's rights."
)

_OWNER_SCOPED = (
    "an if_owner grant reached through the Driver Portal, not a plain rights list. The "
    "row filter is the claim, and a flag comparison cannot express it; "
    "apex/salis/test_scope_role_partition.py guards the owner bucket instead."
)

_WORKFLOW_SCOPED = (
    "the Fuel Exception Case rights are decided by the active Frappe Workflow state, not "
    "by a fixed DocPerm set, so no single rights list is true for the whole lifecycle."
)

NON_SCHEMA_CELLS = {
    "child of Salis Vehicle": _CHILD_TABLE,
    "scoped": _WORKFLOW_SCOPED,
    "Read (own, via portal)": _OWNER_SCOPED,
    "Read (own)": _OWNER_SCOPED,
    "Read, Create (own)": _OWNER_SCOPED,
    "Create (Read own only)": (
        "the universal Maintenance Request intake: Create for everyone plus an if_owner "
        "read row. Two different grants in one cell, so a flat rights list is not what it "
        "claims; apex/habitat/permissions.py owns the read side."
    ),
}

KNOWN_TABLE_DIVERGENCES = {
    # Frozen baseline of (file, DocType, role) -> why the page and the JSON disagree.
    # Exact equality, so a NEW pair fails the build and a CLOSED pair fails until pruned.
    # Every entry below was already out of step when this guard landed; none was
    # introduced by it. Each names which side looks wrong, so closing one is a decision
    # about the app or the page, never a silent edit to whichever is easier to change.
    ("costs.md", "Operational Depreciation Policy", "Accommodation Manager"): (
        "APP looks wrong: the JSON grants this master to System Manager only, so the "
        "Accommodation Manager who is documented to maintain depreciation policy cannot "
        "open it. Publishing '—' would document the gap away."
    ),
    ("costs.md", "Operational Depreciation Policy", "Finance Manager"): (
        "Same row as above: Finance Manager holds no DocPerm on the policy master at all."
    ),
    ("custody.md", "Facility Asset Custody Assignment", "Accommodation Manager"): (
        "PAGE looks stale: the JSON has grown Submit and Cancel on this record while the "
        "table still describes it as a plain save. Confirm the record is meant to be "
        "submittable before republishing the wider set."
    ),
    ("custody.md", "Facility Asset Custody Assignment", "Resident Supervisor"): (
        "Same row: the JSON grants Write, Create and Submit where the page says Read only. "
        "The wider grant needs confirming against the building-scoping rule."
    ),
    ("custody.md", "Cleaning Log", "Cleaning Supervisor"): (
        "PAGE looks stale on Submit: the note under the table calls Cleaning Log 'not "
        "submittable', but the JSON grants the Cleaning Supervisor Submit. One of the two "
        "is a mistake and it is not safe to guess which."
    ),
    ("compliance.md", "Movement Cost Recovery", "Fleet Supervisor"): (
        "PAGE looks stale: the JSON grants Submit, so a supervisor can post a recovery "
        "the page says only Finance can. A segregation-of-duties question, not a typo."
    ),
    ("fleet-movement.md", "Salis Vehicle", "Fleet Project Manager"): (
        "PAGE looks stale: the JSON grants Submit on a DocType the same page states is "
        "not submittable. The contradiction is inside the app, so freeze rather than pick."
    ),
    ("fleet-movement.md", "Salis Driver", "Fleet Project Manager"): (
        "APP looks wrong the other way: the page documents Submit and the JSON grants "
        "none, so the driver-record approval step the guide teaches cannot be performed."
    ),
    ("fleet-movement.md", "Vehicle Category", "Fleet Manager"): (
        "PAGE understates by one flag: the JSON also grants Delete on this master."
    ),
    ("fleet-movement.md", "Vehicle Category", "Fleet Project Manager"): (
        "PAGE understates: read-only in the guide, Write and Create in the JSON. A master "
        "editable by every project manager is a data-quality decision worth confirming."
    ),
    ("fleet-movement.md", "Vehicle Category", "Fleet Supervisor"): (
        "Same master, same widening one role down."
    ),
    ("fleet-movement.md", "Driver Clearance", "Fleet Project Manager"): (
        "APP looks wrong: the page documents the project manager as the maker on driver "
        "clearance and the JSON gives it no row at all, so the documented step is unusable."
    ),
    ("fuel.md", "Fuel Platform", "Fleet Manager"): (
        "PAGE understates by one flag: the JSON also grants Delete on this master."
    ),
    ("fuel.md", "Fuel Platform", "Fleet Project Manager"): (
        "PAGE understates: read-only in the guide, Write and Create in the JSON."
    ),
    ("fuel.md", "Fuel Platform", "Fleet Supervisor"): (
        "Same master, same widening one role down."
    ),
    ("maintenance.md", "Maintenance Inspection Report", "Accommodation Manager"): (
        "APP looks wrong: the JSON's only permission row is System Manager, so the "
        "inspection step between request and work order has no operational owner."
    ),
    ("safety.md", "Building License", "Safety Officer"): (
        "APP looks wrong: the page publishes '—' and the JSON grants Read, Write and "
        "Create. Building licences sit outside the published Safety Officer charter "
        "(inspections, executions, incidents), so this reads as an over-grant."
    ),
}


UNGUARDED_PUBLISHED_CLASSES = (
    # In priority order. Each entry states the size measured when this guard landed and
    # whether the class is worth a guard AS PUBLISHED, because the deciding question is
    # never the cell count — it is whether the page states a fact a machine can resolve.
    (
        "README.md served-portal-routes table",
        "28 cells across 7 routes, plus 4 role-set constants and 2 endpoint counts named "
        "in the surrounding prose. WORTH A GUARD, and the highest-value one left: it is "
        "the published access-control record for every portal surface, nothing under "
        "apex/ reads it, and it is unusually checkable — FLEET_ROLES, HOUSING_ROLES, "
        "SAFETY_ROLES and SUPERVISOR_ROLES are real Python sets, and '(4 endpoints)' and "
        "'(13 endpoints)' are countable from the api modules. The parenthesised-list and "
        "number-word techniques this guard uses apply unchanged."
    ),
    (
        "docs/TRAINING.md index",
        "11 page links and one 'seven portal routes' count, read by nothing. WORTH A "
        "GUARD, and a cheap one: link targets either resolve on disk or they do not, and "
        "the count is the same number-word claim made in two other published files, so "
        "all three can be tied together. Small, but a renamed page breaks it silently."
    ),
    (
        "DocType names in training prose",
        "80 bold spans outside any table, of which 34 resolve to a shipped DocType. NOT "
        "WORTH A GUARD AS PUBLISHED: bold marks emphasis, roles, desk pages and DocTypes "
        "alike, so a guard would need a suppression list roughly as long as the class it "
        "checks. Normalise first — write DocType names in prose as `Backticked Name` and "
        "the same name axis this module already implements covers them for free."
    ),
    (
        "Key-field bullets in the training guides",
        "about 70 names across the per-area pages. NOT WORTH A GUARD AS PUBLISHED: they "
        "are human phrases ('employee/resident', 'start date'), not fieldnames, so "
        "matching them to the schema needs fuzzy comparison. A fuzzy guard over prose "
        "fires on rewording rather than on drift, which is worse than a recorded gap."
    ),
    (
        "Background-job list in settings.md",
        "about 22 job descriptions. NOT WORTH A GUARD AS PUBLISHED: they are English "
        "descriptions, not the scheduler keys in hooks.py, so a guard needs a "
        "phrase-to-dotted-path alias map — and that map would itself be an unread copy "
        "of the page, which is the exact failure this card was opened to remove."
    ),
)


def _cell(text):
    return text.replace("*", "").strip()


def _tables(path):
    """Yield (line number of the header, header cells, data rows) for each pipe table."""
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    index = 0
    while index < len(lines):
        divider = index + 1 < len(lines) and _TABLE_DIVIDER.match(lines[index + 1])
        if not (lines[index].startswith("|") and divider):
            index += 1
            continue
        header = [_cell(c) for c in lines[index].strip().strip("|").split("|")]
        rows, cursor = [], index + 2
        while cursor < len(lines) and lines[cursor].startswith("|"):
            rows.append((cursor + 1, [_cell(c) for c in lines[cursor].strip().strip("|").split("|")]))
            cursor += 1
        yield index + 1, header, rows
        index = cursor


def _doctype_name(label):
    """The DocType a first-column cell names, with its `(submittable)` style tag removed."""
    return _ANNOTATION.sub("", label).strip()


def documented_doctypes(root=TRAINING_DIR):
    """{(file, DocType): first line it appears on} across every table keyed by DocType."""
    found = {}
    for name in sorted(os.listdir(root)):
        if not name.endswith(".md"):
            continue
        for _header_line, header, rows in _tables(os.path.join(root, name)):
            if not header or header[0] != "DocType":
                continue
            for lineno, row in rows:
                found.setdefault((name, _doctype_name(row[0])), lineno)
    return found


def documented_cells(root=TRAINING_DIR, roles=None):
    """{(file, DocType, role): cell text} for every table whose columns are all roles."""
    known = set(roles if roles is not None else role_charters()) | set(
        ROLE_HEADERS_OUTSIDE_THE_CHARTER
    )
    cells = {}
    for name in sorted(os.listdir(root)):
        if not name.endswith(".md"):
            continue
        for _header_line, header, rows in _tables(os.path.join(root, name)):
            if not header or header[0] != "DocType" or len(header) < 2:
                continue
            if not all(column in known for column in header[1:]):
                continue
            for _lineno, row in rows:
                doctype = _doctype_name(row[0])
                for role, text in zip(header[1:], row[1:]):
                    cells[(name, doctype, role)] = text
    return cells


def granted_flags(data, role):
    """The DOCUMENTED_FLAGS a role holds at permlevel 0, unioned over its rows."""
    held = set()
    for row in data.get("permissions") or []:
        if row.get("role") == role and not row.get("permlevel"):
            held |= {flag for flag in DOCUMENTED_FLAGS if row.get(flag)}
    return held


def parse_rights(text):
    """The flag set a cell spells out, or None if it is not a rights list."""
    if text == "—":
        return frozenset()
    tokens = [token.strip().lower() for token in text.split(",") if token.strip()]
    if tokens and all(token in DOCUMENTED_FLAGS for token in tokens):
        return frozenset(tokens)
    return None


def rights_divergences(cells, doctypes):
    """{(file, DocType, role): (documented, granted)} for every cell that disagrees.

    Pure over its inputs so the falsifiability class can drive it with planted data.
    """
    found = {}
    for key, text in cells.items():
        _name, doctype, role = key
        documented = parse_rights(text)
        if documented is None or doctype in EXTERNAL_DOCTYPES:
            continue
        data = doctypes.get(doctype)
        if data is None:
            continue
        granted = granted_flags(data, role)
        if documented != granted:
            found[key] = (sorted(documented), sorted(granted))
    return found


class TestTrainingPermissionTablesParse(unittest.TestCase):
    """Non-vacuity, and the declared-exception rules that keep the skips honest."""

    def setUp(self):
        self.doctypes = shipped_doctypes()
        self.cells = documented_cells()

    def test_both_sides_were_actually_parsed(self):
        self.assertGreater(len(self.cells), 150, "training tables did not parse — scan broke")
        self.assertGreater(len(self.doctypes), 50, "DocType JSON scan found nothing")
        for landmark in ("Housing Assignment", "Salis Vehicle", "Cleaning Log"):
            self.assertIn(landmark, self.doctypes)

    def test_every_cell_is_parseable_or_declared(self):
        """A cell that is neither a rights list nor a declared exception is unguarded."""
        undeclared = sorted(
            {
                text
                for key, text in self.cells.items()
                if parse_rights(text) is None and text not in NON_SCHEMA_CELLS
            }
        )
        self.assertEqual(
            undeclared,
            [],
            "training permission cell(s) state something no DocPerm flag expresses and are "
            "not declared in NON_SCHEMA_CELLS, so they silently escape this guard. Rewrite "
            f"them as a rights list or declare them with a reason: {undeclared}",
        )

    def test_declared_exceptions_all_carry_a_reason(self):
        for mapping in (NON_SCHEMA_CELLS, EXTERNAL_DOCTYPES, ROLE_HEADERS_OUTSIDE_THE_CHARTER):
            for key, reason in mapping.items():
                with self.subTest(entry=key):
                    self.assertTrue(reason and reason.strip(), f"'{key}' has no reason")

    def test_declared_non_schema_cells_are_all_in_use(self):
        """A declaration matching no cell is a stale skip that widens the guard for free."""
        stale = sorted(set(NON_SCHEMA_CELLS) - set(self.cells.values()))
        self.assertEqual(stale, [], f"NON_SCHEMA_CELLS entries match no published cell: {stale}")

    def test_the_remaining_unguarded_classes_stay_recorded(self):
        """The gaps this card chose not to close must keep a written verdict, not vanish.

        An unguarded published claim that nobody has written a decision about is how the
        training tables rotted in the first place; the register is the ratchet against
        repeating that, so an entry may be removed only when the gap is actually closed.
        """
        self.assertGreaterEqual(len(UNGUARDED_PUBLISHED_CLASSES), 5, "the register shrank")
        for name, verdict in UNGUARDED_PUBLISHED_CLASSES:
            with self.subTest(published_class=name):
                self.assertTrue(name.strip(), "register entry has no name")
                self.assertTrue(verdict.strip(), f"'{name}' records no verdict")
                self.assertIn(
                    "WORTH A GUARD",
                    verdict,
                    f"'{name}' does not state a WORTH A GUARD / NOT WORTH A GUARD verdict",
                )


class TestTrainingDocTypeNamesAreShipped(unittest.TestCase):
    """The name axis: a table row about a DocType that does not exist teaches nothing."""

    def test_every_documented_doctype_is_shipped_or_declared(self):
        shipped = shipped_doctypes()
        unknown = sorted(
            f"{name}:{line} {doctype!r}"
            for (name, doctype), line in documented_doctypes().items()
            if doctype not in shipped and doctype not in EXTERNAL_DOCTYPES
        )
        self.assertEqual(
            unknown,
            [],
            "docs/training names DocType(s) apex does not ship. Six had drifted this way "
            "before the guard existed, each renamed in the app and left stale on the page. "
            "Correct the name, or declare it in EXTERNAL_DOCTYPES if another app owns it: "
            f"{unknown}",
        )

    def test_the_renamed_doctypes_stay_corrected(self):
        """The specific rot this guard was written for, asserted by name."""
        published = {doctype for _file, doctype in documented_doctypes()}
        for stale in (
            "Accommodation Assignment",
            "Accommodation Checkout",
            "Accommodation Resident Request",
            "Accommodation Lease",
            "Habitat Safety Incident",
            "Salis Portal Theme",
        ):
            with self.subTest(name=stale):
                self.assertNotIn(stale, published, f"{stale} is not a shipped DocType name")


class TestTrainingRightsMatchTheDocPerms(unittest.TestCase):
    """The rights axis, against the frozen baseline of what was already out of step."""

    def test_no_new_divergence_between_the_page_and_the_json(self):
        found = rights_divergences(documented_cells(), shipped_doctypes())
        self.assertEqual(
            sorted(found),
            sorted(KNOWN_TABLE_DIVERGENCES),
            "training permission table / DocPerm parity changed. A NEW entry means the "
            "published rights and the shipped DocPerms disagree — fix whichever is wrong, "
            "or freeze it with a written reason. A MISSING entry means a disagreement was "
            "resolved and the baseline must shrink. Live diff: "
            f"{ {k: v for k, v in found.items() if k not in KNOWN_TABLE_DIVERGENCES} }",
        )

    def test_every_frozen_divergence_carries_a_reason(self):
        for key, reason in KNOWN_TABLE_DIVERGENCES.items():
            with self.subTest(entry=key):
                self.assertTrue(reason and reason.strip(), f"{key} has no documented reason")

    def test_frozen_divergences_name_a_published_role(self):
        """A baseline keyed on a role nobody publishes is one nobody will ever review."""
        known = set(role_charters()) | set(ROLE_HEADERS_OUTSIDE_THE_CHARTER)
        strays = sorted({role for _f, _d, role in KNOWN_TABLE_DIVERGENCES if role not in known})
        self.assertEqual(strays, [], f"frozen entries name unpublished role(s): {strays}")


class TestParityGuardIsFalsifiable(unittest.TestCase):
    """Flip one cell on each side and prove the comparison reports it.

    Driven against temporary copies of the real page and a real DocType JSON: a proof that
    mutates tracked files is one failed revert away from corrupting the tree it proves.
    """

    DOC = "safety.md"
    DOCTYPE = "Safety Task Execution"
    ROLE = "Safety Officer"

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.docs = os.path.join(self.tmp, "training")
        shutil.copytree(TRAINING_DIR, self.docs)
        self.source = os.path.join(APP_ROOT, "habitat", "doctype", "safety_task_execution")
        self.json_path = os.path.join(self.tmp, "safety_task_execution.json")
        shutil.copyfile(
            os.path.join(self.source, "safety_task_execution.json"), self.json_path
        )

    def _doctypes(self):
        with open(self.json_path, encoding="utf-8") as fh:
            return {self.DOCTYPE: json.load(fh)}

    def _compare(self):
        cells = documented_cells(self.docs)
        mine = {key: text for key, text in cells.items() if key[1] == self.DOCTYPE}
        self.assertTrue(mine, "fixture rows did not parse")
        return rights_divergences(mine, self._doctypes())

    def _edit_doc(self, old, new):
        path = os.path.join(self.docs, self.DOC)
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn(old, text, "fixture row no longer matches the edit pattern")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text.replace(old, new, 1))

    def test_the_unmodified_copy_agrees(self):
        self.assertEqual(self._compare(), {}, "baseline fixture must start clean")

    def test_a_flipped_documented_cell_is_reported(self):
        """Doc side: drop Create from the Safety Officer cell and it must red."""
        self._edit_doc(
            "| **Safety Task Execution** *(submittable)* | Read, Write, Create, Submit, Cancel "
            "| Read, Write, Create, Submit | Read, Write, Create |",
            "| **Safety Task Execution** *(submittable)* | Read, Write, Create, Submit, Cancel "
            "| Read, Write, Create, Submit | Read, Write |",
        )
        found = self._compare()
        self.assertIn((self.DOC, self.DOCTYPE, self.ROLE), found, f"flip went unreported: {found}")
        self.assertEqual(
            found[(self.DOC, self.DOCTYPE, self.ROLE)],
            (["read", "write"], ["create", "read", "write"]),
        )

    def test_a_flipped_docperm_is_reported(self):
        """JSON side: grant the same role Delete and it must red just as loudly."""
        with open(self.json_path, encoding="utf-8") as fh:
            data = json.load(fh)
        for row in data["permissions"]:
            if row.get("role") == self.ROLE:
                row["delete"] = 1
        with open(self.json_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)

        found = self._compare()
        self.assertIn((self.DOC, self.DOCTYPE, self.ROLE), found, f"grant went unreported: {found}")
        self.assertIn("delete", found[(self.DOC, self.DOCTYPE, self.ROLE)][1])

    def test_a_renamed_doctype_leaves_the_shipped_set(self):
        """Name axis: rename a row's DocType and it stops resolving."""
        self._edit_doc("| **Safety Task Execution** *(submittable)* |", "| **Safety Execution** |")
        published = {doctype for _file, doctype in documented_doctypes(self.docs)}
        self.assertIn("Safety Execution", published)
        self.assertNotIn("Safety Execution", shipped_doctypes())


if __name__ == "__main__":
    unittest.main()
