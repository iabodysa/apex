# Copyright (c) 2026, AFMCO and contributors
"""Pure-Python guards for Batches 2-3 of the arrival redesign (no live site required).

Two things are locked in so they cannot silently regress:

  1. Every worker-identity doctype exposes the native party_type (Select:
     Employee | Temporary Worker) + party (Dynamic Link -> party_type) pair, and
     keeps `employee` as a read-only mirror.
  2. The shared `sync_party_employee` helper mirrors party <-> employee correctly
     (back-fills either direction, clears employee for a Temporary Worker, and
     enforces an identity when asked).

Run standalone:  python3 -m unittest apex.apex_core.utils.test_worker_party -v
"""

import json
import os
import sys
import types
import unittest
from pathlib import Path

import apex

APP_ROOT = str(Path(apex.__file__).resolve().parent)

DOCTYPE_SPECS = {
    "Housing Assignment": ("habitat/doctype/housing_assignment/housing_assignment.json", 1, 0, 0, "Resident Type", "Resident"),
    "Housing Checkout": ("habitat/doctype/housing_checkout/housing_checkout.json", 0, 1, 1, "Resident Type", "Resident"),
    "Room Bed Transfer": ("habitat/doctype/room_bed_transfer/room_bed_transfer.json", 0, 1, 1, "Resident Type", "Resident"),
    "Resident Request": ("habitat/doctype/resident_request/resident_request.json", 0, 0, 0, "Resident Type", "Resident"),
    "Idle Resident Report": ("habitat/doctype/idle_resident_report/idle_resident_report.json", 1, 0, 0, "Resident Type", "Resident"),
    "Accommodation Ledger": ("habitat/doctype/accommodation_ledger/accommodation_ledger.json", 0, 1, 1, "Resident Type", "Resident"),
    "Masar Worker Token": ("apex_core/doctype/masar_worker_token/masar_worker_token.json", 0, 0, 0, "Worker Type", "Worker"),
}

CUSTODY_SPECS = {
    "Custody Issue": ("habitat/doctype/custody_issue/custody_issue.json", "issued_to_employee"),
    "Custody Return": ("habitat/doctype/custody_return/custody_return.json", "returned_by_employee"),
    "Custody Damage Assessment": ("habitat/doctype/custody_damage_assessment/custody_damage_assessment.json", "employee"),
}


def _fields(doctype_json):
    with open(os.path.join(APP_ROOT, doctype_json), encoding="utf-8") as fh:
        data = json.load(fh)
    return {f["fieldname"]: f for f in data["fields"]}, data.get("field_order", []) or []


