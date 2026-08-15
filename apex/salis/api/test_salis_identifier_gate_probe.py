# Copyright (c) 2026, AFMCO and contributors
"""A whitelisted Salis identifier must not clear its own existence gate.

Every gate here takes its identifier straight from a whitelisted endpoint and
probes it with ``frappe.db.exists``, which answers the value back WITHOUT querying
when it equals the DocType (database.py:1259). Passing the literal "Salis Vehicle" or
"Salis Driver" therefore cleared the gate. No permission check was skipped; what was
lost is the module's own named refusal, and each case asserts that refusal fires here
rather than a bare framework 404 landing downstream.

Site-free: only ``frappe.db.exists`` is exercised, so each module's ``frappe`` is
swapped for ``tests.factories.ExistsShortCircuitDB`` — the shared stub that
reproduces the short-circuit faithfully for every suite pinning this defect.
"""

import unittest
from unittest.mock import patch

from apex.salis.api import fleet_os, operations_control
from apex.tests.factories import ExistsShortCircuitDB

_SUPERVISOR = "supervisor@example.invalid"


def _endpoint(fn):
    """The whitelisted function past frappe's argument-type wrapper.

    ``frappe.whitelist`` wraps every endpoint in ``validate_argument_types``
    (frappe/__init__.py:852), whose condition reads ``frappe.local.flags`` — a
    request/test local these site-free cases do not build, and one that must not be
    assigned into because a process global does not roll back. The gate under test
    lives in the function body, which the wrapper only forwards to.
    """
    return getattr(fn, "__wrapped__", fn)


class _StubDB(ExistsShortCircuitDB):
    """Some of these gates read through ``get_value``. It answers from the same
    rows but carries NO short-circuit, because the real one does not either — only
    ``exists`` short-circuits (database.py:1259)."""

    def get_value(self, doctype, filters, fieldname=None, **_kwargs):
        self.queried.append((doctype, filters))
        rows = self.names(doctype)
        if isinstance(filters, dict):
            return next((v for v in filters.values() if v in rows), None)
        return filters if filters in rows else None


class _Thrown(Exception):
    """What the module's own ``frappe.throw`` refusal looks like to these cases."""


class _DoesNotExistError(Exception):
    pass


class _Session:
    user = _SUPERVISOR


class _StubFrappe:
    """Only what these guards touch before their refusal. Anything a guard reaches
    past its refusal raises, so a skipped gate fails loudly instead of silently."""

    DoesNotExistError = _DoesNotExistError

    def __init__(self, present=None):
        self.db = _StubDB(present)
        self.session = _Session()
        self.reached = []

    def throw(self, message, *_args, **_kwargs):
        raise _Thrown(message)

    def has_permission(self, doctype, ptype=None, doc=None, **_kwargs):
        self.reached.append(("has_permission", doctype, doc))
        return True

    def get_doc(self, *args, **_kwargs):
        self.reached.append(("get_doc", args))
        raise AssertionError(f"the guard let {args!r} through to get_doc")

    def get_all(self, *args, **_kwargs):
        self.reached.append(("get_all", args))
        raise AssertionError(f"the guard let {args!r} through to get_all")


class TestFleetOsPlateGate(unittest.TestCase):
    def test_a_plate_equal_to_its_doctype_is_refused_by_name(self):
        stub = _StubFrappe({"Salis Vehicle": set()})
        with patch.object(fleet_os, "frappe", stub), patch.object(
            fleet_os, "_", lambda text: text
        ):
            with self.assertRaises(_Thrown) as caught:
                fleet_os._resolve_plate("Salis Vehicle")
        self.assertIn("not found", str(caught.exception))
        self.assertEqual(stub.reached, [], "the refusal must land before has_permission")
        self.assertIn(
            ("Salis Vehicle", {"name": "Salis Vehicle"}),
            stub.db.queried,
            "the probe must reach the database, not short-circuit",
        )

    def test_a_vehicle_really_named_after_its_doctype_still_resolves(self):
        """The other direction: a bare ``name != doctype`` rejection would refuse a
        row that genuinely bears that name. The dict filter answers both ways."""
        stub = _StubFrappe({"Salis Vehicle": {"Salis Vehicle"}})
        with patch.object(fleet_os, "frappe", stub), patch.object(
            fleet_os, "_", lambda text: text
        ):
            self.assertEqual(fleet_os._resolve_plate("Salis Vehicle"), "Salis Vehicle")
        self.assertEqual(stub.reached[0][0], "has_permission")


class TestFleetOsDriverGate(unittest.TestCase):
    def _refuses(self, call):
        stub = _StubFrappe({"Salis Driver": set()})
        with patch.object(fleet_os, "frappe", stub), patch.object(
            fleet_os, "_", lambda text: text
        ), patch.object(fleet_os, "_resolve_plate", lambda plate, *a, **k: "VEH-0001"):
            with self.assertRaises(_Thrown) as caught:
                call()
        self.assertIn("not found", str(caught.exception))
        self.assertEqual(stub.reached, [], "the refusal must land before any load")
        self.assertIn(("Salis Driver", {"name": "Salis Driver"}), stub.db.queried)

    def test_reassign_refuses_a_driver_id_equal_to_its_doctype(self):
        self._refuses(lambda: _endpoint(fleet_os.reassign)("ABC-1234", "Salis Driver"))


class TestOperationsControlGates(unittest.TestCase):
    def test_the_timeline_refuses_a_vehicle_equal_to_its_doctype(self):
        """Administrator returns from ``has_permission`` without loading the document
        (permissions.py:107), so this gate — not the permission check — is what stood
        between the literal string and an empty feed returned as a success."""
        stub = _StubFrappe({"Salis Vehicle": set()})
        with patch.object(operations_control, "frappe", stub), patch.object(
            operations_control, "_", lambda text: text
        ):
            with self.assertRaises(_Thrown) as caught:
                _endpoint(operations_control.get_vehicle_timeline)("Salis Vehicle")
        self.assertIn("not found", str(caught.exception))
        self.assertNotIn("get_all", [entry[0] for entry in stub.reached])
        self.assertIn(("Salis Vehicle", {"name": "Salis Vehicle"}), stub.db.queried)

    def test_reassign_driver_refuses_a_driver_equal_to_its_doctype(self):
        stub = _StubFrappe({"Salis Driver": set()})
        calls = []
        with patch.object(operations_control, "frappe", stub), patch.object(
            operations_control, "_", lambda text: text
        ), patch.object(
            operations_control,
            "reassign_vehicle_driver",
            lambda *a, **k: calls.append(a),
        ):
            with self.assertRaises(_Thrown) as caught:
                _endpoint(operations_control.reassign_driver)("VEH-0001", "Salis Driver")
        self.assertIn("not found", str(caught.exception))
        self.assertEqual(calls, [], "the refusal must land before the reassignment")
        self.assertIn(("Salis Driver", {"name": "Salis Driver"}), stub.db.queried)


if __name__ == "__main__":
    unittest.main()
