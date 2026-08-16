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
only, with even the Internal Auditor kept out.

WHAT MOVED HERE AND WHY. This module used to carry a second class asserting the
Freelancer DocPerm JSON row by row (create present/omitted, permlevel-1 rows
present/absent, per role) — a Change Detector Test pinning the file's text.
Every one of those claims is now asked live, of the framework, and mostly by a
sibling that already existed: `test_freelancer.py::test_only_the_permlevel1_roles_can_create`
inserts as Finance Manager (succeeds) and as Accommodation Manager
(`frappe.PermissionError`), checking `frappe.has_permission` and
`get_permlevel_access` on a real document. That test is a strict superset of
what the removed JSON-reading assertions covered for those two roles, so
deleting the duplicate loses no coverage a reader could notice.

The one claim the sibling did NOT cover — that the read-only Internal Auditor
never reaches Freelancer's permlevel-1 boundary either — is kept below, asked
the same live way. A future widening of the auditor's grant is a real
regression (PII exposed to a read-only role); it would not be caught by the
app-wide sweep, because a role that CAN complete a create it now holds is not
an "unusable create" by that sweep's definition.

The app-wide sweep still rides here rather than in `apex/tests/` on purpose: it
is the recurrence guard for the defect this module documents, it needs no
site, and the colocation ratchet (apex/tests/test_colocation_ratchet.py)
forbids a new central module. It has no per-DocType behavioural substitute —
proving it live would mean inserting as every create-holding role against
every one of the app's 50+ shipped DocTypes, most of which carry unrelated
mandatory links this module has no business setting up.

Run standalone (from the repo root):
  python3 -m unittest apex.logistay.doctype.freelancer.test_freelancer_create_permission -v
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import frappe
from frappe.tests.utils import FrappeTestCase

import apex
from apex.tests._helpers import _user, as_user

_HERE = Path(apex.__file__).resolve().parent / "logistay" / "doctype" / "freelancer"
_APP_ROOT = _HERE.parents[2]

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


class TestEveryAppDocTypeCreateGrantIsUsable(unittest.TestCase):
    """The invariant across every DocType the app ships: a role with `create` can
    always complete it. No per-DocType behavioural substitute scales to 50+
    DocTypes and every role that holds `create` on each of them."""

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


class TestInternalAuditorStaysOutOfFreelancerPii(FrappeTestCase):
    """The read-only role never reaches the permlevel-1 boundary the paying
    roles were given, asked live rather than off the DocPerm JSON.

    Companion to `test_freelancer.py::test_only_the_permlevel1_roles_can_create`,
    which proves who CAN create; this proves the read-only auditor can never
    widen into it. `frappe.has_permission` reads DocPerm, Custom DocPerm, User
    Permission and any `has_permission` hook together — a JSON read sees only
    one of the four.
    """

    AUDITOR = "freelancer_create_permission_auditor@example.com"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.auditor = _user(cls.AUDITOR, "Internal Auditor")

    def test_the_auditor_cannot_write_freelancer_and_reaches_no_permlevel_one_field(self):
        with as_user(self.auditor):
            self.assertTrue(
                frappe.has_permission("Freelancer", "read"),
                "Internal Auditor must still be able to read Freelancer",
            )
            for action in ("write", "create", "delete", "submit", "cancel", "amend"):
                self.assertFalse(
                    frappe.has_permission("Freelancer", action),
                    f"Internal Auditor must not be able to {action} Freelancer",
                )
            probe = frappe.new_doc("Freelancer")
            self.assertNotIn(
                1,
                probe.get_permlevel_access("write"),
                "Internal Auditor must not reach Freelancer's permlevel-1 PII fields "
                "— a role that cannot write at all must not appear to write PII either",
            )


if __name__ == "__main__":
    unittest.main()
