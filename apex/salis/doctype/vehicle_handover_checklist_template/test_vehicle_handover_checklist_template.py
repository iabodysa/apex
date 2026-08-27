# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from apex.salis.doctype.vehicle_handover_checklist_template.vehicle_handover_checklist_template import (
    load_template_into_doc,
)
from apex.tests.factories import make_vehicle


def _checklist_template(**overrides):
    fields = {
        "doctype": "Vehicle Handover Checklist Template",
        "template_name": "_T-Checklist " + frappe.generate_hash(length=6),
        "is_active": 1,
        "items": [
            {"check_item": "Tyre condition", "remark": "Check tread depth"},
            {"check_item": "Fuel level"},
        ],
    }
    fields.update(overrides)
    return frappe.get_doc(fields)


def _driver(label):
    return frappe.get_doc(
        {
            "doctype": "Salis Driver",
            "full_name": "_T-Driver " + label + " " + frappe.generate_hash(length=6),
            "status": "Active",
        }
    ).insert(ignore_permissions=True).name


def _draft_handover(plate, **overrides):
    fields = {
        "doctype": "Vehicle Handover",
        "vehicle": make_vehicle(plate),
        "direction": "Transfer",
        "from_driver": _driver("From"),
        "to_driver": _driver("To"),
        "handover_date": today(),
        "odometer_reading": 0,
    }
    fields.update(overrides)
    return frappe.get_doc(fields).insert(ignore_permissions=True)


class TestVehicleHandoverChecklistTemplateNaming(FrappeTestCase):
    def test_a_second_template_reusing_a_template_name_is_refused_by_the_framework(self):
        first = _checklist_template().insert(ignore_permissions=True)
        with self.assertRaises(frappe.DuplicateEntryError):
            _checklist_template(template_name=first.template_name).insert(
                ignore_permissions=True
            )

    def test_a_template_with_no_check_item_is_refused_by_the_framework(self):
        with self.assertRaises(frappe.MandatoryError):
            _checklist_template(items=[]).insert(ignore_permissions=True)


class TestVehicleHandoverChecklistTemplateLoad(FrappeTestCase):
    def test_an_inactive_template_is_refused_by_the_loader(self):
        template = _checklist_template(is_active=0).insert(ignore_permissions=True)
        handover = _draft_handover("_T-VHCT 0001")
        with self.assertRaisesRegex(frappe.ValidationError, "is not active"):
            load_template_into_doc(handover.name, template.name)

    def test_a_submitted_handover_is_refused_by_the_loader(self):
        template = _checklist_template().insert(ignore_permissions=True)
        handover = _draft_handover(
            "_T-VHCT 0002", signed_evidence="/files/_t-handover.pdf"
        )
        handover.submit()
        with self.assertRaisesRegex(
            frappe.ValidationError, "only be loaded into a Draft handover"
        ):
            load_template_into_doc(handover.name, template.name)

    def test_an_active_template_lands_its_rows_on_the_stored_handover(self):
        template = _checklist_template().insert(ignore_permissions=True)
        handover = _draft_handover("_T-VHCT 0003")
        result = load_template_into_doc(handover.name, template.name)
        self.assertEqual(result["rows_added"], 2)
        stored = frappe.get_doc("Vehicle Handover", handover.name)
        self.assertEqual(
            [row.check_item for row in stored.handover_check_items],
            ["Tyre condition", "Fuel level"],
        )
        self.assertEqual(stored.handover_check_items[0].remark, "Check tread depth")

    def test_a_row_already_on_the_handover_survives_the_load(self):
        template = _checklist_template().insert(ignore_permissions=True)
        handover = _draft_handover("_T-VHCT 0004")
        handover.append(
            "handover_check_items", {"check_item": "Operator note", "ok": 1}
        )
        handover.save()
        load_template_into_doc(handover.name, template.name)
        stored = frappe.get_doc("Vehicle Handover", handover.name)
        self.assertEqual(
            [row.check_item for row in stored.handover_check_items],
            ["Operator note", "Tyre condition", "Fuel level"],
        )
