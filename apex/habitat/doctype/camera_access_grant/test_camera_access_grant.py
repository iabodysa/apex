# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from apex.tests.factories import make_building


def _grant(**overrides):
    fields = {
        "doctype": "Camera Access Grant",
        "requested_for": "Administrator",
        "access_level": "Live View Only",
        "valid_from": "2026-01-01",
    }
    fields.update(overrides)
    return frappe.get_doc(fields)


class TestCameraAccessGrantIdentity(FrappeTestCase):
    def test_framework_refuses_a_grant_that_names_nobody(self):
        with self.assertRaises(frappe.MandatoryError):
            _grant(requested_for=None).insert(ignore_permissions=True)

    def test_framework_refuses_a_grant_with_no_start_date(self):
        with self.assertRaises(frappe.MandatoryError):
            _grant(valid_from=None).insert(ignore_permissions=True)

    def test_framework_refuses_a_user_that_does_not_exist(self):
        with self.assertRaisesRegex(frappe.LinkValidationError, "Could not find"):
            _grant(requested_for="nobody" + frappe.generate_hash(length=6) + "@example.com").insert(
                ignore_permissions=True
            )

    def test_framework_refuses_an_access_level_outside_the_select_options(self):
        with self.assertRaisesRegex(frappe.ValidationError, 'cannot be "Root"'):
            _grant(access_level="Root").insert(ignore_permissions=True)

    def test_a_new_grant_waits_for_approval_and_is_named_from_the_declared_series(self):
        doc = _grant().insert(ignore_permissions=True)
        self.assertEqual(doc.status, "Pending Approval")
        self.assertTrue(doc.name.startswith("CAM-ACC-"))


class TestCameraAccessGrantBuildingScope(FrappeTestCase):
    def test_framework_refuses_a_scope_row_that_names_no_building(self):
        with self.assertRaises(frappe.MandatoryError):
            _grant(buildings_scope=[{"notes": "no building named"}]).insert(ignore_permissions=True)

    def test_the_camera_count_is_fetched_from_the_building_without_the_operator_naming_it(self):
        building = make_building("Camera Grant Test Building", company="_Test Company")
        frappe.db.set_value("Building", building.name, "cctv_camera_count", 7)
        doc = _grant(buildings_scope=[{"building": building.name}]).insert(ignore_permissions=True)
        self.assertEqual(doc.buildings_scope[0].camera_count, 7)


class TestCameraAccessGrantSubmitLock(FrappeTestCase):
    def test_a_submitted_grant_refuses_a_changed_access_level(self):
        doc = _grant().insert(ignore_permissions=True)
        doc.submit()
        doc.access_level = "Full Admin"
        with self.assertRaises(frappe.UpdateAfterSubmitError):
            doc.save()

    def test_a_cancelled_grant_carries_docstatus_two(self):
        doc = _grant().insert(ignore_permissions=True)
        doc.submit()
        doc.cancel()
        self.assertEqual(frappe.db.get_value("Camera Access Grant", doc.name, "docstatus"), 2)
