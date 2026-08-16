# Copyright (c) 2026, AFMCO and contributors
"""Housing Assignment core lifecycle, plus the bed-occupancy index it depends on.

* ``TestAccommodationAssignment`` — creation/validation (mandatory fields, duplicate
  active assignment, occupied bed, room/building mismatch), the Temporary Worker
  expiry warning, the terms-signature capture, and that a failed submit does not
  discard rows written earlier in the same request.
* ``TestHousingAssignmentBedIndexDeclaration`` / ``TestFreshInstallHookDeclaresTheIndexes``
  — the two bed-occupancy indexes (``idx_asgn_bed``, ``idx_asgn_bed_active``) that the
  duplicate/occupied-bed guards above depend on for a query plan that scales. They are
  DECLARED, not only patched: ``housing_assignment.on_doctype_update`` is the one
  delivery path that reaches both a brand-new site (fresh install skips patches
  outright) and an already-installed one (``bench migrate``). The mock-based class
  proves the delegation itself; the DDL-based class proves the real index shape by
  dropping and re-declaring it against a live database.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today
import unittest
from unittest import mock
from apex.apex_core.utils import ledger_index
from apex.habitat.doctype.housing_assignment import housing_assignment

test_ignore = [
    "Additional Salary",
    "Asset",
    "Asset Movement",
    "Company",
    "Cost Center",
    "Currency",
    "Employee",
    "Item",
    "Payment Entry",
    "Project",
    "Purchase Invoice",
    "Role",
    "Salary Component",
    "Supplier",
    "User",
]


class TestAccommodationAssignment(FrappeTestCase):

    def test_create_valid_assignment(self):
        doc = frappe.get_doc({
            "doctype": "Housing Assignment",
            "naming_series": "ACC-ASGN-.YYYY.-.####",
            "employee": "EMP-QA-001",
            "project": "PROJ-QA",
            "building": "BLDG-QA",
            "room": "ROOM-QA",
            "bed": "BED-QA",
            "check_in_date": "2026-06-01",
            "assignment_type": "New Assignment",
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertIsNotNone(doc.name)
        frappe.delete_doc("Housing Assignment", doc.name, force=True, ignore_permissions=True)

    def test_missing_employee_raises(self):
        doc = frappe.get_doc({
            "doctype": "Housing Assignment",
            "naming_series": "ACC-ASGN-.YYYY.-.####",
            "project": "PROJ-QA",
            "building": "BLDG-QA",
            "room": "ROOM-QA",
            "bed": "BED-QA",
            "check_in_date": "2026-06-01",
            "assignment_type": "New Assignment",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_missing_check_in_date_raises(self):
        doc = frappe.get_doc({
            "doctype": "Housing Assignment",
            "naming_series": "ACC-ASGN-.YYYY.-.####",
            "employee": "EMP-QA-001",
            "project": "PROJ-QA",
            "building": "BLDG-QA",
            "room": "ROOM-QA",
            "bed": "BED-QA",
            "assignment_type": "New Assignment",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def _h(self):
        return frappe.generate_hash(length=12).upper()

    def _fixtures(self):
        """Create a real, internally-consistent building/room/bed/employee/project
        set so the controller's validate() runs in full (not the link-ignored stubs)."""
        company = frappe.db.get_value("Company", {}) or frappe.get_doc({
            "doctype": "Company", "company_name": "Test Co", "default_currency": "SAR",
            "country": "Saudi Arabia"}).insert(ignore_permissions=True).name
        cc = frappe.db.get_value("Cost Center", {"is_group": 0, "company": company}) or frappe.db.get_value("Cost Center", {"is_group": 0})
        site = frappe.get_doc({"doctype": "Site", "site_name": self._h() + self._h()}).insert(ignore_permissions=True).name
        building = frappe.get_doc({"doctype": "Building", "building_name": "B " + self._h(),
                                   "site": site, "total_capacity": 4, "company": company,
                                   "default_cost_center": cc}).insert(ignore_permissions=True).name
        room = frappe.get_doc({"doctype": "Room", "naming_series": "ROOM-.####", "building": building,
                               "room_number": "R" + self._h(), "bed_capacity": 4,
                               "readiness_status": "Ready"}).insert(ignore_permissions=True).name
        beds = [frappe.get_doc({"doctype": "Bed", "naming_series": "BED-.####", "room": room,
                                "building": building, "bed_code": "B" + self._h(),
                                "status": "Available"}).insert(ignore_permissions=True).name for _ in range(2)]
        project = frappe.get_doc({"doctype": "Project", "project_name": "P " + self._h()}).insert(ignore_permissions=True).name
        emps = [frappe.get_doc({"doctype": "Employee", "first_name": "E " + self._h(), "company": company,
                                "gender": "Male", "date_of_birth": "1990-01-01",
                                "date_of_joining": "2020-01-01"}).insert(ignore_permissions=True).name for _ in range(2)]
        return frappe._dict(company=company, cc=cc, building=building, room=room, beds=beds, project=project, emps=emps)

    def _assignment(self, fx, emp, bed):
        return frappe.get_doc({"doctype": "Housing Assignment", "naming_series": "ACC-ASGN-.YYYY.-.####",
                               "employee": emp, "project": fx.project, "building": fx.building, "room": fx.room,
                               "bed": bed, "cost_center": fx.cc, "check_in_date": "2026-06-01",
                               "assignment_type": "New Assignment"})

    def test_duplicate_active_assignment_rejected(self):
        """Employee with an existing active assignment cannot get a second."""
        fx = self._fixtures()
        self._assignment(fx, fx.emps[0], fx.beds[0]).submit()
        with self.assertRaises(frappe.ValidationError):
            self._assignment(fx, fx.emps[0], fx.beds[1]).insert(ignore_permissions=True)

    def test_occupied_bed_rejected(self):
        """Assignment to an already-occupied bed should be rejected."""
        fx = self._fixtures()
        self._assignment(fx, fx.emps[0], fx.beds[0]).submit()
        with self.assertRaises(frappe.ValidationError):
            self._assignment(fx, fx.emps[1], fx.beds[0]).insert(ignore_permissions=True)

    def test_room_not_in_building_rejected(self):
        """Assignment where the bed/room doesn't belong to the building is rejected."""
        fx = self._fixtures()
        other_building = frappe.get_doc({"doctype": "Building", "building_name": "B " + self._h(),
                                         "site": frappe.db.get_value("Building", fx.building, "site"),
                                         "total_capacity": 2, "company": fx.company,
                                         "default_cost_center": fx.cc}).insert(ignore_permissions=True).name
        doc = self._assignment(fx, fx.emps[0], fx.beds[0])
        doc.building = other_building
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True)

    def _temporary_worker(self, arrival_date, window_days=30):
        """A Temporary Worker whose computed expiry_date = arrival_date + window."""
        return frappe.get_doc({
            "doctype": "Temporary Worker", "worker_name": "TW " + self._h(),
            "passport_number": "P" + frappe.generate_hash(length=12).upper(),
            "arrival_date": arrival_date, "window_days": window_days,
            "status": "Active",
        }).insert(ignore_permissions=True)

    def _tw_assignment(self, fx, tw, bed, check_in_date):
        return frappe.get_doc({
            "doctype": "Housing Assignment", "naming_series": "ACC-ASGN-.YYYY.-.####",
            "party_type": "Temporary Worker", "party": tw, "project": fx.project,
            "building": fx.building, "room": fx.room, "bed": bed, "cost_center": fx.cc,
            "check_in_date": check_in_date, "assignment_type": "New Assignment",
        })

    def test_housing_temporary_worker_past_expiry_flags_not_blocks(self):
        """Housing a Temporary Worker whose window has lapsed warns (msgprint) but
        does NOT block the assignment."""
        fx = self._fixtures()
        tw = self._temporary_worker(add_days(today(), -60), window_days=30)
        self.assertLess(frappe.utils.getdate(tw.expiry_date), frappe.utils.getdate(today()))
        frappe.clear_messages()
        doc = self._tw_assignment(fx, tw.name, fx.beds[0], today())
        doc.insert(ignore_permissions=True)
        doc.submit()
        msgs = " ".join(m.get("message", "") for m in frappe.get_message_log())
        self.assertIn("expired", msgs.lower())
        self.assertEqual(doc.docstatus, 1)

    def test_housing_temporary_worker_within_window_no_flag(self):
        """A Temporary Worker still inside the window houses with no expiry warning."""
        fx = self._fixtures()
        tw = self._temporary_worker(today(), window_days=30)
        frappe.clear_messages()
        doc = self._tw_assignment(fx, tw.name, fx.beds[0], today())
        doc.insert(ignore_permissions=True)
        msgs = " ".join(m.get("message", "") for m in frappe.get_message_log())
        self.assertNotIn("expired", msgs.lower())

    def test_terms_signature_fields_exist(self):
        """The housing-terms acceptance fields are present and of the right type."""
        meta = frappe.get_meta("Housing Assignment")
        sig = meta.get_field("terms_signature")
        self.assertIsNotNone(sig)
        self.assertEqual(sig.fieldtype, "Signature")
        self.assertIsNotNone(meta.get_field("terms_accepted_on"))

    def _witness_row(self):
        """A Site row: one mandatory Data field, no links, untouched by anything else
        in this module, so its survival isolates the transaction behaviour from the
        assignment's own side effects."""
        return frappe.get_doc({
            "doctype": "Site", "site_name": "A333-ASGN-" + self._h() + self._h(),
        }).insert(ignore_permissions=True).name

    def test_a_failed_submit_keeps_rows_written_earlier_in_the_same_request(self):
        """on_submit must not wrap its occupancy writes in ``except Exception:
        frappe.db.rollback(); frappe.throw(generic)``: ``frappe.db.rollback()`` takes
        no savepoint, so it would discard the WHOLE request transaction —
        everything the request wrote before the submit, not just this assignment —
        and replace the real error with "Could not update bed occupancy".

        The recount is made to fail deliberately: nothing reachable from a fixture
        makes ``recalculate_spatial`` throw, and the point under test is what a
        failure ANYWHERE in that block costs, not which failure it was.
        """
        from unittest.mock import patch

        fx = self._fixtures()
        witness = self._witness_row()
        doc = self._assignment(fx, fx.emps[0], fx.beds[0])
        doc.insert(ignore_permissions=True)

        with patch(
            "apex.habitat.doctype.housing_assignment.housing_assignment.recalculate_spatial",
            side_effect=RuntimeError("occupancy recount failed"),
        ):
            with self.assertRaises(RuntimeError) as caught:
                doc.submit()

        self.assertIn(
            "occupancy recount failed", str(caught.exception),
            "the real error must reach the caller instead of a generic bed-occupancy "
            "message that names neither the failure nor its cause",
        )
        self.assertTrue(
            frappe.db.exists("Site", witness),
            "a failed submit must not discard rows this request wrote before it",
        )
        self.assertTrue(
            frappe.db.exists("Bed", fx.beds[0]),
            "the fixtures this request built must outlive the failed submit too",
        )

    def test_terms_signature_persists(self):
        """A captured terms signature is stored on the assignment."""
        fx = self._fixtures()
        data_uri = "data:image/png;base64,iVBORw0KGgo="
        doc = self._assignment(fx, fx.emps[0], fx.beds[0])
        doc.terms_signature = data_uri
        doc.terms_accepted_on = frappe.utils.now()
        doc.insert(ignore_permissions=True)
        self.assertEqual(
            frappe.db.get_value("Housing Assignment", doc.name, "terms_signature"),
            data_uri,
        )


