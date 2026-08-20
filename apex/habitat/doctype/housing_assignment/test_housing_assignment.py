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
from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today
import unittest
from unittest import mock
from apex.apex_core.utils import ledger_index
from apex.habitat.doctype.housing_assignment import housing_assignment
import json
from pathlib import Path
from frappe.desk.query_report import get_report_doc
import apex
import inspect
import os
from apex.apex_core.utils.ledger_index import _index_exists, add_index_guarded
from apex.habitat.doctype.accommodation_stock_ledger import accommodation_stock_ledger



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

test_dependencies = ['Bed', 'Employee']
test_ignore = ['Additional Salary', 'Asset', 'Asset Movement', 'Company', 'Cost Center', 'Currency', 'Employee', 'Item', 'Payment Entry', 'Project', 'Purchase Invoice', 'Role', 'Salary Component', 'Supplier', 'User']


# --- merged from test_housing_assignment_auditor_access.py ---
_HOUSING_ASSIGNMENT_JSON = Path(apex.__file__).resolve().parent / "habitat" / "doctype" / "housing_assignment" / "housing_assignment.json"
AUDITOR_ROLE = "Internal Auditor"
THE_GRANTED_REPORTS = (
    "Accommodation Occupancy Summary",
    "Idle Resident Detection",
)
class TestInternalAuditorHousingAccess(FrappeTestCase):
    """Site-bound. `frappe.session.user` is process state that no rollback restores, so the
    cleanup is registered BEFORE anything sets it."""

    def setUp(self):
        self.addCleanup(frappe.set_user, "Administrator")
        frappe.set_user("Administrator")

    def _auditor(self):
        return frappe.get_doc(
            {
                "doctype": "User",
                "email": f"a216_{frappe.generate_hash(length=12)}@example.com",
                "first_name": "Auditor",
                "roles": [{"role": AUDITOR_ROLE}],
            }
        ).insert(ignore_permissions=True).name

    def test_the_auditor_opens_the_report_and_is_refused_the_export(self):
        """THE PAIR. Both halves in one method, asserted explicitly different at the end —
        a bug that granted everything would satisfy the open, and a bug that granted
        nothing would satisfy the refusal. Only the contrast proves the shape."""
        auditor = self._auditor()
        frappe.set_user(auditor)

        # Half 1 — THE OPEN. get_report_doc carries both gates the role must clear:
        # Report.is_permitted() at query_report.py:41 and has_permission(ref, "report")
        # at :47. Calling it is the real open path, not a re-implementation of it.
        opened = get_report_doc("Accommodation Occupancy Summary")
        self.assertEqual(opened.ref_doctype, "Housing Assignment")
        open_verdict = "opened"

        # Half 2 — THE REFUSAL. Caught by NAME: frappe.PermissionError does not descend
        # from ValidationError, so an unrelated validation failure cannot satisfy this.
        with self.assertRaises(frappe.PermissionError) as caught:
            frappe.permissions.can_export("Housing Assignment", raise_exception=True)
        self.assertIn(
            "Housing Assignment",
            str(caught.exception),
            "the export refusal does not name the DocType it refused",
        )
        export_verdict = "refused"

        self.assertNotEqual(
            open_verdict,
            export_verdict,
            "the two halves collapsed into one verdict — the grant is all-or-nothing",
        )
        # And the underlying rights, so the verdicts above cannot both be accidents.
        self.assertIs(frappe.has_permission("Housing Assignment", "read", user=auditor), True)
        self.assertIs(frappe.has_permission("Housing Assignment", "report", user=auditor), True)
        self.assertFalse(
            frappe.permissions.can_export("Housing Assignment"),
            "export leaked back in",
        )

    def test_every_formerly_broken_report_now_opens(self):
        """The baseline in test_report_role_guard drained them together, because they
        turned on one row. If only one of them opens, that drain was wrong."""
        frappe.set_user(self._auditor())
        for report in THE_GRANTED_REPORTS:
            with self.subTest(report=report):
                doc = get_report_doc(report)
                self.assertEqual(doc.ref_doctype, "Housing Assignment")

    def test_a_role_without_the_row_still_cannot_open_them(self):
        """The control. Without it, a test that passed because the reports stopped checking
        anything would look identical to one that passed because the grant works."""
        outsider = frappe.get_doc(
            {
                "doctype": "User",
                "email": f"a216x_{frappe.generate_hash(length=12)}@example.com",
                "first_name": "Outsider",
                "roles": [{"role": "Fleet Supervisor"}],
            }
        ).insert(ignore_permissions=True).name
        frappe.set_user(outsider)
        with self.assertRaises(frappe.PermissionError):
            get_report_doc("Accommodation Occupancy Summary")

    def test_the_row_grants_exactly_read_and_report(self):
        """The shipped row: a right must be absent by OMISSION, not shipped as 0."""
        shipped = json.loads(_HOUSING_ASSIGNMENT_JSON.read_text(encoding="utf-8"))
        rows = [
            p
            for p in shipped["permissions"]
            if p.get("role") == AUDITOR_ROLE and int(p.get("permlevel") or 0) == 0
        ]
        self.assertEqual(len(rows), 1, f"expected exactly one permlevel-0 {AUDITOR_ROLE} row")
        row = rows[0]
        self.assertEqual(row.get("read"), 1)
        self.assertEqual(row.get("report"), 1)
        for withheld in (
            "export",
            "write",
            "create",
            "delete",
            "submit",
            "cancel",
            "amend",
            "share",
            "print",
            "email",
        ):
            self.assertNotIn(
                withheld,
                row,
                f"{withheld} must be OMITTED from the row, not shipped as 0 — an explicit "
                "0 reads as a toggle someone meant to flip",
            )

    def test_the_grant_did_not_disturb_the_other_roles(self):
        """A second plain read row for an existing role would silently disable an if_owner
        constraint (permissions.py:286-287). Nothing else on this table may have moved.

        Counted at permlevel 0 only. A permlevel-1 row is field access, not a second grant
        of the record, and it cannot reach the if_owner path this guards -- so counting by
        role alone would flag the signature concealment as a duplicate and push the next
        author to delete the row that hides it.
        """
        shipped = json.loads(_HOUSING_ASSIGNMENT_JSON.read_text(encoding="utf-8"))
        by_role = {}
        for p in shipped["permissions"]:
            if int(p.get("permlevel") or 0) == 0:
                by_role.setdefault(p["role"], []).append(p)
        self.assertEqual(
            sorted(by_role),
            ["Accommodation Manager", AUDITOR_ROLE, "Resident Supervisor", "System Manager"],
            "the role set on Housing Assignment changed beyond the Internal Auditor grant",
        )
        for role, rows in by_role.items():
            self.assertEqual(len(rows), 1, f"{role} gained a second permlevel-0 row — check if_owner")

    def test_the_auditor_holds_no_write_authority(self):
        """The read-only shape, proven at runtime rather than inferred from the JSON."""
        auditor = self._auditor()
        for right in ("write", "create", "delete", "submit", "cancel"):
            with self.subTest(right=right):
                self.assertIs(
                    frappe.has_permission("Housing Assignment", right, user=auditor),
                    False,
                    f"the auditor grant leaked {right}",
                )

    def test_the_unscoped_exemption_now_has_a_row_to_apply_to(self):
        """The contradiction, asserted directly: the role is in HOUSING_UNSCOPED_ROLES, and
        it can now actually read the DocType that set was lifting a filter on."""
        from apex.habitat import permissions

        self.assertIn(AUDITOR_ROLE, permissions.HOUSING_UNSCOPED_ROLES)
        auditor = self._auditor()
        self.assertEqual(
            permissions.building_scope_query(auditor, doctype="Housing Assignment"),
            "",
            "an unscoped role must get an empty row filter",
        )
        self.assertIs(frappe.has_permission("Housing Assignment", "read", user=auditor), True)


