# Copyright (c) 2026, AFMCO and contributors
"""Masar worker "My Contacts" card endpoint.

``masar.get_worker_contacts`` resolves the worker from their personal Masar token
(the SOLE identity chokepoint — the client never supplies a worker id) and returns
the three contacts the home card shows:

  * ``building_in_charge`` — the active assignment's building
    ``responsible_supervisor`` (name + mobile);
  * ``today_driver``       — the driver of the worker's OWN today Dispatch Trip;
  * ``housing_office_number`` — the Habitat Settings office number.

These cases prove the goal and the fail-closed contract on a migrated site with no
production data: a real worker with an assignment + today's trip + the setting sees
all three; each degrades to None when its source is absent; and a blank token is
refused before any read.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from apex_habitat.salis.api import masar
from apex_habitat.tests.factories import (
    WorkerTripMixin as _WorkerTripMixin,
    make_masar_building as _building,
    make_test_driver as _ensure_test_driver,
    make_worker_employee as _employee,
    make_project as _project,
)

_OFFICE_NUMBER = "+966112223344"
_SUPERVISOR_EMAIL = "masar_contacts_supervisor@example.com"
_SUPERVISOR_MOBILE = "+966500001111"


def _supervisor_user():
    """A User wired as a building in-charge, with a mobile on file."""
    if not frappe.db.exists("User", _SUPERVISOR_EMAIL):
        frappe.get_doc(
            {
                "doctype": "User",
                "email": _SUPERVISOR_EMAIL,
                "first_name": "Masar Contacts Supervisor",
                "mobile_no": _SUPERVISOR_MOBILE,
                "send_welcome_email": 0,
            }
        ).insert(ignore_permissions=True)
    elif frappe.db.get_value("User", _SUPERVISOR_EMAIL, "mobile_no") != _SUPERVISOR_MOBILE:
        frappe.db.set_value("User", _SUPERVISOR_EMAIL, "mobile_no", _SUPERVISOR_MOBILE)
    return _SUPERVISOR_EMAIL


def _token_for(employee):
    """Issue an enabled Masar Worker Token for ``employee``; return its token."""
    existing = frappe.db.get_value("Masar Worker Token", {"employee": employee}, "name")
    if existing:
        doc = frappe.get_doc("Masar Worker Token", existing)
        if not doc.enabled:
            doc.db_set("enabled", 1)
        return doc.token
    return frappe.get_doc(
        {
            "doctype": "Masar Worker Token",
            "party_type": "Employee",
            "party": employee,
            "employee": employee,
            "enabled": 1,
        }
    ).insert(ignore_permissions=True).token


class TestMasarWorkerContacts(_WorkerTripMixin, FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.project = _project("Masar Contacts Project")
        cls.building = _building("Masar Contacts Building")
        cls.driver = _ensure_test_driver()
        cls.supervisor = _supervisor_user()
        # The active assignment's building carries the in-charge contact.
        frappe.db.set_value(
            "Building", cls.building, "responsible_supervisor", cls.supervisor
        )
        frappe.db.set_single_value("Habitat Settings", "housing_office_number", _OFFICE_NUMBER)

    @classmethod
    def tearDownClass(cls):
        # setUpClass commits a per-class Project OUTSIDE the per-method savepoint
        # rollback; delete it so the committed Project does not leak across the
        # test DB. (Site/Building/Employees are reuse-or-create shared fixtures.)
        frappe.set_user("Administrator")
        if frappe.db.exists("Project", cls.project):
            frappe.delete_doc("Project", cls.project, ignore_permissions=True, force=True)
        frappe.db.commit()
        super().tearDownClass()

    def setUp(self):
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")

    def _assign_bed(self, worker):
        """A valid submitted Accommodation Assignment for ``worker`` in the test
        building, with a freshly wired room+bed so the controller accepts it.
        Returns the assignment doc; registers full cleanup."""
        room = frappe.get_doc(
            {
                "doctype": "Room",
                "building": self.building,
                "room_number": f"MC-{worker}",
            }
        ).insert(ignore_permissions=True)
        bed = frappe.get_doc(
            {"doctype": "Bed", "room": room.name, "bed_code": f"MC-{worker}-B1"}
        ).insert(ignore_permissions=True)
        asg = frappe.get_doc(
            {
                "doctype": "Housing Assignment",
                "party_type": "Employee",
                "party": worker,
                "employee": worker,
                "building": self.building,
                "room": room.name,
                "bed": bed.name,
                "assignment_type": "New Assignment",
                "stay_type": "Permanent",
                "check_in_date": frappe.utils.today(),
                "project": self.project,
            }
        )
        asg.insert(ignore_permissions=True)
        asg.submit()
        self.addCleanup(lambda: self._purge_assignment(asg.name, room.name, bed.name))
        return asg

    @staticmethod
    def _purge_assignment(asg_name, room_name, bed_name):
        frappe.set_user("Administrator")
        if frappe.db.exists("Housing Assignment", asg_name):
            doc = frappe.get_doc("Housing Assignment", asg_name)
            if doc.docstatus == 1:
                try:
                    doc.cancel()
                except Exception:
                    pass
            frappe.delete_doc("Housing Assignment", asg_name, ignore_permissions=True, force=True)
        for dt, name in (("Bed", bed_name), ("Room", room_name)):
            if frappe.db.exists(dt, name):
                frappe.delete_doc(dt, name, ignore_permissions=True, force=True)

    def test_returns_all_three_contacts_for_real_worker(self):
        """The goal: a tokenized worker with an assignment + today's trip + the
        setting sees the building in-charge, today's driver, and the office number."""
        worker = _employee("Masar Contacts Worker A")
        self._assign_bed(worker)
        tr, rp, dt = self._worker_trip(
            self.driver, self.project, self.building, [worker], "Contacts Route A"
        )
        token = _token_for(worker)

        res = masar.get_worker_contacts(token=token)

        # building in-charge — from the building's responsible_supervisor
        self.assertIsNotNone(res["building_in_charge"], "in-charge must resolve from the assignment")
        self.assertEqual(res["building_in_charge"]["phone"], _SUPERVISOR_MOBILE)
        self.assertTrue(res["building_in_charge"]["name"])

        # today's driver — the driver of the worker's own today Dispatch Trip
        self.assertIsNotNone(res["today_driver"], "today's driver must resolve from the trip")
        self.assertEqual(
            res["today_driver"]["full_name"],
            frappe.db.get_value("Salis Driver", self.driver, "full_name"),
        )

        # housing office number — from Habitat Settings
        self.assertEqual(res["housing_office_number"], _OFFICE_NUMBER)

    def test_degrades_cleanly_without_assignment_or_trip(self):
        """A worker with no assignment and no trip today still gets a well-formed
        payload: in-charge and driver are None, the office number still shows."""
        worker = _employee("Masar Contacts Worker B")
        token = _token_for(worker)

        res = masar.get_worker_contacts(token=token)
        self.assertIsNone(res["building_in_charge"])
        self.assertIsNone(res["today_driver"])
        self.assertEqual(res["housing_office_number"], _OFFICE_NUMBER)

    def test_blank_token_is_rejected(self):
        with self.assertRaises(frappe.PermissionError):
            masar.get_worker_contacts(token="")


def tearDownModule():
    # P-148: drop this module's committed Accommodation Buildings so the suite's
    # post-run building count returns to the pre-suite baseline (see factories.py).
    from apex_habitat.tests import factories

    factories.purge_test_buildings()