class TestPartyFieldsInSchema(unittest.TestCase):
    def test_party_fields_present_and_well_formed(self):
        for dt, (path, pt_reqd, pt_ro, party_ro, pt_label, party_label) in DOCTYPE_SPECS.items():
            fields, field_order = _fields(path)
            self.assertIn("party_type", fields, f"{dt}: party_type missing")
            self.assertIn("party", fields, f"{dt}: party missing")
            self.assertIn("employee", fields, f"{dt}: employee missing")

            pt, party, emp = fields["party_type"], fields["party"], fields["employee"]

            self.assertEqual(pt["fieldtype"], "Select", f"{dt}: party_type not Select")
            self.assertEqual(pt.get("options"), "Employee\nTemporary Worker", f"{dt}: party_type options")
            if dt == "Masar Worker Token":
                self.assertNotIn("default", pt, f"{dt}: party_type must not default for Driver")
                self.assertEqual(
                    pt.get("mandatory_depends_on"),
                    "eval:doc.holder_type!='Driver'",
                    f"{dt}: party_type must be mandatory only outside Driver mode",
                )
            else:
                self.assertEqual(pt.get("default"), "Employee", f"{dt}: party_type default")
            self.assertEqual(pt.get("label"), pt_label, f"{dt}: party_type label")
            self.assertEqual(bool(pt.get("reqd")), bool(pt_reqd), f"{dt}: party_type reqd")
            self.assertEqual(bool(pt.get("read_only")), bool(pt_ro), f"{dt}: party_type read_only")

            self.assertEqual(party["fieldtype"], "Dynamic Link", f"{dt}: party not Dynamic Link")
            self.assertEqual(party.get("options"), "party_type", f"{dt}: party options")
            self.assertEqual(party.get("label"), party_label, f"{dt}: party label")
            self.assertEqual(bool(party.get("read_only")), bool(party_ro), f"{dt}: party read_only")

            self.assertTrue(emp.get("read_only"), f"{dt}: employee must be read_only")
            self.assertFalse(emp.get("reqd"), f"{dt}: employee must not be reqd")
            self.assertEqual(emp.get("options"), "Employee", f"{dt}: employee.options changed")

            if field_order:
                for fn in ("party_type", "party", "employee"):
                    self.assertIn(fn, field_order, f"{dt}: {fn} missing from field_order")
                self.assertLess(field_order.index("party_type"), field_order.index("employee"), f"{dt}: party_type after employee")
                self.assertLess(field_order.index("party"), field_order.index("employee"), f"{dt}: party after employee")

    def test_custody_party_fields_present_and_well_formed(self):
        for dt, (path, emp_field) in CUSTODY_SPECS.items():
            fields, field_order = _fields(path)
            self.assertIn("party_type", fields, f"{dt}: party_type missing")
            self.assertIn("party", fields, f"{dt}: party missing")
            self.assertIn(emp_field, fields, f"{dt}: {emp_field} missing")

            pt, party, emp = fields["party_type"], fields["party"], fields[emp_field]

            self.assertEqual(pt["fieldtype"], "Select", f"{dt}: party_type not Select")
            self.assertEqual(pt.get("options"), "Employee\nTemporary Worker", f"{dt}: party_type options")
            self.assertEqual(pt.get("default"), "Employee", f"{dt}: party_type default")
            self.assertEqual(pt.get("label"), "Worker Type", f"{dt}: party_type label")
            self.assertFalse(pt.get("reqd"), f"{dt}: custody party_type must not be reqd")

            self.assertEqual(party["fieldtype"], "Dynamic Link", f"{dt}: party not Dynamic Link")
            self.assertEqual(party.get("options"), "party_type", f"{dt}: party options")
            self.assertEqual(party.get("label"), "Worker", f"{dt}: party label")
            self.assertFalse(party.get("read_only"), f"{dt}: custody party must stay editable")

            self.assertTrue(emp.get("read_only"), f"{dt}: {emp_field} must be read_only")
            self.assertEqual(emp.get("options"), "Employee", f"{dt}: {emp_field}.options changed")

            if field_order:
                for fn in ("party_type", "party", emp_field):
                    self.assertIn(fn, field_order, f"{dt}: {fn} missing from field_order")
                self.assertLess(field_order.index("party"), field_order.index(emp_field), f"{dt}: party after {emp_field}")


# True only on the standalone (`python3 -m unittest`) path below, where frappe is
# replaced by a local stub. Under `bench run-tests` the real frappe is always
# already imported, so this stays False and nothing in this module skips.
FRAPPE_IS_STUBBED = "frappe" not in sys.modules

if FRAPPE_IS_STUBBED:
    _fake = types.ModuleType("frappe")

    class _ValidationError(Exception):
        pass

    class _MandatoryError(_ValidationError):
        pass

    def _throw(msg, exc=_ValidationError, *args, **kwargs):
        raise (exc if isinstance(exc, type) else _ValidationError)(msg)

    _fake.ValidationError = _ValidationError
    _fake.MandatoryError = _MandatoryError
    _fake.throw = _throw
    _fake._ = lambda s: s
    _fake.db = types.SimpleNamespace(get_value=lambda *a, **k: None)
    sys.modules["frappe"] = _fake

import frappe  # noqa: E402  (resolved to the real or stubbed module above)
from apex.apex_core.utils.party_link import (  # noqa: E402
    PARTY_EMPLOYEE,
    PARTY_TEMPORARY_WORKER,
    sync_party_employee,
)

class _Doc:
    """Lightweight stand-in for a Frappe document (get + attribute access)."""

    def __init__(self, **kw):
        self.__dict__.update(kw)

    def get(self, key, default=None):
        return self.__dict__.get(key, default)


