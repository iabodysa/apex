# Copyright (c) 2026, AFMCO and contributors
"""Structural test: Resident Request Coordinator DocPerms on Accommodation
Resident Request (permlevel-0 + permlevel-1 parity).

Pure JSON read — no Frappe site required.  Verifies that:
  1. A permlevel-0 row exists for the role with read/write/create=1 and NO delete/submit.
  2. A permlevel-1 row exists for the role with read/write=1.
  3. Existing rows for System Manager, Accommodation Manager, and Resident Supervisor
     at both perm levels are untouched (still present and correct).
"""

import json
import pathlib
import unittest

_DOCTYPE_JSON = (
    pathlib.Path(__file__).parents[2]
    / "apex"
    / "habitat"
    / "doctype"
    / "resident_request"
    / "resident_request.json"
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

    # [#e7jvoz]

    def test_permlevel0_row_present(self):
        rows = _rows_for(self.perms, ROLE, 0)
        self.assertEqual(len(rows), 1, f"Expected exactly one permlevel-0 row for {ROLE!r}")

    def test_permlevel0_has_read_write_create(self):
        row = _rows_for(self.perms, ROLE, 0)[0]
        self.assertEqual(row.get("read"), 1)
        self.assertEqual(row.get("write"), 1)
        self.assertEqual(row.get("create"), 1)

    def test_permlevel0_no_delete(self):
        row = _rows_for(self.perms, ROLE, 0)[0]
        self.assertNotEqual(row.get("delete"), 1, "Coordinator must NOT have delete")

    def test_permlevel0_no_submit(self):
        row = _rows_for(self.perms, ROLE, 0)[0]
        self.assertNotEqual(row.get("submit"), 1, "DocType is not submittable; no submit perm")

    def test_permlevel1_row_present(self):
        rows = _rows_for(self.perms, ROLE, 1)
        self.assertEqual(len(rows), 1, f"Expected exactly one permlevel-1 row for {ROLE!r}")

    def test_permlevel1_has_read_write(self):
        row = _rows_for(self.perms, ROLE, 1)[0]
        self.assertEqual(row.get("read"), 1)
        self.assertEqual(row.get("write"), 1)

    # [#2acwh6]

    def test_existing_permlevel0_roles_still_present(self):
        for role in ("System Manager", "Accommodation Manager", "Resident Supervisor"):
            rows = _rows_for(self.perms, role, 0)
            self.assertEqual(len(rows), 1, f"Existing permlevel-0 row gone for {role!r}")

    def test_existing_permlevel1_roles_still_present(self):
        for role in ("System Manager", "Accommodation Manager", "Resident Supervisor"):
            rows = _rows_for(self.perms, role, 1)
            self.assertEqual(len(rows), 1, f"Existing permlevel-1 row gone for {role!r}")

    def test_system_manager_still_has_delete(self):
        row = _rows_for(self.perms, "System Manager", 0)[0]
        self.assertEqual(row.get("delete"), 1, "System Manager permlevel-0 delete must remain")

    def test_total_perm_rows(self):
        # [#lkfoj9]
        self.assertEqual(len(self.perms), 8)


if __name__ == "__main__":
    unittest.main()
