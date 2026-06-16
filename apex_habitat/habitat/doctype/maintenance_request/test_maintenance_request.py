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


class TestMaintenanceRequest(FrappeTestCase):

    def test_create_valid_request(self):
        doc = frappe.get_doc({
            "doctype": "Maintenance Request",
            "naming_series": "MAINT-.YYYY.-.#####",
            "building": "QA-BLDG",
            "room": "ROOM-QA",
            "reported_by": "Administrator",
            "issue_type": "Plumbing",
            "issue_description": "Leak under sink",
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertEqual(doc.issue_type, "Plumbing")
        frappe.delete_doc("Maintenance Request", doc.name, force=True, ignore_permissions=True)

    def test_missing_room_raises(self):
        doc = frappe.get_doc({
            "doctype": "Maintenance Request",
            "naming_series": "MAINT-.YYYY.-.#####",
            "building": "QA-BLDG",
            "reported_by": "Administrator",
            "issue_type": "Electrical",
            "issue_description": "Wiring problem",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_missing_issue_description_raises(self):
        doc = frappe.get_doc({
            "doctype": "Maintenance Request",
            "naming_series": "MAINT-.YYYY.-.#####",
            "building": "QA-BLDG",
            "room": "ROOM-QA",
            "reported_by": "Administrator",
            "issue_type": "Plumbing",
        })
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_reported_by_defaults_to_session_user(self):
        # [#nxhfil]
        doc = frappe.get_doc({
            "doctype": "Maintenance Request",
            "naming_series": "MAINT-.YYYY.-.#####",
            "building": "QA-BLDG",
            "room": "ROOM-QA",
            "issue_type": "Plumbing",
            "issue_description": "Leak under sink",
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        # [#4cntn7]
        self.assertEqual(doc.reported_by, frappe.session.user)
        self.assertEqual(doc.owner, frappe.session.user)
        self.assertEqual(doc.owner, doc.reported_by)
        frappe.delete_doc("Maintenance Request", doc.name, force=True, ignore_permissions=True)

    def test_reported_by_default_is_idempotent_on_update(self):
        # [#kl4vyk]
        doc = frappe.get_doc({
            "doctype": "Maintenance Request",
            "naming_series": "MAINT-.YYYY.-.#####",
            "building": "QA-BLDG",
            "room": "ROOM-QA",
            "reported_by": "Administrator",
            "issue_type": "Plumbing",
            "issue_description": "Leak under sink",
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertEqual(doc.reported_by, "Administrator")
        doc.priority = "High"
        doc.save(ignore_permissions=True)
        self.assertEqual(doc.reported_by, "Administrator")
        frappe.delete_doc("Maintenance Request", doc.name, force=True, ignore_permissions=True)

    # [#h5zcoh]

    def _get_perms_by_role(self):
        """Return a dict mapping role name -> document-level (permlevel 0) perm row.

        Only permlevel-0 rows are indexed. T-093 (owner-approved) added permlevel-1
        DocPerm grants (System Manager, Finance Manager, Accommodation Manager) to gate the
        sensitive cost fields; those rows share a role name with the base rows, so a
        flat ``{p.role: p}`` map would let a permlevel-1 row clobber the permlevel-0
        one being asserted here. These tests assert document-level access, so the
        field-level grants are filtered out of this lookup (see
        ``test_field_level_cost_grants`` for the permlevel-1 assertions).

        Accommodation Manager holds BOTH a permlevel-0 row (document access) and a
        permlevel-1 row (T-093 cost-field grant); filtering to permlevel 0 here keeps
        the document-level assertions reading the correct row."""
        meta = frappe.get_meta("Maintenance Request")
        return {p.role: p for p in meta.permissions if (p.permlevel or 0) == 0}

    def test_all_role_row_exists_with_create_and_if_owner(self):
        """'All' role must grant create:1 and if_owner:1 (universal owner-scoped intake)."""
        perms = self._get_perms_by_role()
        self.assertIn("All", perms, "Expected an 'All' role permission row")
        p = perms["All"]
        self.assertEqual(p.read, 1, "'All' role must have read:1")
        self.assertEqual(p.create, 1, "'All' role must have create:1")
        self.assertEqual(p.if_owner, 1, "'All' role must have if_owner:1")
        self.assertEqual(p.write, 0, "'All' role must NOT have write:1")
        self.assertEqual(p.delete, 0, "'All' role must NOT have delete:1")
        self.assertEqual(p.submit, 0, "'All' role must NOT have submit:1")
        self.assertEqual(p.cancel, 0, "'All' role must NOT have cancel:1")

    def test_maintenance_technician_row_is_read_only(self):
        """'Maintenance Technician' role must be read-only on Maintenance Request."""
        perms = self._get_perms_by_role()
        self.assertIn("Maintenance Technician", perms,
                      "Expected a 'Maintenance Technician' permission row")
        p = perms["Maintenance Technician"]
        self.assertEqual(p.read, 1, "'Maintenance Technician' must have read:1")
        self.assertEqual(p.write, 0, "'Maintenance Technician' must NOT have write:1")
        self.assertEqual(p.create, 0, "'Maintenance Technician' must NOT have create:1")
        self.assertEqual(p.delete, 0, "'Maintenance Technician' must NOT have delete:1")
        self.assertEqual(p.submit, 0, "'Maintenance Technician' must NOT have submit:1")

    def test_resident_request_coordinator_row_has_create_write_submit(self):
        """'Resident Request Coordinator' must have create/read/write/submit but no delete."""
        perms = self._get_perms_by_role()
        self.assertIn("Resident Request Coordinator", perms,
                      "Expected a 'Resident Request Coordinator' permission row")
        p = perms["Resident Request Coordinator"]
        self.assertEqual(p.read, 1, "'Resident Request Coordinator' must have read:1")
        self.assertEqual(p.create, 1, "'Resident Request Coordinator' must have create:1")
        self.assertEqual(p.write, 1, "'Resident Request Coordinator' must have write:1")
        self.assertEqual(p.submit, 1, "'Resident Request Coordinator' must have submit:1")
        self.assertEqual(p.delete, 0, "'Resident Request Coordinator' must NOT have delete:1")

    def test_existing_privileged_roles_untouched(self):
        """System Manager, Accommodation Manager, Resident Supervisor rows must be unchanged."""
        perms = self._get_perms_by_role()
        # [#4msost]
        sm = perms.get("System Manager")
        self.assertIsNotNone(sm)
        self.assertEqual(sm.cancel, 1)
        self.assertEqual(sm.delete, 1)
        self.assertEqual(sm.submit, 1)
        # [#lvwyw7]
        am = perms.get("Accommodation Manager")
        self.assertIsNotNone(am)
        self.assertEqual(am.create, 1)
        self.assertEqual(am.read, 1)
        self.assertEqual(am.write, 1)
        self.assertEqual(am.submit, 1)
        self.assertEqual(am.delete, 0)
        # [#mix057]
        rs = perms.get("Resident Supervisor")
        self.assertIsNotNone(rs)
        self.assertEqual(rs.create, 1)
        self.assertEqual(rs.read, 1)
        self.assertEqual(rs.write, 1)
        self.assertEqual(rs.submit, 1)
        self.assertEqual(rs.delete, 0)

    def test_field_level_cost_grants(self):
        """T-093: the sensitive cost fields (Financial section: cost_of_repair,
        cost_center) are gated at permlevel 1, readable/writable only by the
        approved field-level roles — System Manager, Finance Manager, and
        Accommodation Manager — and by no one else. These are the owner-approved
        permlevel-1 DocPerm grants; this test locks the exact grant set."""
        meta = frappe.get_meta("Maintenance Request")
        level1 = {p.role: p for p in meta.permissions if (p.permlevel or 0) == 1}
        self.assertEqual(
            set(level1),
            {"System Manager", "Finance Manager", "Accommodation Manager"},
            "permlevel-1 cost-field grant roles drifted from the approved set",
        )
        for role, p in level1.items():
            self.assertEqual(p.read, 1, f"{role} must have permlevel-1 read")
            self.assertEqual(p.write, 1, f"{role} must have permlevel-1 write")
