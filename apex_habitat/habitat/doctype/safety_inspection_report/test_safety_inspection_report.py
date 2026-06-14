import frappe
from frappe.tests.utils import FrappeTestCase

# Prevent Frappe test runner from recursively resolving Link-field dependencies
# on external DocTypes that require ERPNext (not installed in CI bench).
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

    # ------------------------------------------------------------------
    # T-103: on_submit fan-out — one Maintenance Request per actionable finding
    # ------------------------------------------------------------------

    def _ensure_location(self):
        """Create real Accommodation Building + Room records so the Maintenance
        Requests spawned server-side (which validate their Link targets) pass.
        ignore_links keeps the prerequisites' own external links (e.g. company)
        from needing ERPNext in CI."""
        if not frappe.db.exists("Accommodation Building", "T103-BLDG"):
            frappe.get_doc({
                "doctype": "Accommodation Building",
                "building_name": "T103-BLDG",
                # total_capacity is auto-derived (read-only); a value supplied here is
                # harmless and keeps the fixture explicit (status defaults to Active).
                "total_capacity": 10,
            }).insert(ignore_permissions=True, ignore_links=True)
        if not frappe.db.exists("Accommodation Room", "T103-ROOM"):
            # Accommodation Room autonames from room_number (field:room_number),
            # so naming the room "T103-ROOM" pins the docname directly - no
            # post-insert rename. rename_doc(force=True) commits, which would
            # leak this row past the per-test rollback and collide on the next
            # test's insert; setting the name up front keeps the fixture
            # rollback-clean and the existence guard above accurate.
            frappe.get_doc({
                "doctype": "Accommodation Room",
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
            # No issue_type -> not actionable.
            findings.append({
                "finding_category": "General",
                "description": "Observation only, no ticket",
                "room": room,
                "status": "Open",
            })
            # Resolved -> not actionable even with an issue_type.
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
            # The report is submitted (the fan-out runs on_submit). delete_doc's
            # force flag only bypasses the link check, not the submitted guard, so
            # a submitted doc must be cancelled before it can be deleted.
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
            # N actionable -> N tickets (noise rows produced none).
            self.assertEqual(len(mrs), n,
                             f"expected {n} Maintenance Requests, got {len(mrs)}")
            for mr in mrs:
                self.assertEqual(mr.room, room)
                self.assertEqual(mr.building, building)
                self.assertEqual(mr.issue_type, "Plumbing")
                self.assertEqual(mr.priority, "High")

            # Surfaced in the linked table, one row per ticket.
            report.reload()
            self.assertEqual(len(report.linked_maintenance_requests), n)
            surfaced = {r.maintenance_request for r in report.linked_maintenance_requests}
            self.assertEqual(surfaced, {m.name for m in mrs})

            # Back-link stamped on each actionable finding.
            linked_findings = [f for f in report.safety_findings
                               if f.generated_maintenance_request]
            self.assertEqual(len(linked_findings), n)

            # Idempotency: a second fan-out pass on the submitted doc must add no
            # tickets and no surfacing rows (every actionable finding is already
            # linked to a live MR).
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
