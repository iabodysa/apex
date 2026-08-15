# Copyright (c) 2026, AFMCO and contributors
"""``profile._employee_documents`` must answer from the database, not from its argument.

``frappe.db.exists`` answers a value back WITHOUT querying when it equals the DocType
name (database.py:1259), so ``exists("Employee", "Employee")`` is truthy for a site with
no such record. The gate at ``profile.py:28`` therefore probes with the dict filter
``{"name": employee}``, which has no short-circuit.

Latent rather than live: ``employee`` is read off the driver's own row and is a Link
Frappe validates on save, so the literal string cannot arrive from a caller today. The
case pins the probe's own contract so a later refactor that reaches for the positional
form is caught here rather than by an absent profile.

Site-free: only ``frappe.db.exists`` is exercised, so the module's ``frappe`` is swapped
for ``tests.factories.ExistsShortCircuitDB`` — the shared stub that reproduces the
short-circuit faithfully.
"""

import unittest
from unittest.mock import patch

from apex.salis.api.driver_portal import profile
from apex.tests.factories import ExistsShortCircuitDB


class _StubDB(ExistsShortCircuitDB):
    """Nothing on this path reads a field, so ``get_value`` only has to be inert."""

    def get_value(self, doctype, filters, fieldname=None, **_kwargs):
        return None


class _StubFrappe:
    def __init__(self, present=None):
        self.db = _StubDB(present)
        self.cached = []

    def get_cached_doc(self, *args, **_kwargs):
        self.cached.append(args)
        raise AssertionError(f"the guard let {args!r} through to get_cached_doc")


class TestProfileEmployeeGate(unittest.TestCase):
    def test_an_employee_equal_to_its_doctype_yields_no_documents(self):
        stub = _StubFrappe({"Employee": set()})
        with patch.object(profile, "frappe", stub):
            self.assertEqual(profile._employee_documents("Employee"), [])
        self.assertEqual(stub.cached, [], "an absent Employee must not be loaded")
        self.assertIn(("Employee", {"name": "Employee"}), stub.db.queried)

    def test_a_blank_employee_is_dropped_before_any_query(self):
        stub = _StubFrappe({"Employee": set()})
        with patch.object(profile, "frappe", stub):
            self.assertEqual(profile._employee_documents(None), [])
        self.assertEqual(stub.db.queried, [], "a blank employee must not be probed at all")


if __name__ == "__main__":
    unittest.main()