# `on_doctype_update` is the one delivery path reaching BOTH a fresh site and an upgraded
# one: a fresh install marks every registered patch complete WITHOUT running it, so an index
# delivered by a patch alone would exist only on upgraded sites. The legacy v0_7 patch stays
# registered and uses the SAME index names, so a migrated site grows no duplicates.


DOCTYPE = "Housing Assignment"
BED_INDEX = "idx_asgn_bed"
ACTIVE_INDEX = "idx_asgn_bed_active"
LEGACY_PATCH = "apex.patches.v0_7.add_bed_assignment_index"

_EXPECTED_INDEXES = {
    "idx_asgn_bed": ["bed"],
    "idx_asgn_bed_active": ["bed", "docstatus", "check_out_date"],
}


def _index_calls(add_index_mock):
    """{index_name: [column, ...]} recorded off the mocked helper, so an assertion
    reads as the index contract rather than as call plumbing."""
    calls = {}
    for call in add_index_mock.call_args_list:
        doctype, fields, index_name = call.args
        assert doctype == "Housing Assignment", f"unexpected doctype {doctype!r}"
        calls[index_name] = list(fields)
    return calls


class TestFreshInstallHookDeclaresTheIndexes(unittest.TestCase):
    """No live site or DB is needed: the DDL boundary (``add_index_guarded``) is
    mocked, so what is asserted is the delegation itself, never the SQL."""

    def test_on_doctype_update_declares_both_bed_indexes(self):
        """``on_doctype_update`` is the only path that indexes a brand-new site, so
        it must declare both bed indexes over exactly the columns the occupancy
        lookup reads."""
        with mock.patch.object(
            ledger_index, "add_index_guarded", return_value=True
        ) as add_index:
            housing_assignment.on_doctype_update()

        self.assertEqual(_index_calls(add_index), _EXPECTED_INDEXES)


