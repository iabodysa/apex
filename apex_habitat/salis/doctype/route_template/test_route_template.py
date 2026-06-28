import frappe
from frappe.tests.utils import FrappeTestCase


class TestRouteTemplate(FrappeTestCase):
    def _make_template(self, **kwargs):
        doc = frappe.new_doc("Route Template")
        doc.template_name = kwargs.get("template_name", "Test Route Template")
        doc.route_type = kwargs.get("route_type", "Pickup")
        doc.update(kwargs)
        doc.insert(ignore_permissions=True)
        return doc

    def test_autoname_pattern(self):
        """Route Template names must follow the RT-.#### series."""
        doc = self._make_template(template_name="Autoname Test")
        self.assertTrue(
            doc.name.startswith("RT-"),
            f"Expected name to start with 'RT-', got: {doc.name}",
        )

    def test_is_active_default(self):
        """is_active should default to 1 (enabled) on creation."""
        doc = self._make_template(template_name="Active Default Test")
        self.assertEqual(doc.is_active, 1)
