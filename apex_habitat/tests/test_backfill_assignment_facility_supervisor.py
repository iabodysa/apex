# Copyright (c) 2026, AFMCO and contributors
"""The ONE-TIME backfill that copies a building's responsible_facility_supervisor
onto historical Accommodation Assignment rows whose field is still empty (the
fetch_from only fires on save, so rows saved before the field existed stay blank)."""

import frappe
from apex_habitat.tests.test_utils import ApexHabitatTestCase
from apex_habitat.tests import factories
from apex_habitat.patches.v1_x.backfill_assignment_facility_supervisor import execute

test_ignore = factories.test_ignore


def _user(email):
    if not frappe.db.exists("User", email):
        frappe.get_doc({
            "doctype": "User", "email": email,
            "first_name": email.split("@")[0], "send_welcome_email": 0,
        }).insert(ignore_permissions=True)
    return email


def _project(name):
    existing = frappe.db.get_value("Project", {"project_name": name}, "name")
    if existing:
        return existing
    return frappe.get_doc({"doctype": "Project", "project_name": name}).insert(
        ignore_permissions=True
    ).name


class TestBackfillAssignmentFacilitySupervisor(ApexHabitatTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        factories.make_company("Test AFMCO")
        cls.project = _project("BAFS Project")
        cls.sup_a = _user("bafs-sup-a@example.com")
        cls.sup_b = _user("bafs-sup-b@example.com")

        # Building WITH a supervisor and building WITHOUT one.
        cls.bldg_with = factories.make_building(
            "BAFS-WITH", company="Test AFMCO", responsible_facility_supervisor=cls.sup_a
        ).name
        cls.bldg_without = factories.make_building("BAFS-WITHOUT", company="Test AFMCO").name

        cls.room_with = factories.make_room("BAFS-WITH", room_number="BAFS-WITH-R01").name
        cls.room_without = factories.make_room(
            "BAFS-WITHOUT", room_number="BAFS-WITHOUT-R01"
        ).name

    def _make_assignment(self, building, room, bed_code, supervisor=None):
        bed = factories.make_bed(room, bed_code=bed_code).name
        doc = frappe.get_doc({
            "doctype": "Accommodation Assignment",
            "party_type": "Employee",
            "building": building,
            "room": room,
            "bed": bed,
            "assignment_type": "New Assignment",
            "stay_type": "Permanent",
            "check_in_date": frappe.utils.today(),
            "project": self.project,
            "responsible_facility_supervisor": supervisor,
        })
        # Skip the occupancy/business validate(); keep framework field/link checks.
        doc.flags.ignore_validate = True
        doc.insert(ignore_permissions=True)
        # The fetch_if_empty can populate on insert; force the historical blank state
        # for the rows the patch is meant to repair.
        if supervisor is None:
            frappe.db.set_value(
                doc.doctype, doc.name, "responsible_facility_supervisor", None,
                update_modified=False,
            )
        return doc.name

    def test_backfills_empty_when_building_has_supervisor(self):
        name = self._make_assignment(self.bldg_with, self.room_with, "BAFS-WITH-R01-B01")
        execute()
        self.assertEqual(
            frappe.db.get_value("Accommodation Assignment", name,
                                "responsible_facility_supervisor"),
            self.sup_a,
        )

    def test_skips_when_building_has_no_supervisor(self):
        name = self._make_assignment(
            self.bldg_without, self.room_without, "BAFS-WITHOUT-R01-B01"
        )
        execute()
        self.assertFalse(
            frappe.db.get_value("Accommodation Assignment", name,
                                "responsible_facility_supervisor")
        )

    def test_does_not_clobber_existing_supervisor(self):
        # Pre-set to sup_b even though the building's supervisor is sup_a.
        name = self._make_assignment(
            self.bldg_with, self.room_with, "BAFS-WITH-R01-B02", supervisor=self.sup_b
        )
        execute()
        self.assertEqual(
            frappe.db.get_value("Accommodation Assignment", name,
                                "responsible_facility_supervisor"),
            self.sup_b,
        )

    def test_rerun_is_idempotent(self):
        name = self._make_assignment(self.bldg_with, self.room_with, "BAFS-WITH-R01-B03")
        execute()
        execute()
        self.assertEqual(
            frappe.db.get_value("Accommodation Assignment", name,
                                "responsible_facility_supervisor"),
            self.sup_a,
        )
