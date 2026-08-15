# Copyright (c) 2026, AFMCO and contributors
"""What a saved Route Template is named, and what it defaults to.

The sibling ``test_route_template.py`` grades stop-key assignment against ``validate``.
This module inserts, so it covers what only a real insert shows: the ``RT-.####``
autoname mints a name, and ``is_active`` arrives at 1 without the caller setting it.
"""

import frappe
from frappe.tests.utils import FrappeTestCase


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
