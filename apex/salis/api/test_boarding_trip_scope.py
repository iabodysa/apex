# Copyright (c) 2026, AFMCO and contributors
"""``_resolve_trip`` asks the Dispatch Trip document gate before it hands a trip over.

``STAFF_ROLES`` is a bare role-set intersection, and two of its members — Fleet Project
Manager and Fleet Supervisor — are absent from ``permissions.UNSCOPED_ROLES``: they are
exactly the scoped roles the Dispatch Trip row-scope exists for. Holding one says the
actor may act on THEIR project's trips, and the staff branch used to read the row by name
with no project predicate at all, so eight whitelisted boarding endpoints handed another
project's manifest, boarding pass and boarding writes to whoever named the trip.

The row read cannot make that distinction and no registered hook rescues it:
``frappe.db.get_value`` runs no permission layer, so neither the
``permission_query_conditions`` fragment nor the ``has_permission`` hook that hooks.py
registers for Dispatch Trip is consulted. The staff branch therefore asks the document
gate explicitly. What that gate then decides — assigned driver, named route supervisor,
in-project, out-of-project — is already pinned by test_dispatch_trip_driver_scope and
test_salis_tenant_scope, and is deliberately not re-asserted here; these cases pin that
the gate is REACHED, with the right document and the right right.

The behavioural half stubs the module's ``frappe`` handle, so no site and no rows. The
structural half reads the shipped source, because a caller that asks for "read" before a
write is a hole no output equality can see.
"""

from __future__ import annotations

import unittest
from unittest import mock

from apex.salis.api import boarding, boarding_flow, manual_boarding
from apex.tests.source_tree import func_source

TRIP = "DT-0001"
OWN_DRIVER = "DRV-1"
TRIP_ROW = {
    "name": TRIP,
    "driver": "DRV-9",
    "transport_request": "TR-1",
    "trip_date": "2026-08-16",
}


class _Refused(Exception):
    """Stands in for frappe.PermissionError under the stubbed frappe handle."""


def _resolve(*, staff, credential=None, session_driver=None, ptype=None, refuse=False):
    """Drive ``_resolve_trip`` with every collaborator stubbed, and report the calls."""
    mock_frappe = mock.MagicMock()
    mock_frappe.db.get_value.return_value = dict(TRIP_ROW)
    mock_frappe.throw.side_effect = _Refused
    mock_frappe.PermissionError = _Refused
    mock_frappe.DoesNotExistError = _Refused
    if refuse:
        mock_frappe.has_permission.side_effect = _Refused

    with mock.patch.object(boarding, "frappe", mock_frappe), mock.patch.object(
        boarding, "_presented_driver", return_value=credential
    ), mock.patch.object(boarding, "_is_staff", return_value=staff), mock.patch.object(
        boarding, "_driver_for_user", return_value=session_driver
    ):
        args = (TRIP,) if ptype is None else (TRIP, ptype)
        trip = boarding._resolve_trip(*args)
    return trip, mock_frappe


class TestStaffTripAccessIsAskedOfTheDocumentGate(unittest.TestCase):
    def test_the_staff_path_asks_the_document_gate_for_this_very_trip(self):
        _trip, frappe_mock = _resolve(staff=True)

        frappe_mock.has_permission.assert_called_once_with(
            "Dispatch Trip", "read", doc=TRIP, throw=True
        )

    def test_a_refusal_from_the_gate_is_not_swallowed(self):
        """A gate whose verdict the caller discards is not a gate."""
        with self.assertRaises(_Refused):
            _resolve(staff=True, refuse=True)

    def test_the_right_asked_for_is_the_one_the_caller_passes(self):
        _trip, frappe_mock = _resolve(staff=True, ptype="write")

        self.assertEqual(
            ("Dispatch Trip", "write"), frappe_mock.has_permission.call_args.args
        )

    def test_the_row_read_alone_never_constrained_the_staff_path(self):
        """The read the gate had to be added beside: a bare name, no project predicate."""
        _trip, frappe_mock = _resolve(staff=True)

        self.assertEqual(TRIP, frappe_mock.db.get_value.call_args.args[1])

    def test_a_presented_driver_credential_is_confined_by_the_lookup_itself(self):
        _trip, frappe_mock = _resolve(staff=False, credential=OWN_DRIVER)

        self.assertEqual(
            {"name": TRIP, "driver": OWN_DRIVER}, frappe_mock.db.get_value.call_args.args[1]
        )
        frappe_mock.has_permission.assert_not_called()

    def test_a_linked_driver_session_is_confined_by_the_lookup_itself(self):
        _trip, frappe_mock = _resolve(staff=False, session_driver=OWN_DRIVER)

        self.assertEqual(
            {"name": TRIP, "driver": OWN_DRIVER}, frappe_mock.db.get_value.call_args.args[1]
        )
        frappe_mock.has_permission.assert_not_called()

    def test_a_caller_who_is_neither_staff_nor_a_driver_never_reaches_the_trip(self):
        with self.assertRaises(_Refused):
            _resolve(staff=False)


# (module, endpoint, the resolver call it must carry)
WRITES = [
    (boarding, "scan_boarding_pass", "_resolve_trip("),
    (boarding_flow, "notify_remaining_passengers", "_resolve_trip_for_driver("),
    (boarding_flow, "driver_mark_not_boarded", "_resolve_trip_for_driver("),
    (boarding_flow, "depart_and_finalize", "_resolve_trip_for_driver("),
    (manual_boarding, "board_worker", "_resolve_trip("),
]

READS = [
    (boarding, "get_boarding_pass", "_resolve_trip("),
    (boarding_flow, "get_trip_boarding", "_resolve_trip_for_driver("),
]


def _resolver_call(module, fname, call):
    with open(module.__file__, encoding="utf-8") as fh:
        body = func_source(fh.read(), module.__file__, fname)
    return next((ln for ln in body.splitlines() if call in ln), None)


class TestEveryEndpointNamesTheRightItExercises(unittest.TestCase):
    def test_a_write_endpoint_asks_for_write(self):
        """Asking for "read" before marking another project's workers Absent would pass
        the gate on a Dispatch Trip the caller may see but must not change."""
        for module, fname, call in WRITES:
            with self.subTest(endpoint=fname):
                line = _resolver_call(module, fname, call)
                self.assertIsNotNone(line, f"{fname} no longer resolves the trip at all")
                self.assertIn('"write"', line, f"{fname} resolves the trip without asking for write")

    def test_a_read_endpoint_does_not_claim_write(self):
        """The other half: a read must not demand a right its caller legitimately lacks."""
        for module, fname, call in READS:
            with self.subTest(endpoint=fname):
                line = _resolver_call(module, fname, call)
                self.assertIsNotNone(line, f"{fname} no longer resolves the trip at all")
                self.assertNotIn('"write"', line)

    def test_the_default_right_is_the_narrow_one(self):
        """The read endpoints rely on the default, so the default may not widen."""
        import inspect

        self.assertEqual(
            "read", inspect.signature(boarding._resolve_trip).parameters["ptype"].default
        )
        self.assertEqual(
            "read",
            inspect.signature(boarding_flow._resolve_trip_for_driver).parameters["ptype"].default,
        )


if __name__ == "__main__":
    unittest.main()
