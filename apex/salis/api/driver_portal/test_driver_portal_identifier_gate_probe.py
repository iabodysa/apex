# Copyright (c) 2026, AFMCO and contributors
"""A driver-portal identifier must not clear its own existence gate.

Both gates probe a value with ``frappe.db.exists``, which answers it back WITHOUT
querying when it equals the DocType (database.py:1259). Neither gate guards a
permission; both exist so an unknown value is dropped quietly:

* the support ticket's ``category`` / ``priority`` arrive from the caller, so the
  literal "Issue Type" / "Issue Priority" became a dangling link on insert and lost
  the driver's ticket instead of being dropped here — the reachable half;
* the profile's ``employee`` is read from the driver's own row, so the trap is
  latent today; the case pins the probe's own contract rather than a live path.

Site-free: only ``frappe.db.exists`` is exercised, so each module's ``frappe`` is
swapped for ``tests.factories.ExistsShortCircuitDB`` — the shared stub that
reproduces the short-circuit faithfully for every suite pinning this defect.
"""

import unittest
from unittest.mock import patch

from apex.salis.api.driver_portal import profile, support
from apex.tests.factories import ExistsShortCircuitDB


class _StubDB(ExistsShortCircuitDB):
    """Nothing on these paths reads a field, so ``get_value`` only has to be inert."""

    def get_value(self, doctype, filters, fieldname=None, **_kwargs):
        return None


class _StubUtils:
    @staticmethod
    def cstr(value):
        return "" if value is None else str(value)


class _TicketDoc:
    doctype = "Issue"
    name = "ISS-0001"

    def __init__(self, data):
        self.data = data

    def insert(self, **_kwargs):
        return self


class _StubFrappe:
    def __init__(self, present=None):
        self.db = _StubDB(present)
        self.utils = _StubUtils()
        self.cached = []
        self.inserted = []

    def throw(self, message, *_args, **_kwargs):
        raise AssertionError(f"unexpected refusal: {message}")

    def get_cached_doc(self, *args, **_kwargs):
        self.cached.append(args)
        raise AssertionError(f"the guard let {args!r} through to get_cached_doc")

    def get_doc(self, data):
        self.inserted.append(data)
        return _TicketDoc(data)


class TestSupportTicketCategoryAndPriorityGates(unittest.TestCase):
    """An unknown category or priority is designed to be dropped, so the harm here is
    a lost ticket, not a lost refusal: the short-circuit set a link Frappe cannot
    resolve and the insert failed."""

    def _raise_ticket(self, category, priority, present):
        stub = _StubFrappe(present)
        with patch.object(support, "frappe", stub), patch.object(
            support, "_", lambda text: text
        ), patch.object(
            support, "_driver_identity", lambda driver: "driver@driver.invalid"
        ), patch(
            "apex.salis.api.driver_portal.images.save_driver_image"
        ):
            support._create_support_ticket(
                "DRV-0001", category, priority, "Broken wiper", "It does not move."
            )
        return stub.inserted[0], stub

    def test_a_category_equal_to_its_doctype_is_dropped_not_linked(self):
        data, stub = self._raise_ticket(
            "Issue Type", "Low", {"Issue Priority": {"Low"}, "Issue Type": set()}
        )
        self.assertNotIn("issue_type", data, "an absent category must not become a link")
        self.assertEqual(data["priority"], "Low", "a real priority still applies")
        self.assertIn(("Issue Type", {"name": "Issue Type"}), stub.db.queried)

    def test_a_priority_equal_to_its_doctype_is_dropped_not_linked(self):
        data, stub = self._raise_ticket(
            "Bug", "Issue Priority", {"Issue Type": {"Bug"}, "Issue Priority": set()}
        )
        self.assertNotIn("priority", data, "an absent priority must not become a link")
        self.assertEqual(data["issue_type"], "Bug", "a real category still applies")
        self.assertIn(("Issue Priority", {"name": "Issue Priority"}), stub.db.queried)

    def test_rows_really_bearing_those_names_are_still_applied(self):
        """The other direction: a bare ``name != doctype`` rejection would drop a row
        that genuinely bears that name. The dict filter answers both ways."""
        data, _stub = self._raise_ticket(
            "Issue Type",
            "Issue Priority",
            {"Issue Type": {"Issue Type"}, "Issue Priority": {"Issue Priority"}},
        )
        self.assertEqual(data["issue_type"], "Issue Type")
        self.assertEqual(data["priority"], "Issue Priority")


class TestProfileEmployeeGate(unittest.TestCase):
    """Latent, not live: ``employee`` is read from the driver's own row and is a Link
    Frappe validates on save, so the literal string cannot arrive from a caller. The
    probe must still answer from the database rather than from its own argument."""

    def test_an_employee_equal_to_its_doctype_yields_no_documents(self):
        stub = _StubFrappe({"Employee": set()})
        with patch.object(profile, "frappe", stub):
            self.assertEqual(profile._employee_documents("Employee"), [])
        self.assertEqual(stub.cached, [], "an absent Employee must not be loaded")
        self.assertIn(("Employee", {"name": "Employee"}), stub.db.queried)


if __name__ == "__main__":
    unittest.main()
