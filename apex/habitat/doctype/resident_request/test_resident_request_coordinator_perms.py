# Copyright (c) 2026, AFMCO and contributors
"""Structural test: Resident Request Coordinator DocPerms on Resident Request
(permlevel-0 + permlevel-1 parity).

Pure JSON read — no Frappe site required.  Verifies that:
  1. A permlevel-0 row exists for the role with read/write/create=1 and NO delete/submit.
  2. A permlevel-1 row exists for the role with read/write=1.
  3. Existing rows for System Manager, Accommodation Manager, and Resident Supervisor
     at both perm levels are untouched (still present and correct).
"""

import json
import pathlib
import unittest

import apex

# Resolved from the INSTALLED package: this test's own directory holds only the test, so a
# sibling read raised and every assertion below was unreachable.
_DOCTYPE_JSON = (
    pathlib.Path(apex.__file__).resolve().parent
    / "habitat/doctype/resident_request/resident_request.json"
)

ROLE = "Resident Request Coordinator"


def _load_perms():
    with _DOCTYPE_JSON.open() as fh:
        data = json.load(fh)
    return data["permissions"]


def _rows_for(perms, role, permlevel=0):
    return [p for p in perms if p.get("role") == role and p.get("permlevel", 0) == permlevel]


class TestResidentRequestCoordinatorPerms(unittest.TestCase):
    """JSON-level assertions for the Resident Request Coordinator permission rows."""

    def setUp(self):
        self.perms = _load_perms()


    def test_permlevel0_row_shape(self):
        """The Coordinator's permlevel-0 row: present, and shaped for triage work
        without record-destroying power — read/write/create but no delete, no submit
        (the DocType is not submittable to begin with)."""
        rows = _rows_for(self.perms, ROLE, 0)
        self.assertEqual(len(rows), 1, f"Expected exactly one permlevel-0 row for {ROLE!r}")
        row = rows[0]
        self.assertEqual(row.get("read"), 1, "permlevel-0 must grant read")
        self.assertEqual(row.get("write"), 1, "permlevel-0 must grant write")
        self.assertEqual(row.get("create"), 1, "permlevel-0 must grant create")
        self.assertNotEqual(row.get("delete"), 1, "Coordinator must NOT have delete")
        self.assertNotEqual(row.get("submit"), 1, "DocType is not submittable; no submit perm")

    def test_permlevel1_row_shape(self):
        """The Coordinator's permlevel-1 row: present, with read/write on the
        confidential fields that permlevel gates."""
        rows = _rows_for(self.perms, ROLE, 1)
        self.assertEqual(len(rows), 1, f"Expected exactly one permlevel-1 row for {ROLE!r}")
        row = rows[0]
        self.assertEqual(row.get("read"), 1, "permlevel-1 must grant read")
        self.assertEqual(row.get("write"), 1, "permlevel-1 must grant write")

    def test_existing_roles_are_untouched(self):
        """Adding the Coordinator's rows must not disturb what System Manager,
        Accommodation Manager and Resident Supervisor already had at either
        permlevel — including System Manager's delete, the one privileged bit most
        at risk of being silently dropped by a careless permission-block edit."""
        for role in ("System Manager", "Accommodation Manager", "Resident Supervisor"):
            rows0 = _rows_for(self.perms, role, 0)
            self.assertEqual(len(rows0), 1, f"Existing permlevel-0 row gone for {role!r}")
            rows1 = _rows_for(self.perms, role, 1)
            self.assertEqual(len(rows1), 1, f"Existing permlevel-1 row gone for {role!r}")
        system_manager_row = _rows_for(self.perms, "System Manager", 0)[0]
        self.assertEqual(
            system_manager_row.get("delete"), 1,
            "System Manager permlevel-0 delete must remain",
        )

    def test_the_permission_table_holds_exactly_these_rows(self):
        """A bare row COUNT says nothing about which row appeared. The pair is the key,
        because a permlevel-1 row is field access and a permlevel-0 row is the record.

        ``Worker`` holds the portal intake row: a resident raises their own request
        through the web form, so the role that owns the DocType's create path is part of
        the shape this guards, not noise beside it.
        """
        self.assertEqual(
            sorted((p["role"], int(p.get("permlevel", 0) or 0)) for p in self.perms),
            [
                ("Accommodation Manager", 0),
                ("Accommodation Manager", 1),
                ("Resident Request Coordinator", 0),
                ("Resident Request Coordinator", 1),
                ("Resident Supervisor", 0),
                ("Resident Supervisor", 1),
                ("System Manager", 0),
                ("System Manager", 1),
                ("Worker", 0),
            ],
        )


if __name__ == "__main__":
    unittest.main()