class TestSyncPartyEmployee(unittest.TestCase):
    def test_sync_backfills_party_and_employee_in_either_direction(self):
        """The default employee mirror back-fills whichever half of the pair is
        missing, in either direction (module docstring bullet 2)."""
        forward = _Doc(party_type=PARTY_EMPLOYEE, party="HR-EMP-0001", employee=None)
        sync_party_employee(forward)
        self.assertEqual(
            forward.employee, "HR-EMP-0001", "party fills employee when only party is set"
        )

        # set and no party_type: normalise to Employee, derive party.
        backward = _Doc(employee="HR-EMP-0002")
        sync_party_employee(backward)
        self.assertEqual(
            backward.party_type,
            PARTY_EMPLOYEE,
            "a bare employee normalises party_type to Employee",
        )
        self.assertEqual(
            backward.party, "HR-EMP-0002", "employee fills party when only employee is set"
        )

    def test_temporary_worker_clears_employee(self):
        doc = _Doc(party_type=PARTY_TEMPORARY_WORKER, party="TEMP-2026-00001", employee="STALE")
        sync_party_employee(doc)
        self.assertIsNone(doc.employee)

    def test_require_party_raises_without_identity(self):
        with self.assertRaises(frappe.ValidationError):
            sync_party_employee(_Doc(party_type=PARTY_EMPLOYEE), require_party=True)

    def test_require_party_passes_with_employee_only(self):
        doc = _Doc(employee="HR-EMP-0003")
        sync_party_employee(doc, require_party=True)
        self.assertEqual(doc.party, "HR-EMP-0003")

    def test_employee_field_param_backfills_in_either_direction(self):
        """The employee_field override mirrors the same way as the default field,
        in either direction."""
        forward = _Doc(party_type=PARTY_EMPLOYEE, party="HR-EMP-1", issued_to_employee=None)
        sync_party_employee(forward, employee_field="issued_to_employee")
        self.assertEqual(
            forward.issued_to_employee, "HR-EMP-1", "party fills the named employee field"
        )

        backward = _Doc(returned_by_employee="HR-EMP-2")
        sync_party_employee(backward, employee_field="returned_by_employee")
        self.assertEqual(
            backward.party_type,
            PARTY_EMPLOYEE,
            "a bare named employee field normalises party_type to Employee",
        )
        self.assertEqual(
            backward.party, "HR-EMP-2", "the named employee field fills party"
        )

    def test_employee_field_param_clears_for_temporary_worker(self):
        doc = _Doc(party_type=PARTY_TEMPORARY_WORKER, party="TEMP-1", issued_to_employee="STALE")
        sync_party_employee(doc, employee_field="issued_to_employee")
        self.assertIsNone(doc.issued_to_employee)


