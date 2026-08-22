# Copyright (c) 2026, afmcoltd
"""What a Route Template guarantees, asserted against the DocType itself.

A template with no stops at all is refused. Every stop needs a name. Stop keys
must be unique across the template's own stops, and any stop left without one
is auto-assigned the next free ``stop-N`` key.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = []


class TestRouteTemplate(FrappeTestCase):
    def test_a_template_with_no_stops_is_refused(self):
        """A route template that names no stops describes no route."""
        template = frappe.copy_doc(frappe.get_test_records("Route Template")[0])
        template.stops = []
        self.assertRaisesRegex(
            frappe.ValidationError,
            "Add at least one route stop",
            template.insert,
        )

    def test_a_stop_without_a_name_is_refused(self):
        """An unnamed stop is not a stop an operator or a driver can act on."""
        template = frappe.copy_doc(frappe.get_test_records("Route Template")[0])
        template.append("stops", {"stop_name": "   "})
        self.assertRaisesRegex(
            frappe.ValidationError,
            "Stop Name is required",
            template.insert,
        )

    def test_duplicate_stop_keys_are_refused(self):
        """Two stops sharing one key would collapse to a single stop everywhere the key is read."""
        template = frappe.copy_doc(frappe.get_test_records("Route Template")[0])
        template.append("stops", {"stop_name": "Duplicate A", "stop_key": "same-key"})
        template.append("stops", {"stop_name": "Duplicate B", "stop_key": "same-key"})
        self.assertRaisesRegex(
            frappe.ValidationError,
            "Route stop keys must be unique",
            template.insert,
        )

    def test_a_stop_left_without_a_key_is_auto_assigned_the_next_free_one(self):
        """Every stop must leave validate() with a usable key, hand-set or not."""
        template = frappe.copy_doc(frappe.get_test_records("Route Template")[0])
        template.append("stops", {"stop_name": "Unkeyed Stop"})
        template.insert()
        keys = [row.stop_key for row in template.stops]
        self.assertEqual(len(keys), len(set(keys)), "every stop must end up with a distinct key")
        self.assertTrue(all(keys), "no stop may be left without a key")
