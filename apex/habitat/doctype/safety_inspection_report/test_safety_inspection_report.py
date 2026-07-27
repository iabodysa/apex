# Copyright (c) 2026, AFMCO and contributors
import json
import os

import frappe
from frappe.tests.utils import FrappeTestCase

# [#8evoal]
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

    # [#bd7wcm]

    def _ensure_location(self):
        """Create real Accommodation Building + Room records so the Maintenance
        Requests spawned server-side (which validate their Link targets) pass.
        ignore_links keeps the prerequisites' own external links (e.g. company)
        from needing ERPNext in CI."""
        if not frappe.db.exists("Building", "T103-BLDG"):
            frappe.get_doc({
                "doctype": "Building",
                "building_name": "T103-BLDG",
                # [#tm0kvn]
                "total_capacity": 10,
            }).insert(ignore_permissions=True, ignore_links=True)
        if not frappe.db.exists("Room", "T103-ROOM"):
            # [#64yd4v]
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
            # [#mlfw3r]
            findings.append({
                "finding_category": "General",
                "description": "Observation only, no ticket",
                "room": room,
                "status": "Open",
            })
            # [#53hh0m]
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
            # [#if0ax8]
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
            # [#2xwysp]
            self.assertEqual(len(mrs), n,
                             f"expected {n} Maintenance Requests, got {len(mrs)}")
            for mr in mrs:
                self.assertEqual(mr.room, room)
                self.assertEqual(mr.building, building)
                self.assertEqual(mr.issue_type, "Plumbing")
                self.assertEqual(mr.priority, "High")

            # [#5fy3ci]
            report.reload()
            self.assertEqual(len(report.linked_maintenance_requests), n)
            surfaced = {r.maintenance_request for r in report.linked_maintenance_requests}
            self.assertEqual(surfaced, {m.name for m in mrs})

            # [#578w7r]
            linked_findings = [f for f in report.safety_findings
                               if f.generated_maintenance_request]
            self.assertEqual(len(linked_findings), n)

            # [#ghcv4q]
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
    """[T-281] Safety Inspection Report is deprecated in place (not renamed or
    deleted) in favour of Safety Round + the Safety Task Compliance Summary report.
    These are pure-file assertions on the DocType JSON, so they hold whether or
    not the running site has migrated the schema."""

    def _schema(self):
        path = os.path.join(
            os.path.dirname(__file__), "safety_inspection_report.json"
        )
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)

    def test_sir_json_is_read_only(self):
        """``read_only`` is the whole of the concealment; it used to assert ``hidden`` too.

        Frappe has no root ``hidden`` property on a DocType -- it is absent from
        frappe/core/doctype/doctype/doctype.json, so BaseDocument.get_valid_dict never
        persists it. Asserting it proved only that the JSON still carried a key nothing
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
        # [#n997m7]
        schema = self._schema()
        self.assertEqual(schema.get("name"), "Safety Inspection Report")
        fieldnames = {f.get("fieldname") for f in schema.get("fields", [])}
        for required in ("building", "inspection_date", "inspector", "safety_findings"):
            self.assertIn(required, fieldnames, f"SIR lost field {required}")
