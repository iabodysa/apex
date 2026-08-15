# Copyright (c) 2026, AFMCO and contributors
"""Dispatch Board API gate tests — P-042 (permission gate) + P-043 (PII gate).

The board is a read-only glance reader over the Salis fleet DocTypes. Two gates
are locked down here:

* P-042 — the entry point must gate on Dispatch Trip read, not only Salis
  Vehicle read; a caller who can read vehicles but not trips must get a
  PermissionError (the trips pane uses get_all, which skips row-level checks).
* P-043 — the driver phone is permlevel-1 PII. It must be fetched ONLY when the
  caller holds permlevel-1 read on Salis Driver. The fix gates at the QUERY (the
  fields list), never load-then-blank, so the PII never leaves the DB for an
  unauthorised role.

The gates are exercised with the dependencies patched at the dispatch_board
import site, so the assertions are deterministic and do not depend on seeded
fleet data (matching the test_enrich.py convention).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import frappe
from frappe.exceptions import PermissionError as FrappePermissionError
from frappe.tests.utils import FrappeTestCase

from apex.salis.api import dispatch_board

_MOD = "apex.salis.api.dispatch_board"


class TestDispatchBoardPermissionGate(FrappeTestCase):
    """P-042: Dispatch Trip read is gated, not only Salis Vehicle read."""

    def test_vehicle_read_without_trip_read_is_denied(self):
        def _fake_has_permission(doctype, ptype, throw=False):
            if doctype == "Dispatch Trip":
                if throw:
                    raise FrappePermissionError(doctype)
                return False
            return True

        with patch(f"{_MOD}.frappe.has_permission", side_effect=_fake_has_permission):
            with self.assertRaises(FrappePermissionError):
                dispatch_board.get_dispatch_board()

    def test_entry_point_gates_dispatch_trip_read(self):
        calls = []

        def _record(doctype, ptype, throw=False):
            calls.append((doctype, ptype, throw))
            return True

        with patch(f"{_MOD}.frappe.has_permission", side_effect=_record):
            with patch(f"{_MOD}._permitted_projects", return_value=(False, [])):
                dispatch_board.get_dispatch_board()

        self.assertIn(("Salis Vehicle", "read", True), calls)
        self.assertIn(("Dispatch Trip", "read", True), calls)


class TestDispatchBoardDriverPiiGate(FrappeTestCase):
    """P-043: driver phone is fetched only when the caller may read permlevel 1."""

    def _meta_with_permlevels(self, permlevels):
        meta = MagicMock()
        meta.get_permlevel_access.return_value = permlevels
        return meta

    def _spy_get_all(self, captured):
        """A get_all stand-in that records the fields requested per DocType and
        returns one driver row carrying a phone value (so a leak would show)."""

        def _impl(doctype, filters=None, fields=None, **kwargs):
            captured.setdefault(doctype, []).append(list(fields or []))
            if doctype == "Salis Driver":
                row = frappe._dict(
                    name="DRV-1",
                    full_name="Sara Driver",
                    status="Active",
                    project=None,
                    current_vehicle=None,
                )
                if fields and "phone" in fields:
                    row["phone"] = "0500000000"
                return [row]
            return []

        return _impl

    def test_phone_not_queried_for_unprivileged_caller(self):
        captured: dict = {}
        with patch(
            f"{_MOD}.frappe.get_meta",
            return_value=self._meta_with_permlevels([0]),
        ):
            with patch(f"{_MOD}.frappe.get_all", side_effect=self._spy_get_all(captured)):
                pane = dispatch_board._drivers_pane(unscoped=True, projects=None)

        driver_fields = captured["Salis Driver"][0]
        self.assertNotIn(
            "phone", driver_fields, "phone must not be in the query for an unprivileged caller"
        )
        self.assertEqual(pane["available"][0]["phone"], "")

    def test_phone_queried_for_privileged_caller(self):
        captured: dict = {}
        with patch(
            f"{_MOD}.frappe.get_meta",
            return_value=self._meta_with_permlevels([0, 1]),
        ):
            with patch(f"{_MOD}.frappe.get_all", side_effect=self._spy_get_all(captured)):
                pane = dispatch_board._drivers_pane(unscoped=True, projects=None)

        driver_fields = captured["Salis Driver"][0]
        self.assertIn("phone", driver_fields)
        self.assertEqual(pane["available"][0]["phone"], "0500000000")
