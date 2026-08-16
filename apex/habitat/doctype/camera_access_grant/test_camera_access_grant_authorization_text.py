# Copyright (c) 2026, AFMCO and contributors
"""``approved_by`` records an out-of-system fact. It is not a control and never was.

A Camera Access Grant is requested and submitted by the same role, and that flow is
deliberate. What is not allowed is a field named and described as an approval while nothing
reads it: the label said "Approved By" and the description said "Must be Admin Manager"
beside a controller that runs no check and a hooks entry that registers none.

The field was KEPT and its text rewritten rather than dropped. Two reasons:
  1. Shipped rows carry real history -- who authorized past grants outside the system.
     Dropping the field would leave that column and its data sitting in the table
     (a plain removal never drops the column) while hiding it from every reader, which
     is worse than the misleading label: the record becomes unreachable but not gone.
  2. The defect was the TEXT. Rewriting text is reversible and costs no schema change,
     so no patch is owed and no existing row changes value.

The fieldname stays ``approved_by`` on purpose. Renaming a shipped column is DB-breaking
and ``rename_field`` copies forward without ever dropping the old column, so a rename
would trade a misleading label for two columns holding the same fact. The decision was
about what a reader is TOLD -- so the label and the description are what changed.

BOTH HALVES LIVE HERE so the next auditor finds the decision instead of the silence:
the absence of an approval gate, and the absence of enforcement wording. Either one
alone re-opens as a defect.

Site-free: every assertion reads the shipped JSON, the controller source and hooks.py.

Run under bench:
  bench --site <site> run-tests --module apex.habitat.doctype.camera_access_grant.test_camera_access_grant_authorization_text
"""

from __future__ import annotations

import json
from pathlib import Path

from frappe.tests.utils import FrappeTestCase

import apex

_HERE = Path(apex.__file__).resolve().parent / "habitat" / "doctype" / "camera_access_grant"
_GRANT_JSON = _HERE / "camera_access_grant.json"
_GRANT_PY = _HERE / "camera_access_grant.py"
_HOOKS_PY = _HERE.parents[2] / "hooks.py"

FIELDNAME = "approved_by"

# Words that assert the app DOES something. "authorized" is deliberately absent: it is
# the owner's own word for the out-of-system fact this field records and implies no
# check by itself. Every entry below claims a mechanism that does not exist.
ENFORCEMENT_WORDS = (
    "approve",
    "approved",
    "approval",
    "approver",
    "must",
    "required",
    "requires",
    "mandatory",
    "enforce",
    "enforced",
    "blocks",
    "prevents",
    "not permitted",
)


class TestCameraAccessGrantAuthorizationText(FrappeTestCase):
    def _field(self):
        shipped = json.loads(_GRANT_JSON.read_text(encoding="utf-8"))
        matches = [f for f in shipped["fields"] if f.get("fieldname") == FIELDNAME]
        self.assertEqual(
            len(matches),
            1,
            f"{FIELDNAME} was removed or duplicated -- the decision kept exactly one",
        )
        return matches[0]

    def test_no_approval_check_runs_on_submit(self):
        """HALF ONE. The controller declares no ``before_submit`` and hooks registers
        none for this DocType. A field text that promised a check would be a lie about
        this fact -- which is precisely why the two halves are asserted together."""
        controller = _GRANT_PY.read_text(encoding="utf-8")
        self.assertNotIn(
            "def before_submit",
            controller,
            "an approval gate appeared -- the 2026-07-27 decision was that the flow "
            "stays as it is; re-decide before adding one",
        )

        # The other place a gate could hide: a doc_events entry. The DocType is present
        # in hooks with an EMPTY mapping, so assert the mapping is still empty rather
        # than assuming absence.
        hooks = _HOOKS_PY.read_text(encoding="utf-8")
        self.assertIn(
            '"Camera Access Grant": {}',
            hooks,
            "hooks.py now registers doc_events for Camera Access Grant -- if one of "
            "them is an approval gate the field text below is wrong",
        )

    def test_the_field_text_claims_no_enforcement(self):
        """HALF TWO. Label and description are scanned -- not the fieldname, which stays
        ``approved_by`` because renaming a shipped column is DB-breaking, and not the
        ``status`` Select, whose "Pending Approval" and "Approved" values describe the
        business lifecycle the owner explicitly kept."""
        field = self._field()
        for key in ("label", "description"):
            text = (field.get(key) or "").lower()
            self.assertTrue(text, f"{FIELDNAME} has no {key} -- it must say what it is")
            for word in ENFORCEMENT_WORDS:
                self.assertNotIn(
                    word,
                    text,
                    f"{FIELDNAME} {key} says '{word}' -- it claims a check that does "
                    f"not exist. Current {key}: {field.get(key)!r}",
                )

    def test_the_description_says_what_the_field_actually_is(self):
        """The negative above is satisfiable by an EMPTY description. This is the
        positive half: the reader must be told it is a record and that the app ignores
        it, otherwise the field is merely vague instead of misleading."""
        description = (self._field().get("description") or "").lower()
        self.assertIn(
            "record",
            description,
            "the description must say this is a written record",
        )
        self.assertIn(
            "outside the system",
            description,
            "the description must say the authorization happened outside the app",
        )
        self.assertIn(
            "nothing in the app reads this field",
            description,
            "the description must state plainly that no code reads it",
        )

    def test_the_field_is_still_optional_and_still_a_user_link(self):
        """The field's shape stays as shipped even where its description text differs:
        fieldtype, options and reqd are unchanged, so existing rows keep their value
        and no patch is owed."""
        field = self._field()
        self.assertEqual(field.get("fieldtype"), "Link")
        self.assertEqual(field.get("options"), "User")
        self.assertFalse(
            field.get("reqd"),
            "the field became mandatory -- that is a control and was not decided",
        )
        order = json.loads(_GRANT_JSON.read_text(encoding="utf-8"))["field_order"]
        self.assertIn(
            FIELDNAME, order, f"{FIELDNAME} vanished from field_order -- it is kept"
        )
