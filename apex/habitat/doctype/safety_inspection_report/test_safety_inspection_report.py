# Copyright (c) 2026, AFMCO and contributors
from __future__ import annotations
import json
import os

import frappe
from frappe.tests.utils import FrappeTestCase

import apex
import ast
import glob
import unittest
from apex.tests.source_tree import APP_ROOT, parse, production_py_files, rel



class TestSafetyInspectionReport(FrappeTestCase):

    def test_docperm_safety_officer(self):
        """Safety Officer must have read/write/create on Safety Inspection Report (no submit)."""
        meta = frappe.get_meta("Safety Inspection Report")
        roles = {p.role: p for p in meta.permissions}
        self.assertIn("Safety Officer", roles, "Safety Officer perm row is missing")
        p = roles["Safety Officer"]
        self.assertEqual(p.read, 1)
        self.assertEqual(p.write, 1)
        self.assertEqual(p.create, 1)
        self.assertFalse(getattr(p, "submit", 0), "Safety Officer must NOT have submit on SIR")

    def _user_with_role(self, role):
        return frappe.get_doc({
            "doctype": "User",
            "email": f"sir_{frappe.generate_hash(length=12)}@example.com",
            "first_name": role.split()[0],
            "roles": [{"role": role}],
        }).insert(ignore_permissions=True).name

    def test_a_role_holding_create_is_not_offered_the_new_action(self):
        """The deprecation withdraws the New action without touching a DocPerm row.

        The Desk decides whether to offer New from `frappe.boot.user.can_create`
        (frappe/public/js/frappe/model/model.js:366, and the awesomebar's "New X" at
        search_utils.js:161). Root `in_create` diverts a DocType out of that list into a
        separate `in_create` list (frappe/utils/user.py:132-133), then folds that list
        straight back into `can_write` (:172) -- so every draft already in flight stays
        editable and submittable, and only the offer to open a NEW one goes away.

        Withdrawing the affordance rather than the row is the deliberate half. Revoking
        `create` from the DocPerm rows would take amend with it: `insert` checks the
        create right for an amended document too (frappe/model/document.py:300), so a
        submitted report could never be corrected again.

        Safety Round is the control -- the same user holds create on the successor, so
        the boot payload is not simply empty and the absence below is about this DocType.
        """
        user = self._user_with_role("Safety Officer")
        # Process state, and no rollback restores it: register the undo before the change.
        self.addCleanup(frappe.set_user, "Administrator")
        frappe.set_user(user)
        # Built for the SESSION user: build_perm_map resolves roles through get_valid_perms,
        # which falls back to frappe.session.user (frappe/permissions.py:467-469). Asking
        # for another user's payload while Administrator holds the session returns
        # Administrator's rights under that user's name.
        boot = frappe.get_user().load_user()

        self.assertIn(
            "Safety Round", boot["can_create"],
            "control failed: the role lost create on the successor, so the assertion "
            "below would pass for a reason that has nothing to do with in_create",
        )
        self.assertNotIn(
            "Safety Inspection Report", boot["can_create"],
            "the Desk still offers New on the deprecated report -- root in_create was "
            "dropped from safety_inspection_report.json, or the site has not migrated",
        )
        self.assertIn(
            "Safety Inspection Report", boot["in_create"],
            "the report is absent from BOTH boot lists, which means the role lost its "
            "DocPerm create row rather than being diverted out of the New action",
        )
        self.assertIn(
            "Safety Inspection Report", boot["can_write"],
            "the reports already filed went read-only for the role that owns them",
        )
        self.assertTrue(
            frappe.has_permission("Safety Inspection Report", "create", user=user),
            "the DocPerm create rows were revoked as well -- amending a submitted report "
            "needs the create right, and every server-side writer starts throwing",
        )

    def test_create_valid_inspection(self):
        doc = frappe.get_doc({
            "doctype": "Safety Inspection Report",
            "naming_series": "FSI-.YYYY.-.#####",
            "building": "QA-BLDG",
            "inspection_date": "2026-06-15",
            "inspector": "Administrator",
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertIsNotNone(doc.name)
        frappe.delete_doc("Safety Inspection Report", doc.name, force=True, ignore_permissions=True)

    def test_missing_building_raises(self):
        doc = frappe.get_doc({
            "doctype": "Safety Inspection Report",
            "naming_series": "FSI-.YYYY.-.#####",
            "inspection_date": "2026-06-15",
            "inspector": "Administrator",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_missing_inspector_raises(self):
        doc = frappe.get_doc({
            "doctype": "Safety Inspection Report",
            "naming_series": "FSI-.YYYY.-.#####",
            "building": "QA-BLDG",
            "inspection_date": "2026-06-15",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)


    def _ensure_location(self):
        """Create real Accommodation Building + Room records so the Maintenance
        Requests spawned server-side (which validate their Link targets) pass.
        ignore_links keeps the prerequisites' own external links (e.g. company)
        from needing ERPNext in CI."""
        if not frappe.db.exists("Building", "T103-BLDG"):
            frappe.get_doc({
                "doctype": "Building",
                "building_name": "T103-BLDG",
                "total_capacity": 10,
            }).insert(ignore_permissions=True, ignore_links=True)
        if not frappe.db.exists("Room", "T103-ROOM"):
            frappe.get_doc({
                "doctype": "Room",
                "building": "T103-BLDG",
                "room_number": "T103-ROOM",
                "bed_capacity": 2,
            }).insert(ignore_permissions=True, ignore_links=True)
        return "T103-BLDG", "T103-ROOM"

    def _make_report(self, building, room, n_actionable, with_noise=True):
        """Build (unsaved) a report with n_actionable actionable findings, plus,
        optionally, non-actionable noise rows that must NOT spawn tickets:
        a finding with no issue_type, and a Resolved finding."""
        findings = []
        for i in range(n_actionable):
            findings.append({
                "finding_category": "Maintenance",
                "severity": "High",
                "description": f"Actionable finding {i}",
                "issue_type": "Plumbing",
                "room": room,
                "priority": "High",
                "status": "Open",
            })
        if with_noise:
            findings.append({
                "finding_category": "General",
                "description": "Observation only, no ticket",
                "room": room,
                "status": "Open",
            })
            findings.append({
                "finding_category": "Maintenance",
                "description": "Already fixed on the spot",
                "issue_type": "Electrical",
                "room": room,
                "status": "Resolved",
            })
        return frappe.get_doc({
            "doctype": "Safety Inspection Report",
            "naming_series": "FSI-.YYYY.-.#####",
            "building": building,
            "inspection_date": "2026-06-15",
            "inspector": "Administrator",
            "safety_findings": findings,
        })

    def _cleanup_report(self, report_name):
        for mr in frappe.get_all("Maintenance Request",
                                 filters={"source_inspection": report_name}, pluck="name"):
            frappe.delete_doc("Maintenance Request", mr, force=True, ignore_permissions=True)
        if frappe.db.exists("Safety Inspection Report", report_name):
            report = frappe.get_doc("Safety Inspection Report", report_name)
            if report.docstatus == 1:
                report.cancel()
            frappe.delete_doc("Safety Inspection Report", report_name,
                              force=True, ignore_permissions=True)

    def test_submit_fans_out_one_mr_per_actionable_finding_idempotent(self):
        """Submitting a report with N actionable findings creates exactly N
        Maintenance Requests, surfaces them, stamps the back-links, and a second
        fan-out pass (idempotency) creates no duplicates."""
        building, room = self._ensure_location()
        n = 3
        report = self._make_report(building, room, n)
        report.insert(ignore_permissions=True)
        report.submit()

        try:
            mrs = frappe.get_all(
                "Maintenance Request",
                filters={"source_inspection": report.name},
                fields=["name", "room", "building", "issue_type", "priority"],
            )
            self.assertEqual(len(mrs), n,
                             f"expected {n} Maintenance Requests, got {len(mrs)}")
            for mr in mrs:
                self.assertEqual(mr.room, room)
                self.assertEqual(mr.building, building)
                self.assertEqual(mr.issue_type, "Plumbing")
                self.assertEqual(mr.priority, "High")

            report.reload()
            self.assertEqual(len(report.linked_maintenance_requests), n)
            surfaced = {r.maintenance_request for r in report.linked_maintenance_requests}
            self.assertEqual(surfaced, {m.name for m in mrs})

            linked_findings = [f for f in report.safety_findings
                               if f.generated_maintenance_request]
            self.assertEqual(len(linked_findings), n)

            report.generate_maintenance_requests()
            mrs_after = frappe.get_all("Maintenance Request",
                                       filters={"source_inspection": report.name}, pluck="name")
            self.assertEqual(len(mrs_after), n, "idempotency violated: duplicate MRs created")
            report.reload()
            self.assertEqual(len(report.linked_maintenance_requests), n,
                             "idempotency violated: duplicate surfacing rows")
        finally:
            self._cleanup_report(report.name)

    def test_safety_section_clear_creates_no_mr(self):
        """A report flagged 'Safety Section — No Issues' spawns nothing even if
        finding rows are present."""
        building, room = self._ensure_location()
        report = self._make_report(building, room, 2, with_noise=False)
        report.safety_section_clear = 1
        report.insert(ignore_permissions=True)
        report.submit()
        try:
            mrs = frappe.get_all("Maintenance Request",
                                 filters={"source_inspection": report.name}, pluck="name")
            self.assertEqual(len(mrs), 0)
            report.reload()
            self.assertEqual(len(report.linked_maintenance_requests), 0)
        finally:
            self._cleanup_report(report.name)


class TestSafetyInspectionReportDeprecation(FrappeTestCase):
    """Safety Inspection Report is deprecated in place (not renamed or
    deleted) in favour of Safety Round + the Safety Task Compliance Summary report.
    These are pure-file assertions on the DocType JSON, so they hold whether or
    not the running site has migrated the schema."""

    def _schema(self):
        # The suite lives outside the app, so the DocType JSON is no longer beside this
        # file; it is resolved from the installed package instead.
        path = os.path.join(
            os.path.dirname(apex.__file__),
            "habitat",
            "doctype",
            "safety_inspection_report",
            "safety_inspection_report.json",
        )
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)

    def test_sir_json_is_read_only(self):
        """``read_only`` is the whole of the concealment; ``hidden`` is not, because
        Frappe has no root ``hidden`` property on a DocType -- it is absent from
        frappe/core/doctype/doctype/doctype.json, so BaseDocument.get_valid_dict never
        persists it. Asserting it would prove only that the JSON carries a key nothing
        reads. ``read_only`` is the honoured one: frappe labels it "User Cannot Search"
        and frappe/utils/user.py drops such a doctype from can_search and can_read.
        """
        schema = self._schema()
        self.assertEqual(schema.get("read_only"), 1, "SIR must be read_only")
        self.assertNotIn("hidden", schema, "root 'hidden' is inert; do not re-add it")

    def test_sir_description_marks_deprecation(self):
        schema = self._schema()
        self.assertIn("Deprecated", schema.get("description", ""),
                      "SIR description must mark it as deprecated")
        self.assertIn("Safety Round", schema.get("description", ""),
                      "SIR description must point to Safety Round")

    def test_sir_not_renamed_and_fields_intact(self):
        schema = self._schema()
        self.assertEqual(schema.get("name"), "Safety Inspection Report")
        fieldnames = {f.get("fieldname") for f in schema.get("fields", [])}
        for required in ("building", "inspection_date", "inspector", "safety_findings"):
            self.assertIn(required, fieldnames, f"SIR lost field {required}")

test_ignore = ['Additional Salary', 'Asset', 'Asset Movement', 'Company', 'Cost Center', 'Currency', 'Employee', 'Item', 'Payment Entry', 'Project', 'Purchase Invoice', 'Role', 'Salary Component', 'Supplier', 'User']


# --- merged from test_safety_inspection_report_retired.py ---
DEPRECATED = "Safety Inspection Report"
REPLACEMENT = "Safety Round"
SAFETY_MAP_PY = os.path.join(APP_ROOT, "habitat", "api", "safety_map.py")
SAFETY_MAP_JS = os.path.join(APP_ROOT, "habitat", "page", "safety_map", "safety_map.js")
RETIRED_ENDPOINT = "log_building_inspection"
SELF = os.path.join("habitat", "doctype", "safety_inspection_report")
def _creates(tree):
    """DocType names this module constructs: ``{"doctype": X}`` dict literals and
    ``new_doc(X)`` / ``get_doc(X, ...)`` leading arguments.

    A creation SITE, not a mention. finding_fanout names the doctype in a
    comparison (``source_doc.doctype == _SIR_DOCTYPE``) to decide which back-link
    to stamp, and building_operations_summary names it in a ``get_all`` filter to
    count history — both are legitimate and neither builds anything.
    """
    built = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and key.value == "doctype":
                    if isinstance(value, ast.Constant) and isinstance(value.value, str):
                        built.add(value.value)
        elif isinstance(node, ast.Call):
            name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
            if name in ("new_doc", "get_doc") and node.args:
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    built.add(first.value)
    return built
def _shipped_doctype_schemas():
    """``(path, schema)`` for every DocType JSON apex ships."""
    found = []
    pattern = os.path.join(APP_ROOT, "**", "doctype", "*", "*.json")
    for path in sorted(glob.glob(pattern, recursive=True)):
        with open(path, encoding="utf-8") as handle:
            try:
                schema = json.load(handle)
            except ValueError:
                continue
        if isinstance(schema, dict) and "fields" in schema and "module" in schema:
            found.append((path, schema))
    return found
class TestNoProductionCodeCreatesTheReport(unittest.TestCase):
    def setUp(self):
        self.modules = production_py_files()

    def test_the_scan_is_non_vacuous(self):
        """"Nothing found" is what a broken scan reports too, so the absence only
        means something once the scan is shown to see a real creation site."""
        self.assertGreater(len(self.modules), 100, "the production-module scan is empty")
        tree = parse(os.path.join(APP_ROOT, "habitat", "api", "safety_checklist.py"))
        self.assertIsNotNone(tree, "safety_checklist.py did not parse")
        self.assertIn(
            REPLACEMENT,
            _creates(tree),
            "the AST scan cannot see safety_checklist building a Safety Round, so it "
            "would not see a Safety Inspection Report being built either",
        )

    def test_no_production_module_builds_the_deprecated_report(self):
        offenders = []
        for path in self.modules:
            tree = parse(path)
            if tree is not None and DEPRECATED in _creates(tree):
                offenders.append(rel(path))
        self.assertEqual(
            offenders,
            [],
            "{0} is deprecated in favour of {1} and nothing may produce a new one. "
            "Record the finding on a {1} + its Safety Task Execution rows, which "
            "carry the maker-checker gate. Offenders: {2}".format(
                DEPRECATED, REPLACEMENT, offenders
            ),
        )
class TestSafetyMapWritesNothing(unittest.TestCase):
    """The surface that kept the record alive: a whitelisted POST that inserted
    AND submitted one report per click, from the same session that authored it."""

    def test_the_retired_endpoint_is_gone(self):
        tree = parse(SAFETY_MAP_PY)
        self.assertIsNotNone(tree, "safety_map.py did not parse")
        names = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertIn("get_safety_map", names, "the reader is gone too — wrong file?")
        self.assertNotIn(
            RETIRED_ENDPOINT,
            names,
            "safety_map.{0} built and submitted a {1}; it is retired and the page "
            "routes its tiles to {2} instead".format(RETIRED_ENDPOINT, DEPRECATED, REPLACEMENT),
        )

    def test_the_desk_page_calls_no_retired_endpoint(self):
        with open(SAFETY_MAP_JS, encoding="utf-8") as handle:
            source = handle.read()
        self.assertIn(
            "apex.habitat.api.safety_map.get_safety_map",
            source,
            "the page calls no safety_map endpoint at all — the scan is reading the "
            "wrong file",
        )
        self.assertNotIn(
            RETIRED_ENDPOINT,
            source,
            "the Safety Map page still calls the retired inspection writer",
        )
class TestNoFormDashboardOffersTheReport(unittest.TestCase):
    """A DocType ``links`` row is a live entry point, not decoration: Frappe renders
    the connection with a create affordance for any role holding create, which is
    every role on this record. Building offered one, and Maintenance Request offered
    a second through the report's child table."""

    def setUp(self):
        self.schemas = _shipped_doctype_schemas()

    def test_the_scan_is_non_vacuous(self):
        self.assertGreater(len(self.schemas), 100, "the DocType JSON scan is empty")
        by_name = {schema.get("name"): schema for _p, schema in self.schemas}
        self.assertIn("Building", by_name, "the scan does not see Building")
        targets = {row.get("link_doctype") for row in by_name["Building"].get("links") or []}
        self.assertIn(
            REPLACEMENT,
            targets,
            "Building no longer offers the replacement connection the deprecated one "
            "was swapped for — the scan is not reading links rows",
        )

    def test_no_doctype_links_to_the_deprecated_report(self):
        offenders = []
        for path, schema in self.schemas:
            if SELF in path:
                continue
            for row in schema.get("links") or []:
                if DEPRECATED in (row.get("link_doctype"), row.get("parent_doctype")):
                    offenders.append("{0} -> {1}".format(rel(path), row))
        self.assertEqual(
            offenders,
            [],
            "a form-dashboard connection to {0} is an entry point that offers the "
            "deprecated record for creation; connect {1} instead: {2}".format(
                DEPRECATED, REPLACEMENT, offenders
            ),
        )
if __name__ == "__main__":
    unittest.main()
