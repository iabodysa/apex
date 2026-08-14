# Copyright (c) 2026, afmcoltd
"""The wall on Dispatch Trip goes around the fields a rider must not touch.

A rider writes one thing on a trip: their own row in ``boarding_state``. Everything else on the
document — the route, the vehicle, the driver assignment — belongs to dispatch. ``permlevel``
expresses exactly that, and it runs in the direction people get backwards: a RAISED permlevel
restricts a field, so the wall goes around what must stay untouched and the flow state stays at
level 0 where the ordinary DocPerm governs it.

Two things this proves that reading the JSON cannot. First, the framework RESETS an unauthorised
value rather than refusing the save (``base_document.py:1263``), so the assertion is on the field's
value afterwards, never on an exception. Second, ``Administrator`` is exempt and returns at
``document.py:788``, so every case here runs as a restricted user; a rehearsal as Administrator
would pass against a DocType with no wall at all.

The fixtures pass ``ignore_permissions`` on purpose: they are building the world the assertions
then run against, as Administrator, before any restricted user is set. A fixture that had to
satisfy the permission model would be testing the fixture rather than the wall.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

RIDER = "rider-permlevel@apex.test"


class TestBoardingStatePermlevel(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not frappe.db.exists("User", RIDER):
            user = frappe.get_doc({
                "doctype": "User",
                "email": RIDER,
                "first_name": "Rider",
                "send_welcome_email": 0,
                "roles": [{"role": "Driver"}],
            })
            user.insert(ignore_permissions=True)
        # Dispatch Trip is project-scoped by a has_permission hook, so the rider needs the scope
        # before permlevel is even reached. Without it the save fails on document access and the
        # field-level wall is never exercised.
        if not frappe.db.exists("Project", {"project_name": "Permlevel Scope"}):
            frappe.get_doc({"doctype": "Project", "project_name": "Permlevel Scope"}).insert(
                ignore_permissions=True
            )
        cls.project = frappe.db.get_value("Project", {"project_name": "Permlevel Scope"}, "name")
        if not frappe.db.exists("User Permission", {"user": RIDER, "for_value": cls.project}):
            frappe.get_doc({
                "doctype": "User Permission",
                "user": RIDER,
                "allow": "Project",
                "for_value": cls.project,
            }).insert(ignore_permissions=True)
        cls.trip = frappe.get_doc({
            "doctype": "Dispatch Trip",
            "trip_type": "Ad Hoc",
            "trip_date": frappe.utils.today(),
            "status": "Planned",
            "project": cls.project,
        })
        cls.trip.insert(ignore_permissions=True)

    def setUp(self):
        frappe.set_user(RIDER)
        self.addCleanup(frappe.set_user, "Administrator")

    def test_the_flow_state_stays_writable(self):
        """boarding_state is left at permlevel 0, so the Driver role's ordinary write reaches it."""
        trip = frappe.get_doc("Dispatch Trip", self.trip.name)
        trip.append("boarding_state", {"status": "Pending", "notify_count": 0, "wait_count": 0})
        trip.save()
        self.assertEqual(len(frappe.get_doc("Dispatch Trip", self.trip.name).boarding_state), 1)

    def test_a_protected_field_is_reset_not_refused(self):
        """The vehicle sits at permlevel 1: the save succeeds and the value does not move."""
        trip = frappe.get_doc("Dispatch Trip", self.trip.name)
        before = trip.trip_title
        trip.trip_title = "rider rewrote this"
        trip.save()
        self.assertEqual(frappe.get_doc("Dispatch Trip", self.trip.name).trip_title, before)

    def test_the_wall_is_declared_where_it_belongs(self):
        """Every data field except the flow state carries the raised level."""
        meta = frappe.get_meta("Dispatch Trip")
        layout = {"Section Break", "Column Break", "Tab Break"}
        open_fields = [
            df.fieldname for df in meta.fields
            if df.fieldtype not in layout and not df.permlevel
        ]
        self.assertEqual(open_fields, ["boarding_state"])