# --- merged from test_housing_assignment_bed_index.py ---
DOCTYPE_housing_assignment_bed_index = "Housing Assignment"
BED_INDEX_housing_assignment_bed_index = "idx_asgn_bed"
ACTIVE_INDEX_housing_assignment_bed_index = "idx_asgn_bed_active"
LEGACY_PATCH_housing_assignment_bed_index = "apex.patches.v0_7.add_bed_assignment_index"
def _index_columns_housing_assignment_bed_index(doctype, index_name):
    """The ordered column list of one index, straight out of MariaDB."""
    rows = frappe.db.sql(
        f"SHOW INDEX FROM `tab{doctype}` WHERE Key_name = %s",
        (index_name,),
        as_dict=True,
    )
    return [row["Column_name"] for row in sorted(rows, key=lambda r: r["Seq_in_index"])]
def _indexes_covering_housing_assignment_bed_index(doctype, columns):
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
class TestHousingAssignmentBedIndexDeclaration(FrappeTestCase):
    def test_on_doctype_update_is_a_module_level_hook(self):
        """Frappe's sync/migrate calls the DocType module's MODULE-LEVEL
        ``on_doctype_update`` — a method on the controller class is never
        invoked, so the declaration only reaches a fresh install in this shape."""
        hook = getattr(housing_assignment, "on_doctype_update", None)
        self.assertTrue(callable(hook), "housing_assignment declares no on_doctype_update")
        self.assertTrue(inspect.isfunction(hook), "on_doctype_update must be a module-level function")
        self.assertEqual(hook.__module__, housing_assignment.__name__)

    def test_it_mirrors_the_accommodation_stock_ledger_declaration(self):
        """Same fix, same effect: the sibling ledger's declaration also puts its
        index on the table. Asserted by running it and inspecting the database,
        not by reading either module's source."""
        sibling = getattr(accommodation_stock_ledger, "on_doctype_update", None)
        self.assertTrue(callable(sibling), "the mirrored ASL declaration disappeared")
        sibling()
        self.assertTrue(
            _index_exists("Accommodation Stock Ledger", "idx_asl_cancel_type_emp"),
            "the mirrored declaration must produce its index too",
        )

    def test_both_bed_indexes_are_declared_and_shaped_correctly(self):
        """The state a freshly synced site must end up in."""
        housing_assignment.on_doctype_update()
        self.assertTrue(
            _indexes_covering_housing_assignment_bed_index(DOCTYPE_housing_assignment_bed_index, ["bed"]),
            "no index covers the bed column alone — the occupancy lookup would "
            "table-scan whether or not our own index name is the one present",
        )
        self.assertTrue(_index_exists(DOCTYPE_housing_assignment_bed_index, ACTIVE_INDEX_housing_assignment_bed_index))
        self.assertEqual(
            _index_columns_housing_assignment_bed_index(DOCTYPE_housing_assignment_bed_index, ACTIVE_INDEX_housing_assignment_bed_index),
            ["bed", "docstatus", "check_out_date"],
            "the composite index must serve the active-occupancy lookup "
            '({"bed": ..., "docstatus": 1, "check_out_date": ["is", "not set"]})',
        )

    def _rebuild(self, index_name, fields):
        add_index_guarded(DOCTYPE_housing_assignment_bed_index, fields, index_name)

    def _prove_declaration_recreates(self, index_name, fields):
        """Drop every index over these columns, prove none remain, then let the
        declaration put coverage back.

        This is what makes the test causal: without the drop, a green would only
        show that SOME earlier migrate had created the index, which is exactly the
        upgraded-site case is NOT about.

        Every equivalent index goes, not just ours — leaving the framework's own
        ``bed`` search index in place would make the declaration a legitimate
        no-op and the test would prove nothing. The rebuild registered
        first restores coverage under our name, which is the same invariant, not
        necessarily the same index name the site started with.
        """
        # Make sure coverage is there to drop (and register the rebuild first, so
        # the column is indexed again even if an assertion below fails).
        housing_assignment.on_doctype_update()
        self.addCleanup(self._rebuild, index_name, fields)
        for existing in _indexes_covering_housing_assignment_bed_index(DOCTYPE_housing_assignment_bed_index, fields):
            frappe.db.sql(f"ALTER TABLE `tab{DOCTYPE_housing_assignment_bed_index}` DROP INDEX `{existing}`")
        self.assertEqual(
            _indexes_covering_housing_assignment_bed_index(DOCTYPE_housing_assignment_bed_index, fields),
            set(),
            f"no index over {fields} should remain — this is the fresh-install "
            "starting state",
        )

        housing_assignment.on_doctype_update()

        self.assertIn(
            index_name,
            _indexes_covering_housing_assignment_bed_index(DOCTYPE_housing_assignment_bed_index, fields),
            f"on_doctype_update must create {index_name} on a site where nothing "
            f"else indexes {fields}",
        )
        self.assertEqual(_index_columns_housing_assignment_bed_index(DOCTYPE_housing_assignment_bed_index, index_name), fields)

    def test_a_site_without_the_bed_index_gets_it_from_the_declaration(self):
        self._prove_declaration_recreates(BED_INDEX_housing_assignment_bed_index, ["bed"])

    def test_a_site_without_the_active_index_gets_it_from_the_declaration(self):
        self._prove_declaration_recreates(
            ACTIVE_INDEX_housing_assignment_bed_index, ["bed", "docstatus", "check_out_date"]
        )

    def test_re_declaring_on_an_existing_site_is_an_idempotent_no_op(self):
        """``on_doctype_update`` runs on EVERY migrate. A site that already has
        the indexes must not grow a second copy under the same or a new name."""
        housing_assignment.on_doctype_update()
        before = {
            row["Key_name"]
            for row in frappe.db.sql(f"SHOW INDEX FROM `tab{DOCTYPE_housing_assignment_bed_index}`", as_dict=True)
        }
        housing_assignment.on_doctype_update()
        housing_assignment.on_doctype_update()
        after = {
            row["Key_name"]
            for row in frappe.db.sql(f"SHOW INDEX FROM `tab{DOCTYPE_housing_assignment_bed_index}`", as_dict=True)
        }
        self.assertEqual(after, before, "repeated declaration must add no new index")
        self.assertTrue(
            _indexes_covering_housing_assignment_bed_index(DOCTYPE_housing_assignment_bed_index, ["bed"]),
            "the bed column must stay indexed under some name across re-declaration",
        )
        self.assertIn(ACTIVE_INDEX_housing_assignment_bed_index, after)

    def test_no_patch_is_still_claimed_for_the_bed_index(self):
        """The declaration is the ONLY delivery path for the bed index, and the tree
        must say so: the schema comes from the DocType JSON and
        ``on_doctype_update``, so a legacy ``patches/v0_7/add_bed_assignment_index``
        registration is not required for a site mid-upgrade to get the index. A
        re-registered legacy patch would be the defect: it would race the
        declaration and can only produce a second index for one path.
        """
        app_root = str(Path(apex.__file__).resolve().parent)
        patch_path = os.path.join(
            app_root, "patches", "v0_7", "add_bed_assignment_index.py"
        )
        self.assertFalse(
            os.path.exists(patch_path),
            "the legacy bed-index patch is back; the declaration already owns this index",
        )
        with open(os.path.join(app_root, "patches.txt"), encoding="utf-8") as fh:
            registered = fh.read()
        self.assertNotIn(
            LEGACY_PATCH_housing_assignment_bed_index, registered, "the legacy bed-index patch is registered again"
        )


