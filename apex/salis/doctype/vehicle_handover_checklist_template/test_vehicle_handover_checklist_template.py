# Copyright (c) 2026, afmcoltd
"""What a Vehicle Handover Checklist Template guarantees, asserted against the DocType itself.

The DocType's own controller carries no validation — its guarantee lives in
the whitelisted ``load_template_into_doc``, defined in this same module: it
loads an active template's items onto a Draft Vehicle Handover only, and
refuses an inactive template or a handover that is no longer Draft.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.salis.doctype.vehicle_handover_checklist_template.vehicle_handover_checklist_template import (
    load_template_into_doc,
)

test_dependencies = ["Salis Vehicle", "Salis Driver"]


def _new_draft_handover():
    handover = frappe.copy_doc(frappe.get_test_records("Vehicle Handover")[0])
    handover.insert()
    return handover


class TestVehicleHandoverChecklistTemplate(FrappeTestCase):
    def test_loading_an_inactive_template_is_refused(self):
        """A retired checklist must not be offered onto a live handover."""
        handover = _new_draft_handover()
        template = frappe.get_test_records("Vehicle Handover Checklist Template")[1]
        self.assertFalse(template["is_active"])
        self.assertRaisesRegex(
            frappe.ValidationError,
            "is not active",
            lambda: load_template_into_doc(handover.name, "_T-Retired Bus Checklist"),
        )

    def test_loading_a_template_into_a_submitted_handover_is_refused(self):
        """Once a handover is finalised, its checklist is no longer whose to load."""
        handover = _new_draft_handover()
        handover.signed_evidence = "/files/_t-signed-handover.pdf"
        handover.save()
        handover.submit()
        self.assertRaisesRegex(
            frappe.ValidationError,
            "can only be loaded into a Draft handover",
            lambda: load_template_into_doc(handover.name, "_T-Standard Sedan Checklist"),
        )

    def test_loading_an_active_template_appends_its_items(self):
        """Loading the template is what actually gives the handover its checklist rows."""
        handover = _new_draft_handover()
        result = load_template_into_doc(handover.name, "_T-Standard Sedan Checklist")
        self.assertEqual(result["rows_added"], 2)
        handover.reload()
        self.assertEqual(
            [row.check_item for row in handover.handover_check_items],
            ["Tyre condition", "Fuel level"],
        )
