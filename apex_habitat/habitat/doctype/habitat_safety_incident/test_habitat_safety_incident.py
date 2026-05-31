import frappe
from frappe.tests.utils import FrappeTestCase

# Prevent Frappe test runner from recursively resolving Link-field dependencies
# on external DocTypes that require ERPNext (not installed in CI bench).
test_ignore = [
    "Company",
    "Role",
    "User",
]


class TestHabitatSafetyIncident(FrappeTestCase):

    def _base(self, **overrides):
        doc = {
            "doctype": "Habitat Safety Incident",
            "naming_series": "HSI-.YYYY.-.#####",
            "incident_datetime": "2026-06-15 10:00:00",
            "accommodation_building": "QA-BLDG",
            "severity": "High",
            "description": "Smoke detected in stairwell.",
        }
        doc.update(overrides)
        return frappe.get_doc(doc)

    def test_create_valid_incident(self):
        doc = self._base()
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertIsNotNone(doc.name)
        self.assertTrue(doc.reported_by)  # defaulted to session user
        frappe.delete_doc("Habitat Safety Incident", doc.name, force=True, ignore_permissions=True)

    def test_missing_building_raises(self):
        doc = self._base()
        doc.accommodation_building = None
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_missing_severity_raises(self):
        doc = self._base()
        doc.severity = None
        with self.assertRaises(frappe.exceptions.MandatoryError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_negative_casualties_raises(self):
        doc = self._base(casualties=-1)
        with self.assertRaises(frappe.exceptions.ValidationError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_close_without_resolution_raises(self):
        doc = self._base(status="Closed")
        with self.assertRaises(frappe.exceptions.ValidationError):
            doc.insert(ignore_permissions=True, ignore_links=True)