# --- merged from test_housing_assignment_bed_lock.py ---
BUILDING = "_Test Building"
ROOM = "_T-101"
class TestHousingAssignmentBedLock(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.company = frappe.db.get_value("Building", BUILDING, "company")
        # ERPNext's Project fixture is not idempotent (autoname mints a new name while
        # project_name carries a unique index), so the one already on the site is read.
        self.project = frappe.db.get_value("Project", {"project_name": "_Test Project"})
        self.bed = frappe.db.get_value("Bed", {"room": ROOM, "status": "Available"})
        self.assertTrue(self.bed, "the shipped Bed fixture must provide a free bed")
        # Shared fixtures are handed back: FrappeTestCase rolls back once per CLASS
        # (frappe/tests/utils.py:46), so a bed left Occupied outlives this method.
        self.addCleanup(frappe.db.set_value, "Bed", self.bed, "status", "Available")

    def _employee(self):
        """A fresh Employee every time: the controller refuses a second live assignment
        for the same worker, so a shared one makes this file's result depend on whatever
        else on the bench is currently housing him."""
        return frappe.get_doc({
            "doctype": "Employee",
            "first_name": "_T Bed Lock " + frappe.generate_hash(length=12),
            "company": self.company,
            "status": "Active",
            "gender": "Male",
            "date_of_birth": "1990-01-01",
            "date_of_joining": "2020-01-01",
        }).insert(ignore_permissions=True, ignore_mandatory=True).name

    def _assignment(self, check_in="2026-05-01"):
        doc = frappe.get_doc({
            "doctype": "Housing Assignment",
            "party_type": "Employee",
            "party": self._employee(),
            "building": BUILDING,
            "room": ROOM,
            "bed": self.bed,
            "assignment_type": "New Assignment",
            "stay_type": "Permanent",
            "check_in_date": check_in,
            "project": self.project,
        })
        doc.insert(ignore_permissions=True)
        return doc

    def _submit_capturing_sql(self, doc):
        captured: list[str] = []
        real_sql = frappe.db.sql

        def _recording_sql(query, *args, **kwargs):
            captured.append(str(query))
            return real_sql(query, *args, **kwargs)

        frappe.db.sql = _recording_sql
        try:
            doc.submit()
        finally:
            frappe.db.sql = real_sql
        return captured

    def test_the_bed_status_is_decided_by_a_locking_read(self):
        captured = self._submit_capturing_sql(self._assignment())
        locking = [
            q for q in captured
            if "`tabBed`" in q and "FOR UPDATE" in q.upper() and "SELECT" in q.upper()
        ]
        self.assertTrue(
            locking,
            "submitting an assignment must read Bed.status FOR UPDATE — a plain read "
            f"answers from a snapshot taken before the lock. Captured: {captured}",
        )

    def test_a_bed_taken_after_validate_is_refused_at_submit(self):
        """The other half: the lock is only worth taking if the decision refuses.

        Both drafts are inserted while the bed is free, so the validate-time occupancy
        check passes on both — exactly the window the race opens. Only the submit-time
        locked read stands between them and a double allocation.
        """
        first = self._assignment()
        second = self._assignment(check_in="2026-05-02")

        first.submit()
        self.assertEqual(frappe.db.get_value("Bed", self.bed, "status"), "Occupied")

        with self.assertRaises(frappe.ValidationError) as caught:
            second.submit()
        message = str(caught.exception)
        self.assertIn(self.bed, message)
        self.assertIn(first.name, message)
