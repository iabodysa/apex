# Copyright (c) 2026, AFMCO and contributors
"""Transport Request's `mobile_number` had a writer for the junior roles only.

`mobile_number` is the one permlevel-1 field on Transport Request. Fleet Project Manager
and Fleet Supervisor already shipped a permlevel-1 row carrying `read` + `write`; Fleet
Manager and System Manager — the two roles that own the DocType at level 0, including
delete and cancel — shipped a level-1 row with `read` only. The senior roles could
therefore not write a column the junior roles could. `write: 1` was added to those two
rows; nothing at permlevel 0 moved and no role gained a level-1 row.

WHY THE FIELD WAS ARRIVING EMPTY, NOT MERELY UNEDITABLE
--------------------------------------------------------
`mobile_number` is `fetch_from: requested_by.mobile_no` with `fetch_if_empty`. The fetch
runs inside `_validate_links` (frappe/model/document.py:302, the fetch itself at
base_document.py:849-851) and `validate_higher_perm_levels` runs AFTER it, at :306. On a
create the replacement value comes from `frappe.new_doc` (base_document.py:1276-1278), so
the freshly fetched number was fetched and then blanked in the same insert. That is why
the proof below asserts the field is POPULATED after a Fleet Manager insert rather than
merely that an edit stuck.

A level violation reverts, it never raises — never assert `assertRaises` here.

Run under bench:
  bench --site <site> run-tests --module apex.salis.doctype.transport_request.test_transport_request_pii_permlevel
"""

from __future__ import annotations

import json
from pathlib import Path

import frappe
from frappe.tests.utils import FrappeTestCase

import apex
from apex.salis.doctype.transport_request.transport_request import (
    SERVICE_LINE_REQUEST_TYPE,
    WORKER_MANIFEST_SERVICE_LINES,
)

_REQUEST_JSON = Path(apex.__file__).resolve().parent / "salis" / "doctype" / "transport_request" / "transport_request.json"

FLEET_MANAGER = "Fleet Manager"
# Read + report at level 0, no write anywhere, and in salis/permissions.py UNSCOPED_ROLES —
# so it reaches every row and any refusal it hits is a FIELD verdict, not a row filter.
INTERNAL_AUDITOR = "Internal Auditor"

# Both halves of the pair must be stated: validate (transport_request.py:81-91) throws when
# they disagree, and request_type declares no `default`, so naming only the transport type
# leaves Frappe seeding the other half with the Select's FIRST option, which contradicts it.
# The manifest-free type (transport_request.py:42) needs no Building, Project or worker rows,
# so it is the lightest valid document. Derived from the controller's own constants, and
# asserted single below so a third manifest-free type is reported, not silently picked.
_MANIFEST_FREE_SERVICE_LINES = sorted(
    set(SERVICE_LINE_REQUEST_TYPE) - set(WORKER_MANIFEST_SERVICE_LINES)
)
FIXTURE_SERVICE_LINE = _MANIFEST_FREE_SERVICE_LINES[0]
FIXTURE_REQUEST_TYPE = SERVICE_LINE_REQUEST_TYPE[FIXTURE_SERVICE_LINE]