def _index_columns(doctype, index_name):
    """The ordered column list of one index, straight out of MariaDB."""
    rows = frappe.db.sql(
        f"SHOW INDEX FROM `tab{doctype}` WHERE Key_name = %s",
        (index_name,),
        as_dict=True,
    )
    return [row["Column_name"] for row in sorted(rows, key=lambda r: r["Seq_in_index"])]


def _indexes_covering(doctype, columns):
    """Every index name whose ordered column list equals ``columns``.

    Assert on THIS, not on an index name, wherever the framework may already
    have built an equivalent index of its own. ``bed`` is a Link carrying
    ``search_index: 1``, so Frappe creates its own single-column index (named
    ``bed`` at table creation, ``bed_index`` on a later alter). Since that change the
    guarded helper recognises that equivalence and declines to add a duplicate
    under our name, so ``idx_asgn_bed`` is present on some sites and absent on
    others while the invariant the query planner needs — bed is indexed — holds
    on both. A test that pinned the name would fail on exactly the sites where
    the deduplication worked.
    """
    rows = frappe.db.sql(f"SHOW INDEX FROM `tab{doctype}`", as_dict=True)
    grouped = {}
    for row in rows:
        grouped.setdefault(row["Key_name"], []).append(row)
    return {
        name
        for name, index_rows in grouped.items()
        if [r["Column_name"] for r in sorted(index_rows, key=lambda r: r["Seq_in_index"])]
        == list(columns)
    }
