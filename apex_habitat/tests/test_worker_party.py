"""Pure-Python guards for Batch 2 of the arrival redesign (no live site required).

Two things are locked in so they cannot silently regress:

  1. Every worker-identity doctype exposes the native party_type (Select:
     Employee | Temporary Worker) + party (Dynamic Link -> party_type) pair, and
     keeps `employee` as a read-only mirror.
  2. The shared `sync_party_employee` helper mirrors party <-> employee correctly
     (back-fills either direction, clears employee for a Temporary Worker, and
     enforces an identity when asked).

Run standalone:  python3 -m unittest tests.test_worker_party -v
"""

import json
import os
import sys
import types
import unittest

APP_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))

# (relative json path, party_type reqd, party_type read_only, party read_only,
#  party_type label, party label)
DOCTYPE_SPECS = {
    "Accommodation Assignment": ("habitat/doctype/accommodation_assignment/accommodation_assignment.json", 1, 0, 0, "Resident Type", "Resident"),
    "Accommodation Checkout": ("habitat/doctype/accommodation_checkout/accommodation_checkout.json", 0, 1, 1, "Resident Type", "Resident"),
    "Room Bed Transfer": ("habitat/doctype/room_bed_transfer/room_bed_transfer.json", 0, 1, 1, "Resident Type", "Resident"),
    "Accommodation Resident Request": ("habitat/doctype/accommodation_resident_request/accommodation_resident_request.json", 0, 0, 0, "Resident Type", "Resident"),
    "Idle Resident Report": ("habitat/doctype/idle_resident_report/idle_resident_report.json", 1, 0, 0, "Resident Type", "Resident"),
    "Accommodation Ledger": ("habitat/doctype/accommodation_ledger/accommodation_ledger.json", 0, 1, 1, "Resident Type", "Resident"),
    "Masar Worker Token": ("apex_core/doctype/masar_worker_token/masar_worker_token.json", 1, 0, 0, "Worker Type", "Worker"),
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
            self.assertEqual(pt.get("default"), "Employee", f"{dt}: party_type default")
            self.assertEqual(pt.get("label"), pt_label, f"{dt}: party_type label")
            self.assertEqual(bool(pt.get("reqd")), bool(pt_reqd), f"{dt}: party_type reqd")
            self.assertEqual(bool(pt.get("read_only")), bool(pt_ro), f"{dt}: party_type read_only")

            self.assertEqual(party["fieldtype"], "Dynamic Link", f"{dt}: party not Dynamic Link")
            self.assertEqual(party.get("options"), "party_type", f"{dt}: party options")
            self.assertEqual(party.get("label"), party_label, f"{dt}: party label")
            self.assertEqual(bool(party.get("read_only")), bool(party_ro), f"{dt}: party read_only")

            # employee is now a read-only mirror, never mandatory.
            self.assertTrue(emp.get("read_only"), f"{dt}: employee must be read_only")
            self.assertFalse(emp.get("reqd"), f"{dt}: employee must not be reqd")
            self.assertEqual(emp.get("options"), "Employee", f"{dt}: employee.options changed")

            # When an explicit field_order exists, the party pair must precede employee.
            if field_order:
                for fn in ("party_type", "party", "employee"):
                    self.assertIn(fn, field_order, f"{dt}: {fn} missing from field_order")
                self.assertLess(field_order.index("party_type"), field_order.index("employee"), f"{dt}: party_type after employee")
                self.assertLess(field_order.index("party"), field_order.index("employee"), f"{dt}: party after employee")


# --- helper logic ---------------------------------------------------------
# Stub a minimal `frappe` only if one is not already importable (mirrors
# tests/test_release_hygiene). Under bench the real frappe is used; standalone
# the stub lets the pure mirror logic run with no live site.
if "frappe" not in sys.modules:
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
from apex_habitat.apex_core.party_link import (  # noqa: E402
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
    def test_party_populates_employee(self):
        doc = _Doc(party_type=PARTY_EMPLOYEE, party="HR-EMP-0001", employee=None)
        sync_party_employee(doc)
        self.assertEqual(doc.employee, "HR-EMP-0001")

    def test_legacy_employee_backfills_party(self):
        # A doc built directly (e.g. the daily cost engine) with only `employee`
        # set and no party_type: normalise to Employee, derive party.
        doc = _Doc(employee="HR-EMP-0002")
        sync_party_employee(doc)
        self.assertEqual(doc.party_type, PARTY_EMPLOYEE)
        self.assertEqual(doc.party, "HR-EMP-0002")

    def test_temporary_worker_clears_employee(self):
        doc = _Doc(party_type=PARTY_TEMPORARY_WORKER, party="TEMP-2026-00001", employee="STALE")
        sync_party_employee(doc)
        self.assertIsNone(doc.employee)

    def test_require_party_raises_without_identity(self):
        with self.assertRaises(frappe.ValidationError):
            sync_party_employee(_Doc(party_type=PARTY_EMPLOYEE), require_party=True)

    def test_require_party_passes_with_employee_only(self):
        doc = _Doc(employee="HR-EMP-0003")
        sync_party_employee(doc, require_party=True)  # must not raise
        self.assertEqual(doc.party, "HR-EMP-0003")


if __name__ == "__main__":
    unittest.main()