class TestTransportRequestPiiPermlevel(FrappeTestCase):
    """Site-bound. Fixtures are minted per METHOD: rollback covers rows only."""

    def setUp(self):
        # frappe.session.user is process state — no rollback restores it.
        self.addCleanup(frappe.set_user, "Administrator")
        frappe.set_user("Administrator")

    def _user_with_role(self, role, mobile=None):
        """A fresh System User holding exactly one apex role.

        Exactly one, because a fixture user that had picked up a second role would grant
        the level-1 access this proof believes it withheld. `mobile_no` is set when the
        user is going to be the `requested_by` link the fetch reads through.
        """
        return (
            frappe.get_doc(
                {
                    "doctype": "User",
                    "email": f"s005tr_{frappe.generate_hash(length=12)}@example.com",
                    "first_name": role.split()[0],
                    "send_welcome_email": 0,
                    "mobile_no": mobile,
                    "roles": [{"role": role}],
                }
            )
            .insert(ignore_permissions=True)
            .name
        )

    def _request(self, requester):
        """Insert the lightest valid Transport Request AS THE CALLING USER.

        Deliberately not `ignore_permissions`: the whole point is that the insert runs
        under the acting user's DocPerms, because `validate_higher_perm_levels` returns
        early on that flag (document.py:785) and an ignored insert would prove nothing
        about permlevels. `destination` is what the derived request type's validate branch
        requires (transport_request.py:117-119).
        """
        return frappe.get_doc(
            {
                "doctype": "Transport Request",
                "requested_by": requester,
                "service_line": FIXTURE_SERVICE_LINE,
                "request_type": FIXTURE_REQUEST_TYPE,
                "destination": "S005 Destination",
            }
        ).insert()

    def test_the_fixture_pair_is_the_one_the_controller_declares(self):
        """Non-vacuity for the fixture itself.

        The derivation must yield exactly ONE candidate, and both halves must be live
        options on the shipped Selects — otherwise the two proofs below would die on a
        fixture error and report it as a permlevel failure, which is how this file failed
        the first time it ran.
        """
        self.assertEqual(
            len(_MANIFEST_FREE_SERVICE_LINES),
            1,
            "more than one transport type now carries no worker manifest — pick the "
            f"fixture pair deliberately instead of taking the first: {_MANIFEST_FREE_SERVICE_LINES}",
        )
        shipped = json.loads(_REQUEST_JSON.read_text(encoding="utf-8"))
        for fieldname, expected in (
            ("service_line", FIXTURE_SERVICE_LINE),
            ("request_type", FIXTURE_REQUEST_TYPE),
        ):
            with self.subTest(field=fieldname):
                field = next(f for f in shipped["fields"] if f["fieldname"] == fieldname)
                options = [o for o in (field.get("options") or "").split("\n") if o.strip()]
                self.assertIn(
                    expected,
                    options,
                    f"the controller pairs {fieldname} to {expected!r}, which is not a "
                    "shipped Select option — controller and JSON have drifted",
                )
                self.assertIsNone(
                    field.get("default"),
                    f"{fieldname} gained a default; re-check that it agrees with its pair, "
                    "because a reqd Select with no default silently takes its FIRST option",
                )

    def test_a_fleet_manager_insert_keeps_the_fetched_mobile_number(self):
        """The card's create-path proof: `requested_by` populated, `mobile_number` non-empty
        after insert. Before the write flag it was fetched at document.py:302 and blanked at
        :306, so the request reached dispatch with no way to phone the requester."""
        manager = self._user_with_role(FLEET_MANAGER, mobile="0533221100")
        frappe.set_user(manager)
        doc = self._request(manager)

        stored = frappe.db.get_value("Transport Request", doc.name, "mobile_number")
        self.assertTrue(
            stored,
            f"mobile_number was blanked on insert — {FLEET_MANAGER} cannot write permlevel 1, "
            "so the fetched value was reset to the new-doc default",
        )
        self.assertEqual(stored, "0533221100", "the fetched number was replaced, not kept")

    def test_the_manager_reaches_level_one_and_the_auditor_does_not(self):
        """The counter-case. Without it the method above would pass just as happily on a
        build where permlevel enforcement had been switched off entirely."""
        manager = self._user_with_role(FLEET_MANAGER, mobile="0544332211")
        auditor = self._user_with_role(INTERNAL_AUDITOR)

        frappe.set_user(manager)
        doc = self._request(manager)
        self.assertIn(
            1,
            frappe.get_doc("Transport Request", doc.name).get_permlevel_access("write"),
            f"{FLEET_MANAGER} holds no permlevel-1 write row on Transport Request",
        )

        frappe.set_user(auditor)
        self.assertNotIn(
            1,
            frappe.get_doc("Transport Request", doc.name).get_permlevel_access("write"),
            f"{INTERNAL_AUDITOR} must not reach permlevel 1",
        )

    def test_the_level_one_field_set_is_still_the_one_this_proves(self):
        """Non-vacuity: if `mobile_number` left permlevel 1 the methods above would pass
        while proving nothing."""
        shipped = json.loads(_REQUEST_JSON.read_text(encoding="utf-8"))
        elevated = {
            f["fieldname"] for f in shipped["fields"] if int(f.get("permlevel") or 0) == 1
        }
        self.assertEqual(
            elevated,
            {"mobile_number"},
            "the permlevel-1 field set on Transport Request changed — re-derive this proof",
        )

    def test_all_four_level_one_rows_now_carry_the_write(self):
        """The senior/junior inversion this fix closed, read off the shipped JSON.

        The pair (role, permlevel) is the identity — `is_perm_applicable` keeps only
        permlevel-0 rows (frappe/permissions.py:284) — so a level-1 row coexists with the
        level-0 row for the same role by design, and deduplicating on role alone would
        strip the field access.
        """
        shipped = json.loads(_REQUEST_JSON.read_text(encoding="utf-8"))
        rows = shipped["permissions"]
        high = [p for p in rows if int(p.get("permlevel") or 0) == 1]
        self.assertEqual(
            {p["role"] for p in high},
            {FLEET_MANAGER, "System Manager", "Fleet Project Manager", "Fleet Supervisor"},
            "the permlevel-1 role set changed — this fix was supposed to add a flag to two "
            "existing rows, not widen who reaches the number",
        )
        for row in high:
            with self.subTest(role=row["role"]):
                self.assertEqual(row.get("read"), 1, f"{row['role']}: level-1 read missing")
                self.assertEqual(row.get("write"), 1, f"{row['role']}: level-1 write missing")

        # The explicit non-change: the auditor stays read-only, at level 0 only.
        auditor = [p for p in rows if p["role"] == INTERNAL_AUDITOR]
        self.assertEqual(len(auditor), 1, "Internal Auditor must keep exactly one row")
        self.assertEqual(int(auditor[0].get("permlevel") or 0), 0)
        for flag in ("write", "create", "delete", "submit", "cancel", "amend"):
            self.assertNotEqual(
                auditor[0].get(flag), 1, f"Internal Auditor gained {flag} as collateral damage"
            )
