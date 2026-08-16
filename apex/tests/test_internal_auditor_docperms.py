# Copyright (c) 2026, AFMCO and contributors
"""Structural test: Internal Auditor read+report-only DocPerms across the
custody/asset/movement/ledger set.

Pure JSON read — no Frappe site required.  Verifies for each target DocType:
  1. Exactly one permission row for "Internal Auditor" exists.
  2. The row has read=1 and report=1.
  3. The row has NO write, create, delete, submit, cancel, or amend flags.
  4. No pre-existing rows for other roles were removed (regression guard).

Special case — accommodation_ledger:
  The Internal Auditor row pre-existed with read=1; this task adds report=1.
  The test verifies the row was edited in-place (still one row, not two).

Writer-ownership note for cleaning_log:
  T8 owns the Internal Auditor row; T6 owns the Cleaning Supervisor row.
  Both rows coexist in the file; this test guards only the auditor row.
"""

import json
import pathlib
import unittest

import apex

_BASE = pathlib.Path(apex.__file__).resolve().parent / "habitat" / "doctype"

_TARGET_DOCTYPES = {
    "custody_issue": ["System Manager", "Accommodation Manager", "Resident Supervisor"],
    "custody_return": ["System Manager", "Accommodation Manager", "Resident Supervisor"],
    "custody_damage_assessment": ["System Manager", "Accommodation Manager", "Resident Supervisor"],
    "facility_asset": ["System Manager", "Accommodation Manager", "Resident Supervisor"],
    "facility_asset_movement": ["System Manager", "Accommodation Manager", "Resident Supervisor"],
    "facility_asset_custody_assignment": ["System Manager", "Accommodation Manager", "Resident Supervisor"],
    "utility_bill_entry": ["System Manager", "Accommodation Manager", "Finance Manager"],
    "lease": ["System Manager", "Accommodation Manager", "Finance Manager"],
    "accommodation_ledger": ["System Manager", "Finance Manager"],
    "cleaning_log": ["System Manager", "Accommodation Manager", "Resident Supervisor", "Cleaning Supervisor"],
}

ROLE = "Internal Auditor"
_WRITE_FLAGS = ("write", "create", "delete", "submit", "cancel", "amend")


def _load_perms(folder: str):
    path = _BASE / folder / f"{folder}.json"
    with path.open() as fh:
        data = json.load(fh)
    return data["permissions"]


def _auditor_rows(perms):
    return [p for p in perms if p.get("role") == ROLE]


class TestInternalAuditorDocPerms(unittest.TestCase):
    """JSON-level assertions for Internal Auditor permission rows."""

    def _check_doctype(self, folder: str, pre_existing_roles: list):
        perms = _load_perms(folder)
        rows = _auditor_rows(perms)

        self.assertEqual(
            len(rows),
            1,
            f"{folder}: expected exactly 1 Internal Auditor row, got {len(rows)}",
        )
        row = rows[0]

        self.assertEqual(row.get("read"), 1, f"{folder}: Internal Auditor must have read=1")
        self.assertEqual(row.get("report"), 1, f"{folder}: Internal Auditor must have report=1")

        for flag in _WRITE_FLAGS:
            self.assertNotEqual(
                row.get(flag),
                1,
                f"{folder}: Internal Auditor must NOT have {flag}=1",
            )

        existing_roles = {p.get("role") for p in perms}
        for role in pre_existing_roles:
            self.assertIn(
                role,
                existing_roles,
                f"{folder}: pre-existing role {role!r} was removed",
            )


    def test_custody_issue(self):
        self._check_doctype("custody_issue", _TARGET_DOCTYPES["custody_issue"])

    def test_custody_return(self):
        self._check_doctype("custody_return", _TARGET_DOCTYPES["custody_return"])

    def test_custody_damage_assessment(self):
        self._check_doctype("custody_damage_assessment", _TARGET_DOCTYPES["custody_damage_assessment"])

    def test_facility_asset(self):
        self._check_doctype("facility_asset", _TARGET_DOCTYPES["facility_asset"])

    def test_facility_asset_movement(self):
        self._check_doctype("facility_asset_movement", _TARGET_DOCTYPES["facility_asset_movement"])

    def test_facility_asset_custody_assignment(self):
        self._check_doctype(
            "facility_asset_custody_assignment",
            _TARGET_DOCTYPES["facility_asset_custody_assignment"],
        )

    def test_utility_bill_entry(self):
        self._check_doctype("utility_bill_entry", _TARGET_DOCTYPES["utility_bill_entry"])

    def test_accommodation_lease(self):
        self._check_doctype("lease", _TARGET_DOCTYPES["lease"])

    def test_accommodation_ledger_edited_not_duplicated(self):
        """Existing Internal Auditor row was edited in-place; must not be duplicated."""
        self._check_doctype("accommodation_ledger", _TARGET_DOCTYPES["accommodation_ledger"])

    def test_cleaning_log_auditor_row_coexists_with_cleaning_supervisor(self):
        """T8 owns auditor row; T6's Cleaning Supervisor row must still be present."""
        perms = _load_perms("cleaning_log")

        rows = _auditor_rows(perms)
        self.assertEqual(len(rows), 1, "cleaning_log: expected exactly 1 Internal Auditor row")
        row = rows[0]
        self.assertEqual(row.get("read"), 1)
        self.assertEqual(row.get("report"), 1)
        for flag in _WRITE_FLAGS:
            self.assertNotEqual(row.get(flag), 1, f"cleaning_log: auditor must NOT have {flag}=1")

        cs_rows = [p for p in perms if p.get("role") == "Cleaning Supervisor"]
        self.assertEqual(len(cs_rows), 1, "cleaning_log: Cleaning Supervisor row must remain")
        cs = cs_rows[0]
        self.assertEqual(cs.get("read"), 1)
        self.assertEqual(cs.get("write"), 1)
        self.assertEqual(cs.get("create"), 1)


if __name__ == "__main__":
    unittest.main()
