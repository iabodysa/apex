# Copyright (c) 2026, AFMCO and contributors
"""The vehicle-incident Web Form captures an incident as a draft via the native
Web Form accept() path.

Mirrors the public arrival-manifest / transport-request intake forms: an
anonymous submission creates a docstatus 0 Vehicle Incident for a supervisor to
review and confirm. The Theft on_submit side-effect (stop vehicle / clear driver)
must NOT fire on the draft, so anonymous capture stays safe.
"""

import json

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.website.doctype.web_form.web_form import accept

WEB_FORM = "vehicle-incident"


def _h(n=5):
    return frappe.generate_hash(length=n).upper()


class TestVehicleIncidentWebForm(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.vehicle = frappe.get_doc({
            "doctype": "Salis Vehicle",
            "plate_number": "VIWF " + _h(),
            "status": "Active",
        }).insert(ignore_permissions=True).name

    def tearDown(self):
        frappe.set_user("Administrator")

    def _accept(self, **overrides):
        data = {
            "incident_type": "Accident",
            "vehicle": self.vehicle,
            "incident_date": "2026-06-01",
            "location": "Ring Road",
            "report_number": "PR-" + _h(),
            "description": "Side-swiped while parked.",
            "reported_by": "Gate Guard",
        }
        data.update(overrides)
        return accept(web_form=WEB_FORM, data=json.dumps(data))

    def test_accept_creates_draft_incident(self):
        self._accept()
        frappe.set_user("Administrator")
        names = frappe.get_all(
            "Vehicle Incident",
            filters={"vehicle": self.vehicle, "incident_type": "Accident"},
            fields=["name", "docstatus", "description"],
        )
        self.assertEqual(len(names), 1)
        self.assertEqual(names[0].docstatus, 0)
        self.assertEqual(names[0].description, "Side-swiped while parked.")

    def test_theft_capture_does_not_stop_the_vehicle(self):
        # A drafted Theft report must not run the on_submit lock until a
        # supervisor submits it: the vehicle stays Active.
        self._accept(incident_type="Theft", description="Vehicle missing from yard.")
        frappe.set_user("Administrator")
        self.assertTrue(
            frappe.db.exists("Vehicle Incident", {"vehicle": self.vehicle, "incident_type": "Theft"})
        )
        self.assertEqual(frappe.db.get_value("Salis Vehicle", self.vehicle, "status"), "Active")
