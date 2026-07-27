# Copyright (c) 2026, AFMCO and contributors
"""A whitelisted Salis identifier must not clear its own existence gate.

Every gate here takes its identifier straight from a whitelisted endpoint and
probes it with ``frappe.db.exists``, which answers the value back WITHOUT querying
when it equals the DocType (database.py:1259). Passing the literal "Salis Vehicle",
"Salis Driver" or "Route Plan" therefore cleared the gate. No permission check was
skipped; what was lost is the module's own named refusal, and each case asserts
that refusal fires here rather than a bare framework 404 landing downstream.

The checklist-template case runs the other way: an unknown template is meant to be
ignored, so the short-circuit turned a silent drop into a dangling load. That case
asserts the drop, not a refusal.

Site-free: only ``frappe.db.exists`` is exercised, so each module's ``frappe`` is
swapped for a stub that reproduces the short-circuit faithfully.
"""

import unittest
from unittest.mock import patch

from apex.salis.api import fleet_os, operations_control, route_supervisor

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


class _StubDB:
    """``frappe.db``, faithful to database.py:1259 on the positional call shape."""

    def __init__(self, present=None):
        self.present = present or {}
        self.queried = []

    def exists(self, doctype, key=None, **_kwargs):
        if isinstance(key, str) and key == doctype and doctype != "DocType":
            return key
        self.queried.append((doctype, key))
        rows = self.present.get(doctype, set())
        if isinstance(key, dict):
            return next((v for v in key.values() if v in rows), None)
        return key if key in rows else None

    def get_value(self, doctype, filters, fieldname=None, **_kwargs):
        self.queried.append((doctype, filters))
        rows = self.present.get(doctype, set())
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

    def test_create_handover_refuses_a_driver_id_equal_to_its_doctype(self):
        self._refuses(
            lambda: _endpoint(fleet_os.create_handover)("ABC-1234", "Salis Driver")
        )


class _HandoverDoc:
    """The just-inserted Vehicle Handover, only as much as the endpoint uses."""

    doctype = "Vehicle Handover"
    name = "VH-0001"

    def insert(self):
        return self


class _PriorAssignment:
    """``frappe.get_all`` returns attribute-addressable rows; the endpoint uses one."""

    driver = "DRV-0002"


class TestFleetOsChecklistTemplateGate(unittest.TestCase):
    """An unknown template is designed to be ignored, so this gate's harm is the
    reverse: the short-circuit sent the literal DocType on to the loader, which
    hard-failed a handover that should simply have carried no checklist."""

    def _create_handover(self, template, present):
        stub = _StubFrappe(present)
        stub.get_doc = lambda *a, **k: _HandoverDoc()
        stub.get_all = lambda *a, **k: [_PriorAssignment()]
        with patch.object(fleet_os, "frappe", stub), patch.object(
            fleet_os, "_", lambda text: text
        ), patch.object(
            fleet_os, "_resolve_plate", lambda plate, *a, **k: "VEH-0001"
        ), patch.object(
            fleet_os, "getdate", lambda value=None: value
        ), patch.object(
            fleet_os, "today", lambda: "2026-07-27"
        ), patch(
            "apex.salis.doctype.vehicle_handover_checklist_template"
            ".vehicle_handover_checklist_template.load_template_into_doc"
        ) as loader:
            result = _endpoint(fleet_os.create_handover)(
                "ABC-1234", "DRV-0001", checklist_template=template
            )
        return result, loader, stub

    def test_an_absent_template_named_after_its_doctype_is_dropped(self):
        result, loader, stub = self._create_handover(
            "Vehicle Handover Checklist Template",
            {"Salis Driver": {"DRV-0001"}, "Vehicle Handover Checklist Template": set()},
        )
        self.assertEqual(result["handover"], "VH-0001")
        loader.assert_not_called()
        self.assertIn(
            (
                "Vehicle Handover Checklist Template",
                {"name": "Vehicle Handover Checklist Template"},
            ),
            stub.db.queried,
        )

    def test_a_template_really_bearing_that_name_is_still_loaded(self):
        _result, loader, _stub = self._create_handover(
            "Vehicle Handover Checklist Template",
            {
                "Salis Driver": {"DRV-0001"},
                "Vehicle Handover Checklist Template": {
                    "Vehicle Handover Checklist Template"
                },
            },
        )
        loader.assert_called_once_with("VH-0001", "Vehicle Handover Checklist Template")


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


class TestRouteSupervisorPlanGate(unittest.TestCase):
    def test_a_plan_name_equal_to_its_doctype_is_refused_as_missing(self):
        """Not merely "refused": the fall-through reported the wrong reason. A
        non-supervisor got an ownership error for a plan that does not exist, and an
        admin got a bare 404 from ``get_doc`` instead of this named refusal."""
        stub = _StubFrappe({"Route Plan": set()})
        with patch.object(route_supervisor, "frappe", stub), patch.object(
            route_supervisor, "_", lambda text: text
        ):
            with self.assertRaises(_Thrown) as caught:
                route_supervisor._resolve_owned_plan_doc("Route Plan")
        self.assertIn("not found", str(caught.exception))
        self.assertEqual(stub.reached, [], "the refusal must land before get_doc")
        self.assertIn(("Route Plan", {"name": "Route Plan"}), stub.db.queried)


if __name__ == "__main__":
    unittest.main()
