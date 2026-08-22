# Copyright (c) 2026, afmcoltd
"""What Maintenance Material Template guarantees, asserted against the DocType itself.

Patterned on ``frappe/tests/test_client.py`` — the subject is the whitelisted
``load_template_into_doc``, since the DocType's own class body is ``pass``. It refuses
an unsupported target doctype and a non-Draft target document, returns zero rows
without error when no active template matches the issue type, and otherwise appends
one ``procurement_items`` row per template item and flags ``requires_procurement``.

"Maintenance Request" is deliberately absent from ``test_dependencies``: its own
dependency graph reaches Journal Entry -> Payment Order -> Payment Request -> Payment
Gateway Account -> Payment Gateway, a DocType this bench does not have installed. The
one Maintenance Request this test needs is built directly below.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.doctype.maintenance_material_template.maintenance_material_template import (
    load_template_into_doc,
)

test_dependencies = ["Building", "Room"]


def _new_request():
    record = frappe.copy_doc(frappe.get_test_records("Maintenance Request")[0])
    record.insert()
    return record


class TestMaintenanceMaterialTemplate(FrappeTestCase):
    def test_loading_into_an_unsupported_doctype_is_refused(self):
        """Only a Maintenance Request or Work Order may receive template rows."""
        building = frappe.copy_doc(frappe.get_test_records("Building")[0])
        building.building_name = f"_T-Template Building {frappe.generate_hash(length=8)}"
        building.floor_plan = []
        building.insert()

        with self.assertRaisesRegex(frappe.ValidationError, "only supported for"):
            load_template_into_doc("Building", building.name, "Electrical")

    def test_no_active_template_for_the_issue_type_returns_zero_rows_without_error(self):
        """A miss is reported, not thrown — the caller decides what to do about it.

        The issue type queried is a value nothing else — this test class shares one
        transaction across its methods, and the shipped catalog seeds an active
        template for every real Select option — ever inserts a template against, so
        no active row can exist for it under any run order.
        """
        request = _new_request()

        result = load_template_into_doc(
            "Maintenance Request", request.name, "_T-No-Such-Issue-Type"
        )

        self.assertEqual(result["rows_added"], 0)

    def test_loading_into_a_submitted_request_is_refused(self):
        """A template can only add procurement rows while the request is still Draft.

        Its issue type is a value unique to this test: the shipped catalog seeds an
        active template for every real Select option (and this class shares one
        transaction across its own methods), so reusing a real option or another
        test's value would make ``limit=1`` ambiguous.
        """
        template = frappe.copy_doc(frappe.get_test_records("Maintenance Material Template")[0])
        template.template_name = f"_T-Kit {frappe.generate_hash(length=6)}"
        template.issue_type = f"_T-Issue-Submitted-{frappe.generate_hash(length=8)}"
        template.insert()

        request = _new_request()
        request.submit()

        with self.assertRaisesRegex(frappe.ValidationError, "Draft document"):
            load_template_into_doc("Maintenance Request", request.name, template.issue_type)

    def test_a_matching_active_template_appends_its_items_and_flags_procurement(self):
        """The acceptance case: a matching template's rows land on the request as its own.

        Its issue type is unique to this test for the same reason as its sibling above.
        """
        template = frappe.copy_doc(frappe.get_test_records("Maintenance Material Template")[0])
        template.template_name = f"_T-Kit {frappe.generate_hash(length=6)}"
        template.issue_type = f"_T-Issue-Accepted-{frappe.generate_hash(length=8)}"
        template.insert()

        request = _new_request()

        result = load_template_into_doc(
            "Maintenance Request", request.name, template.issue_type
        )

        self.assertEqual(result["rows_added"], len(template.items))
        reloaded = frappe.get_doc("Maintenance Request", request.name)
        self.assertEqual(len(reloaded.procurement_items), len(template.items))
        self.assertEqual(reloaded.procurement_items[0].material, template.items[0].material)
        self.assertEqual(reloaded.procurement_items[0].quantity, template.items[0].quantity)
        self.assertTrue(reloaded.requires_procurement)
