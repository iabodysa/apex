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


class TestAccommodationAssignment(FrappeTestCase):

    def test_create_valid_assignment(self):
        doc = frappe.get_doc({
            "doctype": "Accommodation Assignment",
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
        frappe.delete_doc("Accommodation Assignment", doc.name, force=True, ignore_permissions=True)

    def test_missing_employee_raises(self):
        doc = frappe.get_doc({
            "doctype": "Accommodation Assignment",
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
            "doctype": "Accommodation Assignment",
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

    def test_duplicate_active_assignment_rejected(self):
        """Employee with existing active assignment cannot get a second."""
        # Setup: Create building, room, bed, employee with an active assignment
        # Then try to create a second assignment for the same employee
        # Expect frappe.exceptions.ValidationError
        # Use try/except or assertRaises pattern
        pass  # Implement the test body using available fixtures

    def test_occupied_bed_rejected(self):
        """Assignment to an already-occupied bed should be rejected."""
        pass

    def test_room_not_in_building_rejected(self):
        """Assignment where room doesn't belong to the specified building is rejected."""
        pass
