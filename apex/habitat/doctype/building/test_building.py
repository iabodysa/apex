# Copyright (c) 2026, AFMCO and contributors
from __future__ import annotations
import frappe
from frappe.tests.utils import FrappeTestCase

from apex.tests.factories import make_building
from apex.habitat.doctype.building.building import (
    get_site_address,
)
from apex.tests.factories import make_company
import os
import re
from apex.habitat.doctype.building.building import generate_safety_setup
from apex.tests.factories import ApexHabitatTestCase
from apex.habitat.doctype.building.building import (
    generate_rooms_and_beds,
)

class TestAccommodationBuilding(FrappeTestCase):

    def test_create_valid_building(self):
        doc = frappe.get_doc({
            "doctype": "Building",
            "building_name": "QA Test Building",
            "total_capacity": 20,
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        self.assertEqual(doc.building_name, "QA Test Building")
        frappe.delete_doc("Building", doc.name, force=True, ignore_permissions=True)

    def test_missing_building_name_raises(self):
        doc = frappe.get_doc({
            "doctype": "Building",
            "total_capacity": 10,
        })
        with self.assertRaises(frappe.exceptions.ValidationError):
            doc.insert(ignore_permissions=True, ignore_links=True)

    def test_new_building_saves_without_manual_capacity(self):
        """total_capacity is system-derived (read-only, not reqd): a brand-new building
        with NO rooms/beds yet must still save, defaulting the capacity to 0 rather than
        raising MandatoryError (a read-only reqd Int could never be filled on a new doc)."""
        doc = frappe.get_doc({
            "doctype": "Building",
            "building_name": "QA No Manual Capacity",
        })
        doc.insert(ignore_permissions=True, ignore_links=True)
        try:
            self.assertEqual(doc.total_capacity, 0, "no beds yet -> capacity defaults to 0")
            self.assertEqual(
                frappe.get_meta("Building").get_field("total_capacity").reqd, 0,
                "total_capacity must no longer be reqd (it is system-derived)",
            )
        finally:
            frappe.delete_doc("Building", doc.name, force=True, ignore_permissions=True)

    def test_room_number_blank_prefix_is_byte_identical(self):
        from apex.habitat.doctype.building.building import _room_number
        self.assertEqual(_room_number("JED1", "G", "", 1), "JED1-G01")
        self.assertEqual(_room_number("JED1", "1", "", 5), "JED1-105")

    def test_room_number_with_prefix(self):
        from apex.habitat.doctype.building.building import _room_number
        self.assertEqual(_room_number("JED1", "G", "A", 1), "JED1-GA01")
        self.assertEqual(_room_number("JED1", "1", "B", 5), "JED1-1B05")
        self.assertEqual(_room_number("JED1", "G", " A ", 1), "JED1-GA01")

    def test_abbreviation_locked_after_rooms_exist(self):
        m = frappe.generate_hash(length=12)
        b = frappe.get_doc({
            "doctype": "Building", "building_name": "QA Lock " + m,
            "abbreviation": "QA" + m.upper(), "total_capacity": 10,
        })
        b.insert(ignore_permissions=True, ignore_links=True)
        room = frappe.get_doc({
            "doctype": "Room", "naming_series": "ROOM-.####",
            "building": b.name, "room_number": b.abbreviation + "-G01",
        })
        room.insert(ignore_permissions=True, ignore_links=True)
        b.reload()
        b.abbreviation = "QANEW"
        with self.assertRaises(frappe.ValidationError):
            b.save(ignore_permissions=True)
        frappe.delete_doc("Room", room.name, force=True, ignore_permissions=True)
        frappe.delete_doc("Building", b.name, force=True, ignore_permissions=True)

    def test_total_capacity_derives_from_beds(self):
        """total_capacity is the TRUE physical capacity: it must equal the count of the
        building's ACTUAL beds that are not Out of Service (and not virtual over-capacity
        beds), overriding any manual figure, so the occupancy / cost / over-capacity
        denominators cannot drift. Setting one bed Out of Service drops capacity by 1.
        The field is also read-only (system-derived)."""
        from apex.habitat.doctype.building.building import (
            generate_rooms_and_beds,
        )
        self.assertEqual(
            frappe.get_meta("Building").get_field("total_capacity").read_only, 1,
            "total_capacity must be read_only (auto-derived)",
        )
        m = frappe.generate_hash(length=12)
        b = frappe.get_doc({
            "doctype": "Building",
            "building_name": "QA Capacity " + m,
            "abbreviation": "QC" + m.upper(),
            "total_capacity": 999,
            "floor_plan": [
                {"doctype": "Floor Plan", "floor_number": 0, "room_count": 3,
                 "bed_capacity_per_room": 4, "room_type": "Standard", "generate_beds": 1,
                 "starting_room_number": 1},
                {"doctype": "Floor Plan", "floor_number": 1, "room_count": 2,
                 "bed_capacity_per_room": 2, "room_type": "Standard", "generate_beds": 1,
                 "starting_room_number": 1},
            ],
        })
        b.insert(ignore_permissions=True, ignore_links=True)
        try:
            generate_rooms_and_beds(b.name)
            b.reload()
            available_beds = frappe.db.count(
                "Bed",
                {"building": b.name, "status": ["!=", "Out of Service"], "is_temporary": 0},
            )
            self.assertEqual(b.total_capacity, 16, "total_capacity must derive to the physical bed count")
            self.assertEqual(available_beds, 16, "fixture sanity: 16 available physical beds")
            self.assertEqual(b.total_capacity, available_beds,
                             "total_capacity must equal the non-Out-of-Service physical bed count")
            one_bed = frappe.db.get_value("Bed", {"building": b.name}, "name")
            frappe.db.set_value("Bed", one_bed, "status", "Out of Service")
            b.save(ignore_permissions=True)
            b.reload()
            self.assertEqual(b.total_capacity, 15,
                             "an Out-of-Service bed must be excluded -> capacity drops by 1")
            b.total_capacity = 5
            b.save(ignore_permissions=True)
            b.reload()
            self.assertEqual(b.total_capacity, 15, "before_save must re-derive, ignoring the manual value")
        finally:
            for room in frappe.db.get_all("Room", {"building": b.name}, pluck="name"):
                for bed in frappe.db.get_all("Bed", {"room": room}, pluck="name"):
                    frappe.delete_doc("Bed", bed, force=True, ignore_permissions=True)
                frappe.delete_doc("Room", room, force=True, ignore_permissions=True)
            frappe.delete_doc("Building", b.name, force=True, ignore_permissions=True)

    def test_no_bed_room_does_not_inflate_capacity(self):
        """The core fix: a room with generate_beds=0 has a planned bed_capacity but
        NO physical beds. Deriving from sum(bed_capacity) over-counted it; deriving from
        the actual beds must NOT — total_capacity counts only the beds that truly exist."""
        from apex.habitat.doctype.building.building import (
            generate_rooms_and_beds,
        )
        m = frappe.generate_hash(length=12)
        b = frappe.get_doc({
            "doctype": "Building",
            "building_name": "QA NoBed " + m,
            "abbreviation": "QN" + m.upper(),
            "total_capacity": 999,
            "floor_plan": [
                {"doctype": "Floor Plan", "floor_number": 0, "room_count": 2,
                 "bed_capacity_per_room": 3, "room_type": "Standard", "generate_beds": 1,
                 "starting_room_number": 1},
                {"doctype": "Floor Plan", "floor_number": 1, "room_count": 2,
                 "bed_capacity_per_room": 5, "room_type": "Office", "generate_beds": 0,
                 "starting_room_number": 1},
            ],
        })
        b.insert(ignore_permissions=True, ignore_links=True)
        try:
            generate_rooms_and_beds(b.name)
            b.reload()
            bed_count = frappe.db.count("Bed", {"building": b.name})
            self.assertEqual(bed_count, 6, "only the generate_beds=1 rooms mint physical beds")
            self.assertEqual(b.total_capacity, 6,
                             "no-bed rooms must NOT inflate capacity (old sum() would give 16)")
        finally:
            for room in frappe.db.get_all("Room", {"building": b.name}, pluck="name"):
                for bed in frappe.db.get_all("Bed", {"room": room}, pluck="name"):
                    frappe.delete_doc("Bed", bed, force=True, ignore_permissions=True)
                frappe.delete_doc("Room", room, force=True, ignore_permissions=True)
            frappe.delete_doc("Building", b.name, force=True, ignore_permissions=True)

    def test_cctv_camera_count_derives_from_facility_assets(self):
        """cctv_camera_count auto-counts the building's CCTV Camera Facility Assets,
        excluding retired ones (Replaced/Scrapped), and is read-only — so a manual
        value is overridden on save."""
        self.assertEqual(
            frappe.get_meta("Building").get_field("cctv_camera_count").read_only, 1,
            "cctv_camera_count must be read_only (auto-derived)",
        )
        m = frappe.generate_hash(length=12)
        b = frappe.get_doc({
            "doctype": "Building",
            "building_name": "QA CCTV " + m,
            "cctv_camera_count": 99,
        })
        b.insert(ignore_permissions=True, ignore_links=True)
        cams = []
        try:
            for i, status in enumerate(("Operational", "Faulty", "Scrapped")):
                cam = frappe.get_doc({
                    "doctype": "Facility Asset",
                    "naming_series": "FAC-AST-.YYYY.-.####",
                    "asset_name": f"QA Cam {m} {i}",
                    "asset_category": "CCTV Camera",
                    "building": b.name,
                    "status": status,
                    "responsible_supervisor": "Administrator",
                })
                cam.insert(ignore_permissions=True, ignore_links=True)
                cams.append(cam.name)
            other = frappe.get_doc({
                "doctype": "Facility Asset",
                "naming_series": "FAC-AST-.YYYY.-.####",
                "asset_name": f"QA Gen {m}",
                "asset_category": "Generator",
                "building": b.name,
                "responsible_supervisor": "Administrator",
            })
            other.insert(ignore_permissions=True, ignore_links=True)
            cams.append(other.name)

            b.save(ignore_permissions=True)
            b.reload()
            self.assertEqual(
                b.cctv_camera_count, 2,
                "counts Operational + Faulty CCTV cameras; excludes Scrapped and the Generator",
            )
        finally:
            for name in cams:
                frappe.delete_doc("Facility Asset", name, force=True, ignore_permissions=True)
            frappe.delete_doc("Building", b.name, force=True, ignore_permissions=True)

    def test_generate_rooms_and_beds_rejects_unauthorized_user(self):
        """Unauthorized user (Guest) must receive PermissionError from
        generate_rooms_and_beds, which guards with a doc-level write check."""
        from apex.habitat.doctype.building.building import (
            generate_rooms_and_beds,
        )
        m = frappe.generate_hash(length=12)
        b = frappe.get_doc({
            "doctype": "Building",
            "building_name": "QA Perm Test " + m,
            "abbreviation": "QP" + m.upper(),
            "total_capacity": 4,
        })
        b.insert(ignore_permissions=True, ignore_links=True)
        try:
            frappe.set_user("Guest")
            with self.assertRaises((frappe.PermissionError, frappe.exceptions.PermissionError)):
                generate_rooms_and_beds(b.name)
        finally:
            frappe.set_user("Administrator")
            frappe.delete_doc("Building", b.name, force=True, ignore_permissions=True)

    def test_generate_rooms_and_beds_idempotent_no_duplicate_beds(self):
        """Re-running generate_rooms_and_beds must NOT create duplicate beds for
        existing rooms. The idempotency guard uses existing_bed_codes to skip any
        bed whose code is already present."""
        from apex.habitat.doctype.building.building import (
            generate_rooms_and_beds,
        )
        m = frappe.generate_hash(length=12)
        b = frappe.get_doc({
            "doctype": "Building",
            "building_name": "QA Idempotent " + m,
            "abbreviation": "QI" + m.upper(),
            "total_capacity": 2,
            "floor_plan": [
                {
                    "doctype": "Floor Plan",
                    "floor_number": 0,
                    "room_count": 1,
                    "bed_capacity_per_room": 2,
                    "room_type": "Standard",
                    "generate_beds": 1,
                    "starting_room_number": 1,
                }
            ],
        })
        b.insert(ignore_permissions=True, ignore_links=True)
        try:
            generate_rooms_and_beds(b.name)
            beds_after_first = frappe.db.count(
                "Bed",
                {"room": ["in", frappe.db.get_all(
                    "Room", {"building": b.name}, pluck="name"
                )]},
            )
            r2 = generate_rooms_and_beds(b.name, confirm_new_rooms=1)
            beds_after_second = frappe.db.count(
                "Bed",
                {"room": ["in", frappe.db.get_all(
                    "Room", {"building": b.name}, pluck="name"
                )]},
            )
            self.assertEqual(
                beds_after_first, beds_after_second,
                "Re-running should not create duplicate beds"
            )
            self.assertEqual(r2.get("created_beds", 0), 0, "No new beds should be created on re-run")
            self.assertGreater(r2.get("skipped_beds", 0), 0, "Existing beds must be counted as skipped")
        finally:
            frappe.set_user("Administrator")
            rooms = frappe.db.get_all("Room", {"building": b.name}, pluck="name")
            for room in rooms:
                beds = frappe.db.get_all("Bed", {"room": room}, pluck="name")
                for bed in beds:
                    frappe.delete_doc("Bed", bed, force=True, ignore_permissions=True)
                frappe.delete_doc("Room", room, force=True, ignore_permissions=True)
            frappe.delete_doc("Building", b.name, force=True, ignore_permissions=True)

class TestBuildingSupervisorPermission(FrappeTestCase):
    """The building's responsible_supervisor is the single source of truth for
    the building-scoped User Permission — on_update keeps the permission in sync."""

    @staticmethod
    def _user(email):
        if not frappe.db.exists("User", email):
            frappe.get_doc(
                {
                    "doctype": "User",
                    "email": email,
                    "first_name": email.split("@")[0],
                    "send_welcome_email": 0,
                }
            ).insert(ignore_permissions=True)
        return email

    @staticmethod
    def _has_perm(user, building):
        return bool(
            frappe.db.exists(
                "User Permission",
                {"user": user, "allow": "Building", "for_value": building},
            )
        )

    def test_supervisor_field_syncs_user_permission(self):
        frappe.set_user("Administrator")
        sup_a = self._user("t254_sup_a@example.com")
        sup_b = self._user("t254_sup_b@example.com")
        company = (
            frappe.defaults.get_global_default("company")
            or frappe.get_all("Company", limit=1)[0].name
        )
        b = make_building(
            name="T254 Building", company=company, responsible_supervisor=sup_a
        )
        self.assertTrue(self._has_perm(sup_a, b.name))

        b.responsible_supervisor = sup_b
        b.save(ignore_permissions=True)
        self.assertFalse(self._has_perm(sup_a, b.name))
        self.assertTrue(self._has_perm(sup_b, b.name))

        b.responsible_supervisor = None
        b.save(ignore_permissions=True)
        self.assertFalse(self._has_perm(sup_b, b.name))

test_ignore = ['Additional Salary', 'Asset', 'Asset Movement', 'Company', 'Cost Center', 'Currency', 'Employee', 'Item', 'Payment Entry', 'Project', 'Purchase Invoice', 'Role', 'Salary Component', 'Supplier', 'User']

def _ensure_site(name):
    """Per-name idempotent Accommodation Site (re-runnable across test sessions)."""
    if not frappe.db.exists("Site", name):
        frappe.get_doc(
            {"doctype": "Site", "site_name": name}
        ).insert(ignore_permissions=True)
    return name
def _ensure_address(title, line1, city, link_doctype=None, link_name=None):
    """Per-title idempotent Address; optionally Dynamic-Linked to a parent so it is
    that parent's DEFAULT address (get_address_text resolves via get_default_address)."""
    existing = frappe.db.get_value("Address", {"address_title": title})
    if existing:
        return existing
    payload = {
        "doctype": "Address",
        "address_title": title,
        "address_type": "Other",
        "address_line1": line1,
        "city": city,
        "country": "Saudi Arabia",
    }
    if link_doctype and link_name:
        payload["links"] = [{"link_doctype": link_doctype, "link_name": link_name}]
    return frappe.get_doc(payload).insert(ignore_permissions=True).name
class TestBuildingAddressFallback(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        make_company()

    def test_saved_site_address_when_no_own_address(self):
        """No stored building_address but a stored site -> the SITE's address.

        Drives the saved-record fallback with NO args (the controller reads the
        stored `site` because both building_address and site are omitted).
        """
        site = _ensure_site("T143 Fallback Site A")
        _ensure_address(
            "T143 Fallback Site A Addr", "Site Street 5", "Riyadh",
            link_doctype="Site", link_name=site,
        )
        bldg = make_building(name="T143 Fallback Bldg A", site=site).name

        self.assertIn("Site Street 5", get_site_address(bldg))

    def test_saved_own_address_precedes_saved_site(self):
        """Both stored: the building's OWN address wins over the site's, resolved
        purely from the saved record (no args passed)."""
        site = _ensure_site("T143 Fallback Site B")
        _ensure_address(
            "T143 Fallback Site B Addr", "Site Street 7", "Riyadh",
            link_doctype="Site", link_name=site,
        )
        own = _ensure_address("T143 Fallback Own B Addr", "Own Street 9", "Jeddah")
        bldg = make_building(
            name="T143 Fallback Bldg B", site=site, building_address=own
        ).name

        text = get_site_address(bldg)
        self.assertIn("Own Street 9", text)
        self.assertNotIn("Site Street 7", text)

    def test_legacy_dynamic_link_own_address_precedes_site(self):
        """A legacy own Address linked via Dynamic Link (the pre-Link-field native
        widget) and NO stored building_address must still surface on the form,
        winning over the site's address instead of being silently shadowed."""
        site = _ensure_site("T139 Reconcile Site")
        _ensure_address(
            "T139 Reconcile Site Addr", "Site Street 21", "Riyadh",
            link_doctype="Site", link_name=site,
        )
        bldg = make_building(name="T139 Reconcile Bldg", site=site).name
        _ensure_address(
            "T139 Reconcile Own Addr", "Legacy Own Street 23", "Jeddah",
            link_doctype="Building", link_name=bldg,
        )

        text = get_site_address(bldg)
        self.assertIn("Legacy Own Street 23", text)
        self.assertNotIn("Site Street 21", text)

    def test_clearing_saved_own_address_falls_back_to_site(self):
        """Clearing the stored building_address on the record makes the next no-arg
        resolution fall back to the stored site again (the live fallback path)."""
        site = _ensure_site("T143 Fallback Site C")
        _ensure_address(
            "T143 Fallback Site C Addr", "Site Street 11", "Riyadh",
            link_doctype="Site", link_name=site,
        )
        own = _ensure_address("T143 Fallback Own C Addr", "Own Street 13", "Jeddah")
        bldg = make_building(
            name="T143 Fallback Bldg C", site=site, building_address=own
        ).name

        self.assertIn("Own Street 13", get_site_address(bldg))

        frappe.db.set_value("Building", bldg, "building_address", None)
        cleared = get_site_address(bldg)
        self.assertIn("Site Street 11", cleared)
        self.assertNotIn("Own Street 13", cleared)
class TestBuildingSiteAddress(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def test_passed_site_overrides_stored_site(self):
        site_a = _ensure_site("T138 Site A")
        site_b = _ensure_site("T138 Site B")
        if not frappe.db.exists("Address", {"address_title": "T138 A"}):
            frappe.get_doc(
                {
                    "doctype": "Address",
                    "address_title": "T138 A",
                    "address_type": "Other",
                    "address_line1": "A Street 1",
                    "city": "Riyadh", "country": "Saudi Arabia",
                    "links": [{"link_doctype": "Site", "link_name": site_a}],
                }
            ).insert(ignore_permissions=True)
        company = (
            frappe.defaults.get_global_default("company")
            or frappe.get_all("Company", limit=1)[0].name
        )
        bldg = make_building(name="T138 Building", site=site_a, company=company).name

        self.assertTrue(get_site_address(bldg))
        self.assertEqual(get_site_address(bldg, site=site_b), "")

    def test_building_address_overrides_site(self):
        """the building's own selected Address wins over the Site's; clearing it
        falls back to the Site."""
        site_a = _ensure_site("T144 Site")
        if not frappe.db.exists("Address", {"address_title": "T144 Site Addr"}):
            frappe.get_doc(
                {
                    "doctype": "Address", "address_title": "T144 Site Addr",
                    "address_type": "Other", "address_line1": "Site Street", "city": "Riyadh", "country": "Saudi Arabia",
                    "links": [{"link_doctype": "Site", "link_name": site_a}],
                }
            ).insert(ignore_permissions=True)
        own = frappe.db.get_value("Address", {"address_title": "T144 Own Addr"})
        if not own:
            own = frappe.get_doc(
                {
                    "doctype": "Address", "address_title": "T144 Own Addr",
                    "address_type": "Other", "address_line1": "Own Street 9", "city": "Jeddah", "country": "Saudi Arabia",
                }
            ).insert(ignore_permissions=True).name
        company = (
            frappe.defaults.get_global_default("company")
            or frappe.get_all("Company", limit=1)[0].name
        )
        bldg = make_building(name="T144 Building", site=site_a, company=company).name

        own_text = get_site_address(bldg, site=site_a, building_address=own)
        self.assertIn("Own Street 9", own_text)
        self.assertNotIn("Site Street", own_text)
        self.assertIn("Site Street", get_site_address(bldg, site=site_a, building_address=""))

def _rand(n: int = 12) -> str:
    return frappe.generate_hash(length=n)
def _make_catalog(code: str, frequency: str, all_buildings: int = 1) -> str:
    """Get-or-create an active Safety Task Catalog with a given frequency; return name."""
    existing = frappe.db.get_value("Safety Task Catalog", {"task_code": code}, "name")
    if existing:
        frappe.db.set_value("Safety Task Catalog", existing, {
            "frequency": frequency,
            "is_active": 1,
            "applicable_to_all_buildings": all_buildings,
        })
        return existing
    return frappe.get_doc({
        "doctype": "Safety Task Catalog",
        "naming_series": "STC-.####",
        "task_title": f"A076 {code}",
        "task_code": code,
        "department": "Fire Safety",
        "frequency": frequency,
        "priority": "High",
        "is_active": 1,
        "applicable_to_all_buildings": all_buildings,
    }).insert(ignore_permissions=True).name
def _make_building(name: str) -> str:
    existing = frappe.db.get_value("Building", {"building_name": name}, "name")
    if existing:
        return existing
    return frappe.get_doc({
        "doctype": "Building",
        "building_name": name,
        "status": "Active",
        "total_capacity": 10,
    }).insert(ignore_permissions=True).name
def _template_for(catalog: str) -> str | None:
    return frappe.db.get_value(
        "Scheduled Task Template", {"safety_task_catalog": catalog}, "name"
    )
class TestGenerateSafetySetup(FrappeTestCase):

    def setUp(self):
        frappe.set_user("Administrator")

    def _cleanup(self, building: str, *catalogs: str):
        frappe.set_user("Administrator")
        for sta in frappe.get_all(
            "Scheduled Task Assignment", {"building": building}, pluck="name"
        ):
            frappe.delete_doc("Scheduled Task Assignment", sta, force=True, ignore_permissions=True)
        for cat in catalogs:
            tmpl = _template_for(cat)
            if tmpl:
                frappe.delete_doc("Scheduled Task Template", tmpl, force=True, ignore_permissions=True)
            if frappe.db.exists("Safety Task Catalog", cat):
                frappe.delete_doc("Safety Task Catalog", cat, force=True, ignore_permissions=True)
        if frappe.db.exists("Building", building):
            frappe.delete_doc("Building", building, force=True, ignore_permissions=True)

    def test_creates_reusable_template_and_assignment(self):
        cat = _make_catalog(f"A076-CRT-{_rand()}", "Monthly")
        bld = _make_building(f"A076 CRT {_rand()}")
        self.addCleanup(self._cleanup, bld, cat)

        summary = generate_safety_setup(bld)

        tmpl = _template_for(cat)
        self.assertTrue(tmpl, "a reusable template must be created for the catalog task")

        row = frappe.db.get_value(
            "Scheduled Task Template", tmpl, ["task_type", "frequency"], as_dict=True
        )
        self.assertEqual(row.task_type, "Safety")
        self.assertEqual(row.frequency, "Monthly")

        self.assertTrue(
            frappe.db.exists(
                "Scheduled Task Template Item",
                {"parent": tmpl, "task_catalog": cat, "is_active": 1},
            ),
            "catalog must be an active template_items row so the generator emits instances",
        )
        self.assertTrue(
            frappe.db.exists("Scheduled Task Assignment", {"template": tmpl, "building": bld}),
            "an assignment must bind the reusable template to this building",
        )
        self.assertGreaterEqual(summary["created_assignments"], 1)
        self.assertEqual(
            frappe.db.get_value("Building", bld, "safety_setup_status"), "Completed"
        )

    def test_idempotent_rerun_creates_no_duplicate_assignment_or_template(self):
        cat = _make_catalog(f"A076-IDEM-{_rand()}", "Quarterly")
        bld = _make_building(f"A076 IDEM {_rand()}")
        self.addCleanup(self._cleanup, bld, cat)

        generate_safety_setup(bld)
        second = generate_safety_setup(bld)

        tmpl = _template_for(cat)
        self.assertEqual(
            frappe.db.count("Scheduled Task Assignment", {"template": tmpl, "building": bld}),
            1,
            "re-run must not duplicate the (template, building) assignment",
        )
        self.assertEqual(
            frappe.db.count("Scheduled Task Template", {"safety_task_catalog": cat}),
            1,
            "re-run must reuse the single template, not create a second",
        )
        self.assertGreaterEqual(
            second["skipped_assignments"], 1,
            "the already-present assignment must be counted as skipped on re-run",
        )

    def test_annual_catalog_frequency_maps_to_annually(self):
        cat = _make_catalog(f"A076-ANN-{_rand()}", "Annual")
        bld = _make_building(f"A076 ANN {_rand()}")
        self.addCleanup(self._cleanup, bld, cat)

        generate_safety_setup(bld)

        tmpl = _template_for(cat)
        self.assertTrue(tmpl)
        self.assertEqual(
            frappe.db.get_value("Scheduled Task Template", tmpl, "frequency"),
            "Annually",
            "catalog 'Annual' must map to the template Select value 'Annually'",
        )

    def test_event_driven_frequency_is_excluded_not_scheduled(self):
        for freq in ("As Needed", "On Entry"):
            code = f"A076-EVT-{_rand()}"
            cat = _make_catalog(code, freq)
            bld = _make_building(f"A076 EVT {_rand()}")
            self.addCleanup(self._cleanup, bld, cat)

            summary = generate_safety_setup(bld)

            self.assertFalse(
                _template_for(cat),
                f"an event-driven ({freq}) task must NOT get a scheduled template",
            )
            self.assertIn(
                code, summary["event_driven_excluded"],
                f"an event-driven ({freq}) task must be reported as excluded, not swallowed",
            )

    def test_reused_template_backfills_missing_scheduling_item(self):
        """A pre-existing template linked to the catalog but WITHOUT items (as a
        pre-redesign / migrated template is) must be reused (not duplicated) and the
        generator must backfill the catalog as an active template_items row, otherwise
        the daily generator would silently emit nothing for it."""
        cat = _make_catalog(f"A076-LEG-{_rand()}", "Weekly")
        bld = _make_building(f"A076 LEG {_rand()}")
        self.addCleanup(self._cleanup, bld, cat)

        legacy = frappe.get_doc({
            "doctype": "Scheduled Task Template",
            "template_name": f"Legacy STT {_rand()}",
            "task_type": "Safety",
            "frequency": "Weekly",
            "safety_task_catalog": cat,
            "is_active": 1,
        }).insert(ignore_permissions=True)

        summary = generate_safety_setup(bld)

        self.assertEqual(
            frappe.db.count("Scheduled Task Template", {"safety_task_catalog": cat}),
            1,
            "must reuse the existing catalog template, not create a duplicate",
        )
        self.assertEqual(_template_for(cat), legacy.name)
        self.assertTrue(
            frappe.db.exists(
                "Scheduled Task Template Item",
                {"parent": legacy.name, "task_catalog": cat, "is_active": 1},
            ),
            "the reused template must be backfilled with the catalog scheduling item",
        )
        self.assertTrue(
            frappe.db.exists(
                "Scheduled Task Assignment", {"template": legacy.name, "building": bld}
            ),
        )
        self.assertGreaterEqual(summary["reused_templates"], 1)

    def test_no_scheduled_task_template_building_field_or_usage(self):
        """The redesign dropped ``Scheduled Task Template.building``. Prove the
        field is gone from the DocType AND that no product code constructs or queries a
        Scheduled Task Template with a ``building`` key (the breakage)."""
        self.assertIsNone(
            frappe.get_meta("Scheduled Task Template").get_field("building"),
            "Scheduled Task Template must have no 'building' field; it was dropped "
            "when the template stopped being building-scoped",
        )

        import apex

        apex_root = os.path.dirname(apex.__file__)
        this_file = os.path.abspath(__file__)
        allow = set()
        construct_re = re.compile(r'"doctype":\s*"Scheduled Task Template"')
        building_key_re = re.compile(r"""["']building["']\s*:""")
        filter_re = re.compile(
            r'"Scheduled Task Template"\s*,\s*\{[^}]*["\']building["\']'
        )

        offenders = []
        for dirpath, _dirs, files in os.walk(apex_root):
            for fn in files:
                if not fn.endswith(".py"):
                    continue
                full = os.path.join(dirpath, fn)
                if os.path.abspath(full) == this_file:
                    continue
                if os.path.relpath(full, apex_root) in allow:
                    continue
                with open(full, encoding="utf-8") as fh:
                    text = fh.read()
                for m in construct_re.finditer(text):
                    if building_key_re.search(text[m.start():m.start() + 400]):
                        offenders.append(os.path.relpath(full, apex_root))
                        break
                if filter_re.search(text):
                    offenders.append(os.path.relpath(full, apex_root))

        self.assertEqual(
            offenders, [],
            f"Scheduled Task Template.building usage must be gone; found in: {offenders}",
        )

class TestIdempotencyGuards(ApexHabitatTestCase):
    def setUp(self):
        self.company = frappe.db.get_value("Company", {}) or frappe.get_doc({
            "doctype": "Company", "company_name": "Test Company",
            "default_currency": "SAR", "country": "Saudi Arabia",
        }).insert(ignore_permissions=True).name
        self.cost_center = (
            frappe.db.get_value("Cost Center", {"is_group": 0, "company": self.company})
            or frappe.db.get_value("Cost Center", {"is_group": 0})
        )
        self.project = frappe.db.get_value("Project", {}) or frappe.get_doc({
            "doctype": "Project", "project_name": "Test Project", "company": self.company,
        }).insert(ignore_permissions=True).name
        self.employee = frappe.get_doc({
            "doctype": "Employee", "first_name": f"Test Emp {frappe.generate_hash(length=12)}",
            "company": self.company, "gender": "Male",
            "date_of_birth": "1990-01-01", "date_of_joining": "2020-01-01",
        }).insert(ignore_permissions=True).name

        self.site = frappe.get_doc({
            "doctype": "Site", "site_name": frappe.generate_hash(length=12),
        }).insert(ignore_permissions=True)

    def _make_building(self, abbr):
        b = frappe.get_doc({
            "doctype": "Building",
            "building_name": f"Bldg {abbr}",
            "abbreviation": abbr,
            "site": self.site.name,
            "total_capacity": 50,
            "default_cost_center": self.cost_center,
        })
        b.append("floor_plan", {
            "floor_number": 1,
            "starting_room_number": 1,
            "room_count": 3,
            "bed_capacity_per_room": 2,
            "room_type": "Standard",
            "generate_beds": 1,
        })
        b.insert(ignore_permissions=True)
        return b

    def test_room_generator_run_twice_creates_no_duplicates(self):
        abbr = "T" + frappe.generate_hash(length=12).upper()
        building = self._make_building(abbr)

        first = generate_rooms_and_beds(building.name)
        rooms_after_first = frappe.db.count("Room", {"building": building.name})
        beds_after_first = frappe.db.count(
            "Bed", {"room": ["in", frappe.get_all(
                "Room", {"building": building.name}, pluck="name")]}
        )

        second = generate_rooms_and_beds(building.name)
        rooms_after_second = frappe.db.count("Room", {"building": building.name})
        beds_after_second = frappe.db.count(
            "Bed", {"room": ["in", frappe.get_all(
                "Room", {"building": building.name}, pluck="name")]}
        )

        self.assertEqual(first["created_rooms"], 3)
        self.assertEqual(
            second["created_rooms"], 0,
            "Second run must create 0 rooms (all already exist).",
        )
        self.assertEqual(second["skipped_rooms"], 3)
        self.assertEqual(
            rooms_after_second, rooms_after_first,
            f"Room count changed on re-run ({rooms_after_first} -> {rooms_after_second}): duplicates created.",
        )
        self.assertEqual(
            beds_after_second, beds_after_first,
            f"Bed count changed on re-run ({beds_after_first} -> {beds_after_second}): duplicate beds created.",
        )

    def _assignment(self, building, room, bed):
        a = frappe.get_doc({
            "doctype": "Housing Assignment",
            "employee": self.employee, "project": self.project,
            "cost_center": self.cost_center, "building": building,
            "room": room, "bed": bed, "check_in_date": "2026-05-01",
            "assignment_type": "New Assignment",
        })
        a.insert(ignore_permissions=True)
        a.submit()
        return a

    def test_second_checkout_for_same_assignment_is_rejected(self):
        abbr = "C" + frappe.generate_hash(length=12).upper()
        building = self._make_building(abbr)
        generate_rooms_and_beds(building.name)
        room = frappe.get_all("Room", {"building": building.name}, pluck="name")[0]
        bed = frappe.get_all("Bed", {"room": room}, pluck="name")[0]

        assignment = self._assignment(building.name, room, bed)

        checkout1 = frappe.get_doc({
            "doctype": "Housing Checkout", "assignment": assignment.name,
            "checkout_date": "2026-05-21", "checkout_reason": "Internal Transfer",
        })
        checkout1.insert(ignore_permissions=True)
        checkout1.submit()

        checkout2 = frappe.get_doc({
            "doctype": "Housing Checkout", "assignment": assignment.name,
            "checkout_date": "2026-05-22", "checkout_reason": "Internal Transfer",
        })
        with self.assertRaises(frappe.ValidationError,
                               msg="A second checkout for the same assignment must be rejected."):
            checkout2.insert(ignore_permissions=True)
            checkout2.submit()
