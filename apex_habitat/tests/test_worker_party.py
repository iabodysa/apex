"""Pure-Python guards for Batches 2-3 of the arrival redesign (no live site required).

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

# [#9fiaqz]
# [#5zn7hs]
DOCTYPE_SPECS = {
    "Accommodation Assignment": ("habitat/doctype/accommodation_assignment/accommodation_assignment.json", 1, 0, 0, "Resident Type", "Resident"),
    "Accommodation Checkout": ("habitat/doctype/accommodation_checkout/accommodation_checkout.json", 0, 1, 1, "Resident Type", "Resident"),
    "Room Bed Transfer": ("habitat/doctype/room_bed_transfer/room_bed_transfer.json", 0, 1, 1, "Resident Type", "Resident"),
    "Accommodation Resident Request": ("habitat/doctype/accommodation_resident_request/accommodation_resident_request.json", 0, 0, 0, "Resident Type", "Resident"),
    "Idle Resident Report": ("habitat/doctype/idle_resident_report/idle_resident_report.json", 1, 0, 0, "Resident Type", "Resident"),
    "Accommodation Ledger": ("habitat/doctype/accommodation_ledger/accommodation_ledger.json", 0, 1, 1, "Resident Type", "Resident"),
    "Masar Worker Token": ("apex_core/doctype/masar_worker_token/masar_worker_token.json", 1, 0, 0, "Worker Type", "Worker"),
}

# [#o85oxg]
# [#4sxjje]
# [#cmx67n]
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
            self.assertEqual(pt.get("default"), "Employee", f"{dt}: party_type default")
            self.assertEqual(pt.get("label"), pt_label, f"{dt}: party_type label")
            self.assertEqual(bool(pt.get("reqd")), bool(pt_reqd), f"{dt}: party_type reqd")
            self.assertEqual(bool(pt.get("read_only")), bool(pt_ro), f"{dt}: party_type read_only")

            self.assertEqual(party["fieldtype"], "Dynamic Link", f"{dt}: party not Dynamic Link")
            self.assertEqual(party.get("options"), "party_type", f"{dt}: party options")
            self.assertEqual(party.get("label"), party_label, f"{dt}: party label")
            self.assertEqual(bool(party.get("read_only")), bool(party_ro), f"{dt}: party read_only")

            # [#308o1s]
            self.assertTrue(emp.get("read_only"), f"{dt}: employee must be read_only")
            self.assertFalse(emp.get("reqd"), f"{dt}: employee must not be reqd")
            self.assertEqual(emp.get("options"), "Employee", f"{dt}: employee.options changed")

            # [#jrtffz]
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

            # [#lgvec7]
            self.assertTrue(emp.get("read_only"), f"{dt}: {emp_field} must be read_only")
            self.assertEqual(emp.get("options"), "Employee", f"{dt}: {emp_field}.options changed")

            if field_order:
                for fn in ("party_type", "party", emp_field):
                    self.assertIn(fn, field_order, f"{dt}: {fn} missing from field_order")
                self.assertLess(field_order.index("party"), field_order.index(emp_field), f"{dt}: party after {emp_field}")


# [#f9d9bl]
# [#8wsoyo]
# [#bu8yhr]
# [#p39gby]
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
from apex_habitat.apex_core.utils.party_link import (  # noqa: E402
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
        # [#cvvot8]
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
        sync_party_employee(doc, require_party=True)  # [#3vfaf1]
        self.assertEqual(doc.party, "HR-EMP-0003")

    def test_employee_field_param_mirrors_named_link(self):
        # [#fuzw50]
        doc = _Doc(party_type=PARTY_EMPLOYEE, party="HR-EMP-1", issued_to_employee=None)
        sync_party_employee(doc, employee_field="issued_to_employee")
        self.assertEqual(doc.issued_to_employee, "HR-EMP-1")

    def test_employee_field_param_backfills_party(self):
        doc = _Doc(returned_by_employee="HR-EMP-2")
        sync_party_employee(doc, employee_field="returned_by_employee")
        self.assertEqual(doc.party_type, PARTY_EMPLOYEE)
        self.assertEqual(doc.party, "HR-EMP-2")

    def test_employee_field_param_clears_for_temporary_worker(self):
        doc = _Doc(party_type=PARTY_TEMPORARY_WORKER, party="TEMP-1", issued_to_employee="STALE")
        sync_party_employee(doc, employee_field="issued_to_employee")
        self.assertIsNone(doc.issued_to_employee)


class TestTemporaryWorkerLink(unittest.TestCase):
    """Batch 5 — the daily Temporary-Worker -> Employee linker (pure-Python guards)."""

    def test_repoint_map_matches_party_doctypes(self):
        from apex_habitat.habitat.temporary_worker_engine import PARTY_DOCTYPES
        expected = {
            "Accommodation Assignment": "employee",
            "Accommodation Checkout": "employee",
            "Room Bed Transfer": "employee",
            "Accommodation Resident Request": "employee",
            "Idle Resident Report": "employee",
            "Accommodation Ledger": "employee",
            "Masar Worker Token": "employee",
            "Custody Issue": "issued_to_employee",
            "Custody Return": "returned_by_employee",
            "Custody Damage Assessment": "employee",
        }
        # [#rm9c5a]
        # [#g51kbi]
        self.assertEqual(PARTY_DOCTYPES, expected)
        all_paths = {dt: v[0] for dt, v in {**DOCTYPE_SPECS, **CUSTODY_SPECS}.items()}
        for dt, emp_field in PARTY_DOCTYPES.items():
            fields, _fo = _fields(all_paths[dt])
            self.assertIn("party", fields, f"{dt}: party field missing")
            self.assertIn(emp_field, fields, f"{dt}: Employee mirror {emp_field} missing")

    def test_linker_registered_in_daily_scheduler(self):
        with open(os.path.join(APP_ROOT, "hooks.py"), encoding="utf-8") as fh:
            hooks = fh.read()
        self.assertIn(
            "temporary_worker_engine.link_temporary_workers", hooks,
            "Batch 5 daily linker is not wired into scheduler_events",
        )


class TestArrivalsDeskGroundwork(unittest.TestCase):
    """Batch 6 groundwork — party-aware housing endpoint + the over-capacity bed flag."""

    def test_quick_check_in_is_party_aware(self):
        with open(os.path.join(APP_ROOT, "habitat", "api", "front_desk.py"), encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn("party_type=None, party=None", src, "quick_check_in is not party-aware")
        # [#7mg3jf]
        self.assertIn('party_type, party = "Employee", employee', src)

    def test_bed_has_is_temporary_flag(self):
        fields, _fo = _fields("habitat/doctype/accommodation_bed/accommodation_bed.json")
        self.assertIn("is_temporary", fields, "Accommodation Bed missing is_temporary")
        self.assertEqual(fields["is_temporary"]["fieldtype"], "Check")
        self.assertTrue(fields["is_temporary"].get("read_only"), "is_temporary must be read-only")

    def test_arrivals_endpoints_party_aware(self):
        with open(os.path.join(APP_ROOT, "habitat", "api", "arrivals_desk.py"), encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn("def get_arrival_card(party_type=None, party=None, employee=None)", src)
        self.assertIn("def search_arrivals_workers(", src)
        self.assertIn("def register_temporary_worker(", src)
        # [#15svuv]
        self.assertIn('"doctype": "Temporary Worker"', src)
        self.assertNotIn('"doctype": "Employee"', src)

    def test_arrivals_page_floor_map_reuses_grid(self):
        with open(
            os.path.join(APP_ROOT, "habitat", "page", "arrivals_desk", "arrivals_desk.js"), encoding="utf-8"
        ) as fh:
            js = fh.read()
        # [#6ptkdp]
        self.assertIn("apex_habitat.habitat.api.front_desk.get_building_grid", js)
        self.assertIn("class ArrivalsDesk", js)
        self.assertIn("arrivals-desk", js)  # [#lnoqyd]

    def test_arrivals_page_search_register_one_modal(self):
        with open(
            os.path.join(APP_ROOT, "habitat", "page", "arrivals_desk", "arrivals_desk.js"), encoding="utf-8"
        ) as fh:
            js = fh.read()
        self.assertIn("search_arrivals_workers", js)
        self.assertIn("register_temporary_worker", js)
        # [#32zn3u]
        self.assertEqual(js.count("new frappe.ui.Dialog"), 1, "Arrivals Desk must keep exactly one modal")

    def test_arrivals_page_houses_via_quick_check_in(self):
        with open(
            os.path.join(APP_ROOT, "habitat", "page", "arrivals_desk", "arrivals_desk.js"), encoding="utf-8"
        ) as fh:
            js = fh.read()
        # [#capvrx]
        self.assertIn("apex_habitat.habitat.api.front_desk.quick_check_in", js)
        self.assertIn("party_type: worker.party_type", js)
        self.assertIn("this.cart", js)  # [#py3nht]

    def test_over_capacity_mints_temporary_bed(self):
        with open(os.path.join(APP_ROOT, "habitat", "api", "arrivals_desk.py"), encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn("def house_over_capacity(", src)
        self.assertIn('"is_temporary": 1', src)  # [#823gp6]
        self.assertIn("quick_check_in", src)  # [#c8bpuy]
        # [#r94oxg]
        with open(os.path.join(APP_ROOT, "habitat", "api", "front_desk.py"), encoding="utf-8") as fh:
            grid = fh.read()
        self.assertIn('"is_temporary": bed.is_temporary', grid)

    def test_arrivals_page_custody_defers_temporary_worker(self):
        with open(
            os.path.join(APP_ROOT, "habitat", "page", "arrivals_desk", "arrivals_desk.js"), encoding="utf-8"
        ) as fh:
            js = fh.read()
        self.assertIn("apex_habitat.habitat.api.custody_kiosk.issue_cart", js)
        self.assertIn("Custody deferred", js)  # [#ikrv9n]
        # [#7ee3xf]
        # [#lbkt3t]
        self.assertIn("custody_kiosk.get_kiosk_catalog", js)
        self.assertIn("_custody_lines", js)
        self.assertNotIn("get_list('Custody Article'", js)

    def test_arrival_card_masar_link_and_print_slip(self):
        with open(os.path.join(APP_ROOT, "habitat", "api", "arrivals_desk.py"), encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn("def get_arrival_slip(", src)
        self.assertIn("frappe.render_template", src)  # [#5i18u4]
        with open(
            os.path.join(APP_ROOT, "habitat", "page", "arrivals_desk", "arrivals_desk.js"), encoding="utf-8"
        ) as fh:
            js = fh.read()
        # [#37bwkl]
        self.assertIn("batch_issue_worker_links", js)
        self.assertNotIn("show_worker_link_dialog", js)
        self.assertIn("get_arrival_slip", js)
        with open(
            os.path.join(APP_ROOT, "apex_core", "doctype", "masar_worker_token", "masar_worker_token.py"),
            encoding="utf-8",
        ) as fh:
            masar = fh.read()
        self.assertIn("def batch_issue_worker_links(", masar)
        self.assertIn("def masar_qr_data_uri(", masar)  # [#hsla1f]

    def test_print_slips_terms_signature_and_qr(self):
        with open(os.path.join(APP_ROOT, "habitat", "api", "arrivals_desk.py"), encoding="utf-8") as fh:
            src = fh.read()
        # [#ro6hpi]
        self.assertIn("def get_checkin_slip(", src)
        self.assertIn("def get_custody_handover_slip(", src)
        self.assertIn("masar_qr_data_uri(_worker_link", src)  # [#gp5a8y]
        self.assertNotIn("#00844e", src)  # [#9n35yx]
        with open(
            os.path.join(APP_ROOT, "habitat", "page", "arrivals_desk", "arrivals_desk.js"), encoding="utf-8"
        ) as fh:
            js = fh.read()
        self.assertIn("_print_checkin", js)
        self.assertIn("_print_custody", js)
        self.assertIn("_print_all_cards", js)

    def test_grid_occupant_shows_party_name(self):
        with open(os.path.join(APP_ROOT, "habitat", "api", "front_desk.py"), encoding="utf-8") as fh:
            src = fh.read()
        # [#oarm6k]
        self.assertIn('"party_type", "party"', src)  # [#dsjafg]
        self.assertIn("tw_names", src)  # [#7dxggs]
        self.assertIn("worker_name", src)

    def test_arrivals_page_no_orphan_dollar_refs(self):
        # [#mjnohm]
        # [#5zp6th]
        # [#dr4a2o]
        import re

        with open(
            os.path.join(APP_ROOT, "habitat", "page", "arrivals_desk", "arrivals_desk.js"), encoding="utf-8"
        ) as fh:
            js = fh.read()
        assigned = set(re.findall(r"this\.(\$[A-Za-z_]+)\s*=", js))
        used = set(re.findall(r"this\.(\$[A-Za-z_]+)\b", js))
        self.assertEqual(used - assigned, set(), "this.$ refs used but never created")

    def test_web_form_route_safeguard_patch(self):
        with open(os.path.join(APP_ROOT, "patches", "v1_x", "ensure_web_form_route.py"), encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn("def execute(", src)
        self.assertIn('frappe.db.exists("Web Form"', src)  # [#nsadxz]
        self.assertIn("set_value", src)
        self.assertNotIn("make_route_to_web_form(", src)  # [#m183h0]
        with open(os.path.join(APP_ROOT, "patches.txt"), encoding="utf-8") as fh:
            self.assertIn("v1_x.ensure_web_form_route", fh.read())

    def test_transport_one_request_employees_only(self):
        with open(
            os.path.join(APP_ROOT, "habitat", "page", "arrivals_desk", "arrivals_desk.js"), encoding="utf-8"
        ) as fh:
            js = fh.read()
        self.assertIn("frappe.new_doc('Transport Request'", js)  # [#csb2dv]
        self.assertIn("Unregistered manifest", js)  # [#1us0bs]
        self.assertIn("party_type === 'Employee'", js)  # [#glfm9i]


if __name__ == "__main__":
    unittest.main()
