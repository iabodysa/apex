import frappe
from frappe.tests.utils import FrappeTestCase

# [#8evoal]
test_ignore = [
    "Company",
    "Role",
    "User",
]


class TestHabitatSafetyIncident(FrappeTestCase):

    def test_docperm_safety_officer(self):
        """Safety Officer must have read/write/create on Habitat Safety Incident (no submit)."""
        meta = frappe.get_meta("Habitat Safety Incident")
        roles = {p.role: p for p in meta.permissions}
        self.assertIn("Safety Officer", roles, "Safety Officer perm row is missing")
        p = roles["Safety Officer"]
        self.assertEqual(p.read, 1)
        self.assertEqual(p.write, 1)
        self.assertEqual(p.create, 1)
        self.assertFalse(getattr(p, "submit", 0), "Safety Officer must NOT have submit on HSI")

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
        self.assertTrue(doc.reported_by)  # [#30fqgf]
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
