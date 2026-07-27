# Copyright (c) 2026, AFMCO and contributors
"""What a REFUSED ``load_template_into_doc`` costs the rest of the request.

The endpoint used to wrap its ``doc.save()`` in ``except Exception:
frappe.db.rollback(); frappe.throw(generic)``. ``frappe.db.rollback()`` takes no
savepoint, so it discarded the WHOLE request transaction — every row the request
had written before this endpoint was reached, not just the appended template rows —
and the generic message then stood in for the validation error that actually
refused the save.

Both halves are asserted here: a row written EARLIER in the same request survives
the refusal, and the caller is handed the real reason. The refusal itself is real
rather than injected — ``frappe.db.set_value`` skips validate, so the target
request can be put in exactly the state its own ``before_save`` refuses, which is
how live data drifts under a draft somebody left open.
"""

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


def _hash():
    return frappe.generate_hash(length=12).upper()


class TestMaintenanceMaterialTemplateLoad(FrappeTestCase):
    """A Site row is the witness: one mandatory Data field, no links, and nothing
    else in this module touches it, so its survival isolates the transaction
    behaviour from every other side effect the endpoint has."""

    def _witness_row(self):
        return frappe.get_doc({
            "doctype": "Site", "site_name": "A333-MMT-" + _hash(),
        }).insert(ignore_permissions=True).name

    def _template(self, issue_type):
        material = frappe.get_doc({
            "doctype": "Maintenance Material",
            "material_name": "Washer " + _hash(),
            "material_category": "General",
        }).insert(ignore_permissions=True)
        template = frappe.get_doc({
            "doctype": "Maintenance Material Template",
            "template_name": "Kit " + _hash(),
            "issue_type": issue_type,
            "is_active": 1,
        })
        template.append("items", {"material": material.name, "quantity": 2, "unit": "Piece"})
        template.insert(ignore_permissions=True)
        return template

    def _draft_request(self, issue_type):
        building = frappe.get_doc({
            "doctype": "Building", "building_name": "B " + _hash(), "total_capacity": 4,
        }).insert(ignore_permissions=True)
        room = frappe.get_doc({
            "doctype": "Room", "naming_series": "ROOM-.####", "building": building.name,
            "room_number": "R" + _hash(), "bed_capacity": 2,
        }).insert(ignore_permissions=True)
        request = frappe.get_doc({
            "doctype": "Maintenance Request", "naming_series": "MAINT-.YYYY.-.#####",
            "building": building.name, "room": room.name, "reported_by": "Administrator",
            "issue_type": issue_type, "issue_description": "Leak under sink",
        })
        request.insert(ignore_permissions=True)
        return request

    def test_a_refused_load_keeps_rows_written_earlier_in_the_same_request(self):
        from apex.habitat.doctype.maintenance_material_template.maintenance_material_template import (
            load_template_into_doc,
        )

        witness = self._witness_row()
        template = self._template("Plumbing")
        request = self._draft_request("Plumbing")
        # Reaches a state before_save refuses without going through validate.
        frappe.db.set_value("Maintenance Request", request.name, "status", "Assigned")

        with self.assertRaises(frappe.ValidationError) as caught:
            load_template_into_doc("Maintenance Request", request.name, "Plumbing")

        self.assertIn(
            "Assigned To is required", str(caught.exception),
            "the caller must be handed the refusal that actually happened, not a "
            "generic 'could not save' standing in for it",
        )
        self.assertTrue(
            frappe.db.exists("Site", witness),
            "a refused template load must not discard rows this request wrote before it",
        )
        self.assertTrue(
            frappe.db.exists("Maintenance Material Template", template.name),
            "the template read by the refused load must survive the refusal too",
        )

    def test_a_successful_load_appends_the_template_rows(self):
        """The success path, so the refusal test above is graded against a load that
        demonstrably works on the same fixtures."""
        from apex.habitat.doctype.maintenance_material_template.maintenance_material_template import (
            load_template_into_doc,
        )

        self._template("Electrical")
        request = self._draft_request("Electrical")

        result = load_template_into_doc("Maintenance Request", request.name, "Electrical")

        self.assertEqual(result["rows_added"], 1)
        request.reload()
        self.assertEqual(len(request.procurement_items), 1)
        self.assertEqual(request.requires_procurement, 1)