class TestTemporaryWorkerLink(unittest.TestCase):
    """Batch 5 — the daily Temporary-Worker -> Employee linker (pure-Python guards)."""

    def test_repoint_map_matches_party_doctypes(self):
        from apex.habitat.temporary_worker_engine import PARTY_DOCTYPES
        expected = {
            "Housing Assignment": "employee",
            "Housing Checkout": "employee",
            "Room Bed Transfer": "employee",
            "Resident Request": "employee",
            "Idle Resident Report": "employee",
            "Accommodation Ledger": "employee",
            "Masar Worker Token": "employee",
            "Custody Issue": "issued_to_employee",
            "Custody Return": "returned_by_employee",
            "Custody Damage Assessment": "employee",
            # The custody BALANCE lives here (temporary_worker_engine.py:43-47):
            # leaving either behind strands the worker's stock, so the daily linker
            # repoints these two as well.
            "Accommodation Stock Ledger": "employee",
            "Custody Acknowledgment": "acknowledged_by_employee",
        }
        self.assertEqual(PARTY_DOCTYPES, expected)
        all_paths = {dt: v[0] for dt, v in {**DOCTYPE_SPECS, **CUSTODY_SPECS}.items()}
        # Neither spec dict covers these two -- each field shape is its own (a
        # differently-labelled Holder pair on the stock ledger; a read-only pair
        # fetched from the parent issue on the acknowledgment) -- so only the path
        # is added here. The shape itself is graded by test_party_fields_present_
        # and_well_formed / test_custody_party_fields_present_and_well_formed only
        # for the doctypes named in DOCTYPE_SPECS / CUSTODY_SPECS.
        all_paths.update(
            {
                "Accommodation Stock Ledger": (
                    "habitat/doctype/accommodation_stock_ledger/"
                    "accommodation_stock_ledger.json"
                ),
                "Custody Acknowledgment": (
                    "habitat/doctype/custody_acknowledgment/custody_acknowledgment.json"
                ),
            }
        )
        for dt, emp_field in PARTY_DOCTYPES.items():
            fields, _fo = _fields(all_paths[dt])
            self.assertIn("party", fields, f"{dt}: party field missing")
            self.assertIn(emp_field, fields, f"{dt}: Employee mirror {emp_field} missing")

    def test_linker_registered_in_daily_scheduler(self):
        """Asks frappe's own hook loader, not a substring match on hooks.py.

        The retired version grepped the raw text of hooks.py for the dotted path, which
        is satisfied by the string sitting in a comment, a docstring, or the wrong bucket
        (``cron`` instead of ``daily``) just as readily as by a real registration.
        ``frappe.get_hooks`` is what the scheduler itself calls to decide what runs today
        (frappe/utils/scheduler.py), so this reads the same parsed, bucketed structure.
        """
        if FRAPPE_IS_STUBBED:
            self.skipTest(
                "standalone run: the local frappe stub has no site, so get_hooks cannot resolve"
            )
        daily_jobs = frappe.get_hooks("scheduler_events", app_name="apex").get("daily", [])
        self.assertIn(
            "apex.habitat.temporary_worker_engine.link_temporary_workers", daily_jobs,
            f"Batch 5 daily linker is not registered in hooks.py scheduler_events['daily']: {daily_jobs}",
        )


# TestArrivalsDeskGroundwork was deleted on 2026-08-16: 14 tests holding 26 assertions that
# pinned SOURCE TEXT — `assertIn("def get_arrival_card(party_type=None, party=None, ...)", src)`.
# A Change Detector Test breaks on an honest rename and passes on a wrong implementation, and
# these guarded a migration batch that shipped. The behaviour they claimed to cover is held by
# apex/habitat/api/test_arrivals_card_scope.py and test_arrivals_worker_search_limit.py, which
# call the endpoints instead of reading them.


class TestPassportMrzParser(unittest.TestCase):
    """Deterministic specimen proof for the opt-in MRZ autofill parser.

    parse_mrz_text is the pure, testable core of the camera-capture feature; OCR
    is pluggable. It reads frappe.utils.now_datetime for the two-digit-year century
    rule, so it needs the real bench frappe.

 The retained skip fires ONLY on the standalone `python3 -m unittest`
    path, where the module installs a local frappe stub that cannot import the
    arrivals-desk API at all. Under `bench run-tests` — the CI path — FRAPPE_IS_STUBBED
    is False and both tests below execute. Skipping must key off FRAPPE_IS_STUBBED, not
    `isinstance(frappe.utils, SimpleNamespace)`: the stub never defines that attribute, so a
    check keyed on it would never fire in either direction, leaving the standalone run
    erroring on an ImportError instead of skipping, and staying dead weight under a
    bench."""

    def _parser(self):
        if FRAPPE_IS_STUBBED:
            self.skipTest(
                "standalone run: the local frappe stub cannot import "
                "apex.habitat.api.arrivals_desk (needs the real frappe.utils)"
            )
        from apex.habitat.api.arrivals_desk import parse_mrz_text

        return parse_mrz_text

    def test_parses_td3_specimen(self):
        parse = self._parser()
        text = "P<UTOSPECIMEN<<TRAVELLER<SAMPLE<<<<<<<<<<<<<<\nX123456785UTO8001011M3012315<<<<<<<<<<<<<<04"
        out = parse(text)
        self.assertEqual(out.get("passport_number"), "X12345678")
        self.assertEqual(out.get("worker_name"), "TRAVELLER SAMPLE SPECIMEN")
        self.assertEqual(out.get("expiry_date"), "2030-12-31")

    def test_garbled_scan_degrades_to_empty(self):
        parse = self._parser()
        self.assertEqual(parse("not a passport").get("passport_number"), None)


if __name__ == "__main__":
    unittest.main()
