# Copyright (c) 2026, AFMCO and contributors
from __future__ import annotations
import frappe
from frappe.tests.utils import FrappeTestCase
import json
from pathlib import Path
import apex



class TestCameraAccessGrant(FrappeTestCase):

    def test_create_valid_grant(self):
        doc = frappe.get_doc({
            "doctype": "Camera Access Grant",
            "naming_series": "CAM-ACC-.YYYY.-.####",
            "requested_for": "Administrator",
            "valid_from": "2026-06-01",
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertIsNotNone(doc.name)
        frappe.delete_doc("Camera Access Grant", doc.name, force=True, ignore_permissions=True)

    def test_missing_requested_for_raises(self):
        doc = frappe.get_doc({
            "doctype": "Camera Access Grant",
            "naming_series": "CAM-ACC-.YYYY.-.####",
            "valid_from": "2026-06-01",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_missing_valid_from_raises(self):
        doc = frappe.get_doc({
            "doctype": "Camera Access Grant",
            "naming_series": "CAM-ACC-.YYYY.-.####",
            "requested_for": "Administrator",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

test_ignore = ['Additional Salary', 'Asset', 'Asset Movement', 'Company', 'Cost Center', 'Currency', 'Employee', 'Item', 'Payment Entry', 'Project', 'Purchase Invoice', 'Role', 'Salary Component', 'Supplier', 'User']


# --- merged from test_camera_access_grant_authorization_text.py ---
_HERE = Path(apex.__file__).resolve().parent / "habitat" / "doctype" / "camera_access_grant"
_GRANT_JSON = _HERE / "camera_access_grant.json"
_GRANT_PY = _HERE / "camera_access_grant.py"
_HOOKS_PY = _HERE.parents[2] / "hooks.py"
FIELDNAME = "approved_by"
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
