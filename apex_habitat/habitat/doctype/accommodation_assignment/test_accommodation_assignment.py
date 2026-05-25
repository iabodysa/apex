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

    def _h(self):
        return frappe.generate_hash(length=4).upper()

    def _fixtures(self):
        """Create a real, internally-consistent building/room/bed/employee/project
        set so the controller's validate() runs in full (not the link-ignored stubs)."""
        company = frappe.db.get_value("Company", {}) or frappe.get_doc({
            "doctype": "Company", "company_name": "Test Co", "default_currency": "SAR",
            "country": "Saudi Arabia"}).insert(ignore_permissions=True).name
        cc = frappe.db.get_value("Cost Center", {"is_group": 0, "company": company}) or frappe.db.get_value("Cost Center", {"is_group": 0})
        site = frappe.get_doc({"doctype": "Accommodation Site", "site_name": self._h() + self._h()}).insert(ignore_permissions=True).name
        building = frappe.get_doc({"doctype": "Accommodation Building", "building_name": "B " + self._h(),
                                   "site": site, "total_capacity": 4, "company": company,
                                   "default_cost_center": cc}).insert(ignore_permissions=True).name
        room = frappe.get_doc({"doctype": "Accommodation Room", "naming_series": "ROOM-.####", "building": building,
                               "room_number": "R" + self._h(), "bed_capacity": 4,
                               "readiness_status": "Ready"}).insert(ignore_permissions=True).name
        beds = [frappe.get_doc({"doctype": "Accommodation Bed", "naming_series": "BED-.####", "room": room,
                                "building": building, "bed_code": "B" + self._h(),
                                "status": "Available"}).insert(ignore_permissions=True).name for _ in range(2)]
        project = frappe.get_doc({"doctype": "Project", "project_name": "P " + self._h()}).insert(ignore_permissions=True).name
        emps = [frappe.get_doc({"doctype": "Employee", "first_name": "E " + self._h(), "company": company,
                                "gender": "Male", "date_of_birth": "1990-01-01",
                                "date_of_joining": "2020-01-01"}).insert(ignore_permissions=True).name for _ in range(2)]
        return frappe._dict(company=company, cc=cc, building=building, room=room, beds=beds, project=project, emps=emps)

    def _assignment(self, fx, emp, bed):
        return frappe.get_doc({"doctype": "Accommodation Assignment", "naming_series": "ACC-ASGN-.YYYY.-.####",
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
        other_building = frappe.get_doc({"doctype": "Accommodation Building", "building_name": "B " + self._h(),
                                         "site": frappe.db.get_value("Accommodation Building", fx.building, "site"),
                                         "total_capacity": 2, "company": fx.company,
                                         "default_cost_center": fx.cc}).insert(ignore_permissions=True).name
        doc = self._assignment(fx, fx.emps[0], fx.beds[0])
        doc.building = other_building  # bed/room belong to fx.building, not other_building
        with self.assertRaises(frappe.ValidationError):
            doc.insert(ignore_permissions=True)
