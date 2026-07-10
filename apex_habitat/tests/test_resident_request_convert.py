# Copyright (c) 2026, AFMCO and contributors
"""Converting a triaged Accommodation Resident Request into the operational
document that does the work, and stamping the back-link (target_doctype /
target_document) onto the request for traceability. Mirrors the Maintenance
Request -> Work Order mapper pattern."""

import frappe
from apex_habitat.tests.factories import ApexHabitatTestCase
from apex_habitat.tests import factories

# [#5tgk0h]
test_ignore = factories.test_ignore


class TestResidentRequestConvert(ApexHabitatTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        factories.make_company("Test AFMCO")
        cls.building = factories.make_building("RRC-BLDG", company="Test AFMCO")
        cls.room = factories.make_room("RRC-BLDG", room_number="RRC-BLDG-R01")

    def _new_request(self, category="Maintenance", priority="High", **kw):
        doc = frappe.get_doc({
            "doctype": "Accommodation Resident Request",
            "request_category": category,
            "priority": priority,
            "description": "Convert test " + frappe.generate_hash(length=4),
            "building": "RRC-BLDG",
            "room": "RRC-BLDG-R01",
            "status": "New",
            **kw,
        })
        doc.insert(ignore_permissions=True)
        return doc

    def _convert(self, name):
        from apex_habitat.habitat.doctype.accommodation_resident_request.accommodation_resident_request import (
            convert_request,
        )
        return convert_request(name)

    def test_maintenance_category_creates_maintenance_request_and_links_back(self):
        req = self._new_request(category="Plumbing", priority="High")
        res = self._convert(req.name)

        self.assertEqual(res["target_doctype"], "Maintenance Request")
        self.assertTrue(res["target_document"])
        self.assertFalse(res["already_converted"])

        # [#jaachd]
        req.reload()
        self.assertEqual(req.target_doctype, "Maintenance Request")
        self.assertEqual(req.target_document, res["target_document"])
        # [#7bspo0]
        self.assertEqual(req.status, "In Progress")

        # [#s66kcv]
        mr = frappe.get_doc("Maintenance Request", res["target_document"])
        self.assertEqual(mr.building, "RRC-BLDG")
        self.assertEqual(mr.room, "RRC-BLDG-R01")
        self.assertEqual(mr.priority, "High")
        self.assertEqual(mr.issue_type, "Plumbing")
        self.assertEqual(mr.issue_description, req.description)

    def test_conversion_is_idempotent(self):
        req = self._new_request(category="Maintenance")
        first = self._convert(req.name)
        second = self._convert(req.name)

        self.assertFalse(first["already_converted"])
        self.assertTrue(second["already_converted"])
        self.assertEqual(first["target_document"], second["target_document"])

        # [#2cpc8r]
        count = frappe.db.count("Maintenance Request",
                                {"name": first["target_document"]})
        self.assertEqual(count, 1)

    def test_safety_category_creates_safety_incident(self):
        req = self._new_request(category="Safety", priority="Critical",
                                issue_location="Staircase")
        res = self._convert(req.name)

        self.assertEqual(res["target_doctype"], "Habitat Safety Incident")
        inc = frappe.get_doc("Habitat Safety Incident", res["target_document"])
        self.assertEqual(inc.building, "RRC-BLDG")
        self.assertEqual(inc.severity, "Critical")

        req.reload()
        self.assertEqual(req.target_doctype, "Habitat Safety Incident")
        self.assertEqual(req.target_document, res["target_document"])

    def test_non_convertible_category_throws(self):
        req = self._new_request(category="Suggestion")
        with self.assertRaises(frappe.exceptions.ValidationError):
            self._convert(req.name)

        # [#3ygvnj]
        req.reload()
        self.assertFalse(req.target_doctype)
        self.assertFalse(req.target_document)

    def test_terminal_status_is_not_overridden_on_convert(self):
        # [#ca7ou4]
        req = self._new_request(category="Maintenance", status="Resolved",
                                resolution_notes="Closed at source")
        res = self._convert(req.name)
        req.reload()
        self.assertEqual(req.status, "Resolved")
        self.assertEqual(req.target_document, res["target_document"])
