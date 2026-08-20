"""Size note: 127 test lines against 32 in the subject (4.0x), for 8 distinct behaviours. The ratio is arithmetic on a small subject, not overtesting: each test names a different behaviour."""
from __future__ import annotations

# Copyright (c) 2026, AFMCO and contributors
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
import apex
from apex.habitat import permissions as P
from apex.tests.factories import make_scoped_supervisor



class TestMaintenanceInspectionReport(FrappeTestCase):

    def test_create_valid_report(self):
        doc = frappe.get_doc({
            "doctype": "Maintenance Inspection Report",
            "naming_series": "MIR-.YYYY.-.####",
            "inspection_date": "2026-06-20",
            "building": "QA-BLDG",
            "inspector": "EMP-QA-001",
            "findings": [{"doctype": "Inspection Finding Item", "description": "crack in wall"}],
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertIsNotNone(doc.name)
        frappe.delete_doc("Maintenance Inspection Report", doc.name, force=True, ignore_permissions=True)

    def test_missing_inspector_raises(self):
        doc = frappe.get_doc({
            "doctype": "Maintenance Inspection Report",
            "naming_series": "MIR-.YYYY.-.####",
            "inspection_date": "2026-06-20",
            "building": "QA-BLDG",
            "findings": [{"doctype": "Inspection Finding Item", "description": "crack in wall"}],
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_empty_findings_raises(self):
        doc = frappe.get_doc({
            "doctype": "Maintenance Inspection Report",
            "inspection_date": "2026-06-20",
            "building": "QA-BLDG",
            "inspector": "EMP-QA-001",
            "findings": [],
        })
        # Links are validated before mandatory (document.py:302 then :310), and the
        # placeholder links below do not exist, so the link check is stood down to keep
        # the assertion on the empty table this test is about.
        doc.flags.ignore_links = True
        with self.assertRaises(frappe.MandatoryError):
            doc.insert(ignore_permissions=True)


class TestMaintenanceInspectionAssetStamp(FrappeTestCase):
    """on_submit stamps the linked Facility Asset's last_inspection_date (most-recent
    wins); on_cancel recomputes it from the remaining submitted inspections."""

    def _h(self):
        return frappe.generate_hash(length=12).upper()

    def setUp(self):
        self.company = frappe.db.get_value("Company", {}) or frappe.get_doc({
            "doctype": "Company", "company_name": "Test Co", "default_currency": "SAR",
            "country": "Saudi Arabia"}).insert(ignore_permissions=True).name
        self.building = frappe.get_doc({
            "doctype": "Building", "building_name": "B " + self._h(),
            "total_capacity": 4, "company": self.company,
        }).insert(ignore_permissions=True, ignore_links=True).name
        self.inspector = frappe.get_doc({
            "doctype": "Employee", "first_name": "Insp " + self._h(), "company": self.company,
            "gender": "Male", "date_of_birth": "1990-01-01", "date_of_joining": "2020-01-01",
        }).insert(ignore_permissions=True).name
        self.asset = frappe.get_doc({
            "doctype": "Facility Asset", "naming_series": "FAC-AST-.YYYY.-.####",
            "asset_name": "Camera " + self._h(), "asset_category": "CCTV Camera",
            "building": self.building, "responsible_supervisor": "Administrator",
        }).insert(ignore_permissions=True, ignore_links=True).name

    def _report(self, inspection_date, facility_asset=None):
        doc = frappe.get_doc({
            "doctype": "Maintenance Inspection Report",
            "naming_series": "MIR-.YYYY.-.####",
            "inspection_date": inspection_date,
            "building": self.building,
            "inspector": self.inspector,
            "facility_asset": facility_asset,
            "findings": [{"doctype": "Inspection Finding Item", "description": "check"}],
        })
        doc.insert(ignore_permissions=True)
        return doc

    def _stamp(self):
        return frappe.db.get_value("Facility Asset", self.asset, "last_inspection_date")

    def test_submit_stamps_asset(self):
        self.assertIsNone(self._stamp())
        r = self._report("2026-06-10", self.asset)
        r.submit()
        self.assertEqual(str(self._stamp()), "2026-06-10")

    def test_only_most_recent_date_wins(self):
        self._report("2026-06-10", self.asset).submit()
        self._report("2026-06-20", self.asset).submit()
        self.assertEqual(str(self._stamp()), "2026-06-20")
        self._report("2026-06-01", self.asset).submit()
        self.assertEqual(str(self._stamp()), "2026-06-20")

    def test_cancel_recomputes_from_remaining(self):
        self._report("2026-06-10", self.asset).submit()
        newest = self._report("2026-06-20", self.asset)
        newest.submit()
        self.assertEqual(str(self._stamp()), "2026-06-20")
        newest.cancellation_reason = "test"
        newest.cancel()
        self.assertEqual(str(self._stamp()), "2026-06-10")

    def test_cancel_only_report_clears_stamp(self):
        only = self._report("2026-06-10", self.asset)
        only.submit()
        self.assertEqual(str(self._stamp()), "2026-06-10")
        only.cancellation_reason = "test"
        only.cancel()
        self.assertIsNone(self._stamp())

    def test_report_without_asset_is_noop(self):
        """No facility_asset means the controller writes to no Facility Asset at all.

        Asserting only that this test's own asset stayed unstamped cannot fail:
        ``frappe.db.set_value`` handed a None docname is treated as a Single and
        writes to ``tabSingles``, never to a Facility Asset row, so removing either
        early return would leave every asset untouched anyway and keep the stamp
        assertions green. The falsifiable statement is the count of Facility Asset
        writes, so the writes are recorded across both the submit and the cancel.
        """
        with patch.object(frappe.db, "set_value", wraps=frappe.db.set_value) as writes:
            r = self._report("2026-06-15", None)
            r.submit()
            r.cancellation_reason = "test"
            r.cancel()

        self.assertEqual(
            [call.args[:2] for call in writes.call_args_list
             if call.args and call.args[0] == "Facility Asset"],
            [],
            "an asset-less inspection must not write to Facility Asset",
        )
        self.assertIsNone(self._stamp())

test_ignore = ['Additional Salary', 'Asset', 'Asset Movement', 'Company', 'Cost Center', 'Currency', 'Employee', 'Item', 'Payment Entry', 'Project', 'Purchase Invoice', 'Role', 'Salary Component', 'Supplier', 'User']


# --- merged from test_maintenance_inspection_report_building_scope.py ---
DOCTYPE = "Maintenance Inspection Report"
QUERY_FN = "apex.habitat.permissions.building_scope_query"
HANDLER = "apex.habitat.permissions.building_scoped_has_permission"
ANCHOR = ("maintenance_work_order", "Maintenance Work Order")
BLD_A = "MIR-BLD-A"
BLD_B = "MIR-BLD-B"
def _h(n=12):
    return frappe.generate_hash(length=n).upper()
def _scoped_to(buildings):
    """Patch the two module-level resolvers to a scoped user holding ``buildings``."""
    return (
        patch.object(P, "_building_is_unscoped", return_value=False),
        patch.object(P, "_allowed_buildings", return_value=list(buildings)),
    )
class TestMaintenanceInspectionReportScopeWiring(unittest.TestCase):
    """Siteless: the two hook entries, the anchor, and the handler's verdicts."""

    APEX = Path(apex.__file__).parent

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from apex import hooks

        cls.hooks = hooks
        cls.json = json.loads(
            (
                cls.APEX
                / "habitat"
                / "doctype"
                / "maintenance_inspection_report"
                / "maintenance_inspection_report.json"
            ).read_text()
        )

    def _field(self, fieldname):
        return next(
            (f for f in self.json["fields"] if f.get("fieldname") == fieldname), None
        )

    def test_the_list_view_is_wired_to_the_building_fragment(self):
        self.assertEqual(
            self.hooks.permission_query_conditions.get(DOCTYPE),
            QUERY_FN,
            "the inspection list has no building scope",
        )

    def test_the_form_and_rest_paths_are_wired_to_the_shared_handler(self):
        self.assertEqual(
            self.hooks.has_permission.get(DOCTYPE),
            HANDLER,
            "an out-of-estate inspection is still openable",
        )

    def test_both_wired_targets_resolve_to_a_callable(self):
        """A typo in a dotted path fails here, not on a customer site."""
        for dotted in (QUERY_FN, HANDLER):
            with self.subTest(dotted=dotted):
                self.assertTrue(callable(getattr(P, dotted.rsplit(".", 1)[1])))

    def test_the_building_field_is_fetched_and_therefore_owes_an_anchor(self):
        """The premise of the whole card, kept falsifiable.

        If someone later makes `building` a plain Link the anchor becomes dead weight
        and this test says so; while it stays fetched, the anchor is mandatory.
        """
        field = self._field("building")
        self.assertIsNotNone(field)
        self.assertEqual(field.get("options"), "Building")
        self.assertEqual(field.get("fetch_from"), "maintenance_work_order.building")
        self.assertIn(DOCTYPE, P.BUILDING_FETCH_ANCHOR)

    def test_the_anchor_names_a_real_link_that_is_not_itself_fetched(self):
        """An anchor that is itself `fetch_from` is empty at :300 too, so it fixes nothing."""
        self.assertEqual(P.BUILDING_FETCH_ANCHOR[DOCTYPE], ANCHOR)
        fieldname, parent_doctype = ANCHOR
        field = self._field(fieldname)
        self.assertIsNotNone(field, "{0} absent".format(fieldname))
        self.assertEqual(field.get("fieldtype"), "Link")
        self.assertEqual(field.get("options"), parent_doctype)
        self.assertFalse(
            field.get("fetch_from"), "{0} is itself fetched".format(fieldname)
        )

    def test_building_is_the_only_building_link_so_no_link_is_over_restricted(self):
        """Why no field here needs `ignore_user_permissions`.

        A Building User Permission auto-filters EVERY Link whose target is Building
        (db_query.py:1083). That is wanted on the scope axis and silently
        over-restricts on any other Building link. This DocType has exactly one.
        """
        building_links = [
            f["fieldname"]
            for f in self.json["fields"]
            if f.get("fieldtype") == "Link" and f.get("options") == "Building"
        ]
        self.assertEqual(building_links, ["building"])

    def test_a_stored_row_is_judged_on_its_own_building_not_the_anchor(self):
        outer, inner = _scoped_to([BLD_A])
        with outer, inner:
            self.assertIsNone(
                P.building_scoped_has_permission(
                    SimpleNamespace(doctype=DOCTYPE, building=BLD_A), "read", user="sup"
                ),
                "a supervisor was denied their own estate",
            )
            self.assertIs(
                P.building_scoped_has_permission(
                    SimpleNamespace(doctype=DOCTYPE, building=BLD_B), "read", user="sup"
                ),
                False,
                "another estate's inspection was readable",
            )

    def test_the_create_path_resolves_through_the_work_order_both_ways(self):
        """The decisive pair: `building` unfetched, verdict taken from the anchor.

        Paired on purpose — a handler that returned None for both would pass the
        positive half while granting a supervisor every estate on create.
        """
        parents = {"MWO-A": BLD_A, "MWO-B": BLD_B}
        outer, inner = _scoped_to([BLD_A])
        db = SimpleNamespace(
            get_value=lambda dt, name, field: parents.get(name)
            if (dt, field) == (ANCHOR[1], "building")
            else None
        )
        # `patch.object` restores the real connection on exit, exception or not --
        # `frappe.db` is a process global that no test rollback would put back.
        with outer, inner, patch.object(frappe, "db", db):
            allowed = P.building_scoped_has_permission(
                SimpleNamespace(
                    doctype=DOCTYPE, building=None, maintenance_work_order="MWO-A"
                ),
                "create",
                user="sup",
            )
            refused = P.building_scoped_has_permission(
                SimpleNamespace(
                    doctype=DOCTYPE, building=None, maintenance_work_order="MWO-B"
                ),
                "create",
                user="sup",
            )
            unresolvable = P.building_scoped_has_permission(
                SimpleNamespace(
                    doctype=DOCTYPE, building=None, maintenance_work_order=None
                ),
                "create",
                user="sup",
            )
        self.assertEqual(
            (allowed, refused, unresolvable),
            (None, False, False),
            "create-path verdicts collapsed: an in-estate create must defer, an "
            "out-of-estate create must be refused, and no anchor at all must fail closed",
        )

    def test_every_action_is_denied_out_of_estate_not_only_read(self):
        outer, inner = _scoped_to([BLD_A])
        with outer, inner:
            for ptype in ("read", "write", "create", "submit", "cancel", "delete"):
                with self.subTest(ptype=ptype):
                    self.assertIs(
                        P.building_scoped_has_permission(
                            SimpleNamespace(doctype=DOCTYPE, building=BLD_B),
                            ptype,
                            user="sup",
                        ),
                        False,
                    )

    def test_oversight_defers_and_a_permissionless_scoped_user_is_denied(self):
        with patch.object(P, "_building_is_unscoped", return_value=True):
            self.assertIsNone(
                P.building_scoped_has_permission(
                    SimpleNamespace(doctype=DOCTYPE, building=BLD_B), "read", user="mgr"
                )
            )
        outer, inner = _scoped_to([])
        with outer, inner:
            self.assertIs(
                P.building_scoped_has_permission(
                    SimpleNamespace(doctype=DOCTYPE, building=BLD_A), "read", user="sup"
                ),
                False,
            )
class TestMaintenanceInspectionReportScopeRuntime(FrappeTestCase):
    """Needs a bench site: real buildings, real work orders, a real User Permission."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.b1 = cls._building()
        cls.b2 = cls._building()
        cls.scoped = make_scoped_supervisor(cls._user, cls.b1, cls.addClassCleanup)
        # Same role, NO Building User Permission -- the user frappe's native match
        # leaves completely unrestricted.
        cls.unpermitted = cls._user("Resident Supervisor")
        cls.oversight = cls._user("Accommodation Manager")

    @classmethod
    def _building(cls):
        doc = frappe.get_doc({"doctype": "Building", "building_name": "MIR-" + _h()})
        doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        cls.addClassCleanup(
            frappe.delete_doc, "Building", doc.name, force=True, ignore_permissions=True
        )
        return doc.name

    @classmethod
    def _user(cls, role):
        email = "mir-{0}@example.com".format(_h()).lower()
        frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": "Scope",
                "send_welcome_email": 0,
                "roles": [{"role": role}],
            }
        ).insert(ignore_permissions=True)
        cls.addClassCleanup(
            frappe.delete_doc, "User", email, force=True, ignore_permissions=True
        )
        return email

    def _work_order(self, building):
        doc = frappe.get_doc(
            {
                "doctype": "Maintenance Work Order",
                "naming_series": "MWO-.YYYY.-.####",
                "building": building,
                "work_description": "Scope probe",
                "planned_start_date": frappe.utils.today(),
            }
        )
        doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        return doc.name

    def _report(self, building):
        doc = frappe.get_doc(
            {
                "doctype": DOCTYPE,
                "naming_series": "MIR-.YYYY.-.####",
                "inspection_date": frappe.utils.today(),
                "building": building,
                "inspector": "Administrator",
                "findings": [
                    {"doctype": "Inspection Finding Item", "description": "probe"}
                ],
            }
        )
        doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
        return doc.name

    def _pair(self):
        return self._report(self.b1), self._report(self.b2)

    def _rows_the_fragment_returns(self, user):
        """The names the desk list would return for ``user``.

        The fragment is exactly what `permission_query_conditions` AND-s into
        `DatabaseQuery`'s WHERE clause, and it is built from `frappe.db.escape`d
        values, so running it verbatim is the same read the list view performs.
        """
        fragment = P.building_scope_query(doctype=DOCTYPE, user=user)
        if fragment == "1=0":
            return set()
        where = " where {0}".format(fragment) if fragment else ""
        return set(
            frappe.db.sql_list(
                "select name from `tabMaintenance Inspection Report`" + where
            )
        )

    def test_the_scoped_list_keeps_this_estate_and_drops_the_other(self):
        mine, theirs = self._pair()
        names = self._rows_the_fragment_returns(self.scoped)
        self.assertIn(mine, names, "the supervisor lost their own estate")
        self.assertNotIn(theirs, names, "another estate's inspection leaked")

    def test_oversight_sees_both_estates(self):
        """The control that stops a deny-everything fragment from passing."""
        mine, theirs = self._pair()
        names = self._rows_the_fragment_returns(self.oversight)
        self.assertIn(mine, names)
        self.assertIn(theirs, names)

    def test_a_supervisor_with_no_building_permission_sees_nothing(self):
        """The hole the fragment exists to close: frappe's native match adds NO
        condition for a user holding no Building User Permission."""
        mine, theirs = self._pair()
        self.assertEqual(P.building_scope_query(doctype=DOCTYPE, user=self.unpermitted), "1=0")
        names = self._rows_the_fragment_returns(self.unpermitted)
        self.assertNotIn(mine, names)
        self.assertNotIn(theirs, names)

    def test_the_fragment_names_the_building_column_and_only_this_estate(self):
        fragment = P.building_scope_query(doctype=DOCTYPE, user=self.scoped)
        self.assertIn("`building`", fragment)
        self.assertIn(self.b1, fragment)
        self.assertNotIn(self.b2, fragment)
        self.assertEqual(P.building_scope_query(doctype=DOCTYPE, user=self.oversight), "")

    def test_the_controller_hook_opens_this_estate_and_denies_the_other(self):
        """Isolates the hook from frappe's native check, which would deny the same
        document on its own and so cannot prove the wiring."""
        mine, theirs = self._pair()
        self.assertIsNone(
            P.building_scoped_has_permission(
                frappe.get_doc(DOCTYPE, mine), "read", user=self.scoped
            )
        )
        self.assertIs(
            P.building_scoped_has_permission(
                frappe.get_doc(DOCTYPE, theirs), "read", user=self.scoped
            ),
            False,
        )

    def test_a_create_with_building_unfetched_is_decided_by_the_work_order(self):
        """The create path against real rows, both ways.

        `frappe.get_doc` applies no `fetch_from` -- that runs in `_validate_links()`
        during insert -- so `building` here is genuinely empty at the moment
        `check_permission("create")` would read it.
        """
        for building, expected in ((self.b1, None), (self.b2, False)):
            with self.subTest(building=building):
                draft = frappe.get_doc(
                    {
                        "doctype": DOCTYPE,
                        "naming_series": "MIR-.YYYY.-.####",
                        "inspection_date": frappe.utils.today(),
                        "inspector": "Administrator",
                        "maintenance_work_order": self._work_order(building),
                    }
                )
                self.assertFalse(draft.get("building"), "fetch_from ran too early")
                self.assertIs(
                    P.building_scoped_has_permission(draft, "create", user=self.scoped),
                    expected,
                )
if __name__ == "__main__":
    unittest.main(verbosity=2)
