# Copyright (c) 2026, AFMCO and contributors
"""The SIM loaders must ask the database for their identifier, not the string.

``frappe.db.exists(dt, dn)`` answers ``dn`` back WITHOUT touching the database when
the two are equal (database.py:1259 — the deliberate "a Single always exists"
short-circuit). Three loaders took their identifier straight from a whitelisted
endpoint and probed it positionally, so a caller passing the literal DocType name
cleared the gate without a query:

  * ``sim_actions._load_sim`` and ``telecom_control.get_sim_detail`` fell through to
    ``get_doc``, which raises a bare framework 404 in place of the module's own
    named refusal;
  * ``sim_actions.move_to_contract`` fell through to ``get_value``, which returns
    ``None``, so reading ``target.docstatus`` raised an unhandled ``AttributeError``.

No permission bypass: ``check_permission`` still runs on whatever document loads.
What the short-circuit costs is each module's own named refusal — and, in
``move_to_contract``, an orderly failure at all.

These cases pass the literal DocType string and assert the loader's own throw lands
BEFORE ``get_doc`` / ``get_value``, then assert the other direction: a document that
genuinely bears that name is still found, which a bare ``name != doctype`` rejection
would have broken.

Site-free: only ``frappe.db.exists`` decides these paths, so each module's ``frappe``
is swapped for ``tests.factories.ExistsShortCircuitDB`` — the shared stub that
reproduces the short-circuit faithfully for every suite pinning this defect.
"""

import unittest
from inspect import unwrap
from unittest.mock import patch

from apex.logistay.api import sim_actions, telecom_control
from apex.tests.factories import ExistsShortCircuitDB

SIM_DOCTYPE = "SIM Card"
CONTRACT_DOCTYPE = "Telecom Contract"

# The whitelist decorator wraps each endpoint in frappe's argument-type validator,
# which reads ``frappe.local.flags`` and therefore needs a request or a site. These
# cases exercise the guard inside the endpoint, not the wrapper, so they call the
# undecorated function (``@wraps`` keeps it on ``__wrapped__``) and stay site-free.
_get_sim_detail = unwrap(telecom_control.get_sim_detail)
_move_to_contract = unwrap(sim_actions.move_to_contract)


class _StubDB(ExistsShortCircuitDB):
    """``move_to_contract``'s fall-through landed in ``get_value``, so reaching it
    here means the gate was skipped."""

    def get_value(self, doctype, name, *args, **kwargs):
        raise AssertionError(f"the guard let {doctype} {name!r} through to get_value")


class _Thrown(Exception):
    """What the module's own ``frappe.throw`` refusal looks like to these cases."""


class _StubFrappe:
    def __init__(self, present):
        self.db = _StubDB(present)
        self.loaded = []

    def throw(self, message, **_kwargs):
        raise _Thrown(message)

    def get_doc(self, doctype, name):
        self.loaded.append((doctype, name))
        raise AssertionError(f"the guard let {doctype} {name!r} through to get_doc")


class _RecordingFrappe(_StubFrappe):
    """Records the load instead of refusing it — for the "still found" direction."""

    def get_doc(self, doctype, name):
        self.loaded.append((doctype, name))
        return object()


def _patched(module, stub):
    return patch.multiple(module, frappe=stub, _=lambda text: text)


class TestASelfNamedIdentifierIsRefusedByTheLoaderItself(unittest.TestCase):
    def _refuses(self, module, call, doctype):
        stub = _StubFrappe({doctype: set()})
        with _patched(module, stub):
            with self.assertRaises(_Thrown) as caught:
                call()
        self.assertIn("does not exist", str(caught.exception))
        self.assertEqual(stub.loaded, [], "the refusal must land before get_doc")
        self.assertTrue(stub.db.queried, "the probe must reach the database, not short-circuit")

    def test_a_sim_id_equal_to_its_doctype_is_refused_by_the_action_loader(self):
        self._refuses(sim_actions, lambda: sim_actions._load_sim(SIM_DOCTYPE), SIM_DOCTYPE)

    def test_a_sim_id_equal_to_its_doctype_is_refused_by_the_detail_drawer(self):
        self._refuses(telecom_control, lambda: _get_sim_detail(SIM_DOCTYPE), SIM_DOCTYPE)

    def test_a_contract_id_equal_to_its_doctype_is_refused_before_get_value(self):
        """``move_to_contract`` checks the contract first, so the refusal lands before
        the SIM is loaded AND before the ``get_value`` whose ``None`` used to become
        an AttributeError."""
        self._refuses(
            sim_actions,
            lambda: _move_to_contract("SIM-2026-00001", CONTRACT_DOCTYPE),
            CONTRACT_DOCTYPE,
        )


class TestTheProbeStillTellsAbsentAndPresentApart(unittest.TestCase):
    def test_an_ordinary_absent_docname_is_refused_the_same_way(self):
        """The refusal does not discriminate: a self-named token and a docname that
        simply is not there produce the same message, so neither is usable as a probe
        for which rows exist."""
        stub = _StubFrappe({SIM_DOCTYPE: set()})
        with _patched(sim_actions, stub):
            with self.assertRaises(_Thrown) as caught:
                sim_actions._load_sim("SIM-2026-00001")
        self.assertIn("does not exist", str(caught.exception))

    def test_a_document_really_bearing_its_doctype_name_is_still_loaded(self):
        """The other direction. A bare ``name != doctype`` rejection would refuse a
        real row here; the dict filter asks the database and finds it."""
        stub = _RecordingFrappe({SIM_DOCTYPE: {SIM_DOCTYPE}})
        with _patched(sim_actions, stub):
            sim_actions._load_sim(SIM_DOCTYPE)
        self.assertEqual(stub.loaded, [(SIM_DOCTYPE, SIM_DOCTYPE)])

    def test_an_ordinary_live_sim_is_still_loaded(self):
        stub = _RecordingFrappe({SIM_DOCTYPE: {"SIM-2026-00001"}})
        with _patched(sim_actions, stub):
            sim_actions._load_sim("SIM-2026-00001")
        self.assertEqual(stub.loaded, [(SIM_DOCTYPE, "SIM-2026-00001")])

    def test_an_empty_identifier_is_refused_without_a_query(self):
        stub = _StubFrappe({SIM_DOCTYPE: set()})
        with _patched(sim_actions, stub):
            with self.assertRaises(_Thrown):
                sim_actions._load_sim("")
        self.assertEqual(stub.db.queried, [])


if __name__ == "__main__":
    unittest.main()
