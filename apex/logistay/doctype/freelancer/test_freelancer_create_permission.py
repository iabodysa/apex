# Copyright (c) 2026, AFMCO and contributors
"""A `create` grant a role cannot complete is worse than no grant at all.

Freelancer shipped `create=1` for **Accommodation Manager** at permlevel 0 while
`national_id_or_iqama` is `reqd` at permlevel **1**, and that role held no
permlevel-1 row. Every attempt therefore died the same way, and the button was
still on the form:

  * `Document.insert` runs `validate_higher_perm_levels()`
    (frappe/model/document.py:306) BEFORE `_validate()` (:310).
  * With no permlevel-1 write row, `get_permlevel_access("write")`
    (document.py:808) omits 1, so `reset_values_if_no_permlevel_access`
    (base_document.py:1263) overwrites the submitted national id with the value
    from `frappe.new_doc` — empty, since the field has no default.
  * `_validate_mandatory` (document.py:946) then raises `frappe.MandatoryError`.

A permlevel-1 row is NOT a duplicate of the permlevel-0 one and never a
substitute for it: `is_perm_applicable` (frappe/permissions.py:283) keeps only
`permlevel == 0` rows when resolving create/read/write, so the two rows answer
two different questions and both are needed to create a record with PII on it.

The fix removed `create` rather than widening permlevel 1, because Freelancer's
permlevel-1 set is deliberately narrow — Finance Manager and System Manager
only, with even the Internal Auditor kept out (see the sibling
`test_permlevel_pii_hidden_from_unprivileged_role`). Temporary Worker, the
housing identity this record is explicitly NOT, gives every one of its create
roles a matching permlevel-1 row; Freelancer is the payroll party, and housing
does not originate one.

Note the omission is the mechanism: `create` carries `default: 1` on DocPerm, but
`_set_defaults` returns early while the framework is in import mode
(document.py:833, the flag being set by frappe/modules/import_file.py:212), so a
key left out of a shipped DocPerm row imports as 0. The runtime half lives in
`test_freelancer.py::test_only_the_permlevel1_roles_can_create` — this module is
structural only.

The app-wide sweep rides here rather than in `apex/tests/` on purpose: it is the
recurrence guard for the defect this module documents, it needs no site, and the
colocation ratchet (apex/tests/test_colocation_ratchet.py) forbids a new central
module. One offender existed app-wide when it was written — the one above.

Run standalone (from the repo root):
  python3 -m unittest apex.logistay.doctype.freelancer.test_freelancer_create_permission -v
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import apex

_HERE = Path(apex.__file__).resolve().parent / "logistay" / "doctype" / "freelancer"
_APP_ROOT = _HERE.parents[2]
_FREELANCER_JSON = _HERE / "freelancer.json"

# Layout-only fieldtypes carry no value, so `reset_values_if_no_permlevel_access`
# skips them (base_document.py:1270) and they can never block a create.
_DISPLAY_FIELDTYPES = frozenset(
    {"Section Break", "Column Break", "Tab Break", "HTML", "Heading", "Fold", "Button"}
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _permlevel(row: dict) -> int:
    return int(row.get("permlevel") or 0)


def _blocking_reqd_fields(doctype: dict) -> list[dict]:
    """Mandatory fields above permlevel 0 that a create must supply itself.

    A field with a `default` is exempt: `reset_values_if_no_permlevel_access`
    restores it from `frappe.new_doc`, which applies the default, so the
    mandatory check still passes.
    """
    return [
        f
        for f in doctype.get("fields") or []
        if f.get("reqd")
        and _permlevel(f) > 0
        and f.get("fieldtype") not in _DISPLAY_FIELDTYPES
        and not f.get("default")
    ]


def _unusable_create_grants(doctype: dict) -> list[str]:
    """`role -> fields it can never fill` for every create grant that cannot complete."""
    perms = doctype.get("permissions") or []
    blocking = _blocking_reqd_fields(doctype)
    if not blocking:
        return []
    offenders = []
    for role in sorted({p["role"] for p in perms if p.get("create") and _permlevel(p) == 0}):
        writable = {_permlevel(p) for p in perms if p.get("role") == role and p.get("write")}
        blocked = [f["fieldname"] for f in blocking if _permlevel(f) not in writable]
        if blocked:
            offenders.append(
                f"{doctype['name']}: {role!r} has create=1 but no write row at permlevel "
                f"{sorted({_permlevel(f) for f in blocking if f['fieldname'] in blocked})} "
                f"-> can never supply {sorted(blocked)}"
            )
    return offenders


def _app_doctypes():
    """Every DocType JSON shipped by the app, as (path, parsed) pairs."""
    for jp in sorted(_APP_ROOT.glob("**/doctype/*/*.json")):
        if jp.stem != jp.parent.name:
            continue
        try:
            data = _load(jp)
        except (ValueError, OSError):
            continue
        if data.get("doctype") == "DocType" and data.get("name"):
            yield jp, data


class TestFreelancerCreateGrantIsUsable(unittest.TestCase):
    """The shipped Freelancer DocPerm, read straight off disk."""

    @classmethod
    def setUpClass(cls):
        cls.doctype = _load(_FREELANCER_JSON)
        cls.perms = cls.doctype["permissions"]

    def _rows(self, role, permlevel=0):
        return [p for p in self.perms if p.get("role") == role and _permlevel(p) == permlevel]

    def test_the_pii_field_is_still_the_reason_this_guard_exists(self):
        """Guard-of-the-guard: an empty scan would pass every assertion below.

        The second entry arrived when `monthly_salary` moved to permlevel 1 under the field
        sensitivity model (per-person pay); it is `reqd` with no default, so it joins
        `national_id_or_iqama` as a field a create must be able to write. That is precisely
        why this guard is worth keeping — the move was only safe because every role holding
        `create` here (Finance Manager, System Manager) also holds a permlevel-1 write row,
        which `test_no_role_holds_a_create_it_can_never_complete` re-checks below.
        """
        blocking = _blocking_reqd_fields(self.doctype)
        self.assertEqual(
            [f["fieldname"] for f in blocking],
            ["national_id_or_iqama", "monthly_salary"],
            "Freelancer's mandatory-above-permlevel-0 set changed; re-derive who may create",
        )

    def test_no_role_holds_a_create_it_can_never_complete(self):
        self.assertEqual(_unusable_create_grants(self.doctype), [])

    def test_accommodation_manager_cannot_create_and_keeps_no_pii_row(self):
        """The removed half: no create, and deliberately still outside permlevel 1."""
        rows = self._rows("Accommodation Manager")
        self.assertEqual(len(rows), 1, "expected exactly one permlevel-0 row")
        self.assertNotIn("create", rows[0], "create must be OMITTED, not shipped as 0")
        self.assertEqual(rows[0].get("read"), 1, "read must survive the create removal")
        self.assertEqual(rows[0].get("write"), 1, "write must survive the create removal")
        self.assertEqual(
            self._rows("Accommodation Manager", permlevel=1),
            [],
            "granting permlevel 1 here would put housing inside the payroll-PII "
            "boundary the Internal Auditor is deliberately kept out of",
        )

    def test_the_paying_roles_can_both_create_and_fill_the_pii(self):
        """The kept half, asserted beside the refusal so the two cannot collapse."""
        for role in ("Finance Manager", "System Manager"):
            with self.subTest(role=role):
                self.assertEqual(self._rows(role)[0].get("create"), 1)
                high = self._rows(role, permlevel=1)
                self.assertEqual(len(high), 1, f"{role}: expected one permlevel-1 row")
                self.assertEqual(high[0].get("write"), 1, f"{role}: permlevel-1 write missing")

    def test_internal_auditor_stays_read_only_at_permlevel_zero(self):
        """Regression guard: this fix must not have widened the auditor's view."""
        rows = self._rows("Internal Auditor")
        self.assertEqual(len(rows), 1)
        for flag in ("create", "write", "delete", "submit", "cancel", "amend"):
            self.assertNotEqual(rows[0].get(flag), 1, f"Internal Auditor must not have {flag}")
        self.assertEqual(self._rows("Internal Auditor", permlevel=1), [])


class TestEveryAppDocTypeCreateGrantIsUsable(unittest.TestCase):
    """The same invariant across every DocType the app ships."""

    def test_scan_reaches_the_shipped_doctypes(self):
        names = {d["name"] for _, d in _app_doctypes()}
        self.assertGreater(len(names), 50, "DocType scan returned implausibly few files")
        self.assertIn("Freelancer", names)
        self.assertIn("Temporary Worker", names)

    def test_no_shipped_doctype_grants_a_create_that_cannot_complete(self):
        offenders = []
        for _, doctype in _app_doctypes():
            offenders.extend(_unusable_create_grants(doctype))
        self.assertEqual(
            sorted(offenders),
            [],
            "role(s) hold create on a DocType whose mandatory field sits above "
            "permlevel 0 with no matching write row — the create button is on the "
            "form and every press raises MandatoryError:\n" + "\n".join(sorted(offenders)),
        )


if __name__ == "__main__":
    unittest.main()
