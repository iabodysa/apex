from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


class TestRouteTemplate(FrappeTestCase):
    def test_template_assigns_stable_stop_keys(self):
        route = frappe.get_doc(
            {
                "doctype": "Route Template",
                "template_name": "Housing to Project",
                "route_type": "Mixed",
                "stops": [
                    {"stop_name": "Housing"},
                    {"stop_name": "Project"},
                ],
            }
        )

        route.validate()

        self.assertEqual([row.stop_key for row in route.stops], ["stop-1", "stop-2"])

    def test_template_requires_a_named_stop(self):
        route = frappe.get_doc(
            {
                "doctype": "Route Template",
                "template_name": "Empty",
                "route_type": "Mixed",
                "stops": [],
            }
        )

        with self.assertRaises(frappe.ValidationError):
            route.validate()

    def test_new_stop_key_does_not_reuse_a_surviving_key_after_deletion(self):
        route = frappe.get_doc(
            {
                "doctype": "Route Template",
                "template_name": "Key allocation",
                "route_type": "Mixed",
                "stops": [
                    {"stop_name": "Second", "stop_key": "stop-2"},
                    {"stop_name": "Third", "stop_key": "stop-3"},
                    {"stop_name": "New"},
                ],
            }
        )

        route.validate()

        self.assertEqual(
            [row.stop_key for row in route.stops],
            ["stop-2", "stop-3", "stop-1"],
        )

    def test_duplicate_existing_stop_keys_are_rejected(self):
        route = frappe.get_doc(
            {
                "doctype": "Route Template",
                "template_name": "Duplicate keys",
                "route_type": "Mixed",
                "stops": [
                    {"stop_name": "First", "stop_key": "stop-1"},
                    {"stop_name": "Second", "stop_key": "stop-1"},
                ],
            }
        )

        with self.assertRaises(frappe.ValidationError):
            route.validate()


# --- merged from test_route_template_naming.py ---
class TestRouteTemplateNaming(FrappeTestCase):
    def _template(self, template_name):
        """A Route Template the controller accepts: ``stops`` is mandatory, so a
        stopless template never reaches the autoname."""
        doc = frappe.get_doc(
            {
                "doctype": "Route Template",
                "template_name": template_name,
                "route_type": "Pickup",
                "stops": [{"stop_name": "Housing"}],
            }
        )
        doc.insert(ignore_permissions=True)
        self.addCleanup(
            frappe.delete_doc, "Route Template", doc.name, ignore_permissions=True, force=True
        )
        return doc

    def test_the_autoname_mints_an_rt_name(self):
        doc = self._template("Autoname Route")
        self.assertTrue(
            doc.name.startswith("RT-"),
            f"Expected the RT-.#### series to name the template, got: {doc.name}",
        )

    def test_is_active_defaults_to_enabled(self):
        self.assertEqual(self._template("Active Default Route").is_active, 1)
