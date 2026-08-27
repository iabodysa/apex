# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.habitat.doctype.maintenance_material_template.maintenance_material_template import (
    load_template_into_doc,
)
from apex.tests.factories import make_building, make_maintenance_request, make_room


def _material(**overrides):
    fields = {
        "doctype": "Maintenance Material",
        "material_name": "_T-Material " + frappe.generate_hash(length=6),
        "material_category": "Electrical",
        "default_uom": "Piece",
    }
    fields.update(overrides)
    return frappe.get_doc(fields).insert(ignore_permissions=True)


def _template(**overrides):
    fields = {
        "doctype": "Maintenance Material Template",
        "template_name": "_T-Template " + frappe.generate_hash(length=6),
        "issue_type": "Pest Control",
        "is_active": 1,
        "items": None,
    }
    fields.update(overrides)
    if fields.get("items") is None:
        fields["items"] = [{"material": _material().name, "quantity": 3}]
    return frappe.get_doc(fields)


def _place():
    building = make_building("Material Template Test Building", company="_Test Company")
    room = make_room(building.name, room_number=f"{building.name}-TPL")
    return building.name, room.name


def _draft_request():
    building, room = _place()
    return frappe.get_doc({
        "doctype": "Maintenance Request",
        "building": building,
        "room": room,
        "reported_by": "Administrator",
        "issue_type": "Pest Control",
        "issue_description": "Ants in the kitchen",
    }).insert(ignore_permissions=True)


def _issue_type():
    return "_T-Issue " + frappe.generate_hash(length=6)


class TestTemplateNameIsTheRecordName(FrappeTestCase):
    def test_the_template_name_becomes_the_record_name(self):
        doc = _template().insert(ignore_permissions=True)
        self.assertEqual(doc.name, doc.template_name)

    def test_framework_refuses_a_second_template_carrying_the_same_name(self):
        first = _template().insert(ignore_permissions=True)
        with self.assertRaises((frappe.DuplicateEntryError, frappe.UniqueValidationError)):
            _template(template_name=first.template_name).insert(ignore_permissions=True)

    def test_framework_refuses_an_issue_type_outside_the_select_options(self):
        with self.assertRaisesRegex(frappe.ValidationError, 'cannot be "Roof Repair"'):
            _template(issue_type="Roof Repair").insert(ignore_permissions=True)


class TestTemplateItemsAreMandatory(FrappeTestCase):
    def test_framework_refuses_a_template_with_no_item_row(self):
        with self.assertRaises(frappe.MandatoryError):
            _template(items=[]).insert(ignore_permissions=True)


class TestLoadTemplateIntoDocTarget(FrappeTestCase):
    def test_a_target_doctype_outside_the_two_supported_ones_is_refused(self):
        _building, room = _place()
        with self.assertRaisesRegex(
            frappe.ValidationError,
            "only supported for Maintenance Request and Maintenance Work Order",
        ):
            load_template_into_doc("Room", room, "Pest Control")

    def test_a_submitted_request_refuses_the_template(self):
        building, room = _place()
        issue_type = _issue_type()
        _template(issue_type=issue_type).insert(ignore_permissions=True)
        request = make_maintenance_request(building, room)
        with self.assertRaisesRegex(
            frappe.ValidationError, "Template can only be loaded into a Draft document"
        ):
            load_template_into_doc("Maintenance Request", request.name, issue_type)


class TestLoadTemplateIntoDocSelection(FrappeTestCase):
    def test_an_issue_type_no_template_carries_adds_no_row(self):
        request = _draft_request()
        result = load_template_into_doc("Maintenance Request", request.name, _issue_type())
        self.assertEqual(result["rows_added"], 0)
        self.assertRegex(result["message"], "No active template found for issue type")
        self.assertEqual(frappe.db.count("Maintenance Procurement Item", {"parent": request.name}), 0)

    def test_an_inactive_template_is_never_loaded(self):
        issue_type = _issue_type()
        _template(issue_type=issue_type, is_active=0).insert(ignore_permissions=True)
        request = _draft_request()
        result = load_template_into_doc("Maintenance Request", request.name, issue_type)
        self.assertEqual(result["rows_added"], 0)
        self.assertRegex(result["message"], "No active template found for issue type")

    def test_the_template_rows_land_on_the_draft_request_and_flag_procurement(self):
        issue_type = _issue_type()
        material = _material(default_uom="Roll").name
        template = _template(
            issue_type=issue_type, items=[{"material": material, "quantity": 4}]
        ).insert(ignore_permissions=True)
        request = _draft_request()

        result = load_template_into_doc("Maintenance Request", request.name, issue_type)
        self.assertEqual(result["template"], template.name)
        self.assertEqual(result["rows_added"], 1)

        request.reload()
        self.assertEqual(request.requires_procurement, 1)
        self.assertEqual([row.material for row in request.procurement_items], [material])
        self.assertEqual([row.quantity for row in request.procurement_items], [4])
        self.assertEqual([row.unit for row in request.procurement_items], ["Roll"])

    def test_a_template_row_with_no_quantity_lands_as_one(self):
        issue_type = _issue_type()
        material = _material().name
        _template(issue_type=issue_type, items=[{"material": material, "quantity": 0}]).insert(
            ignore_permissions=True
        )
        request = _draft_request()

        load_template_into_doc("Maintenance Request", request.name, issue_type)
        request.reload()
        self.assertEqual([row.quantity for row in request.procurement_items], [1])

    def test_a_request_that_needs_no_material_keeps_its_procurement_flag_down(self):
        request = _draft_request()
        load_template_into_doc("Maintenance Request", request.name, _issue_type())
        request.reload()
        self.assertEqual(request.requires_procurement, 0)
