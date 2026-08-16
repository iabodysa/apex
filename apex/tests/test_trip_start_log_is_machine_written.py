# Copyright (c) 2026, AFMCO and contributors
"""Trip Start Log is meant to be machine-written: no role may create or write one.

Every code path that writes a Trip Start Log bypasses permissions — the four driver-portal
endpoints (``salis/api/driver_portal/execution.py``), the boarding flow
(``salis/api/boarding_flow.py``), the scan path (``salis/api/boarding.py``), the Masar worker
endpoints (``salis/api/masar.py``) and manual boarding (``salis/api/manual_boarding.py``) all
pass ``ignore_permissions`` or set the flag. So the DocPerm rows grant nothing the app needs,
and by the standard ERPNext applies to GL Entry the bypass is meant to BE the control: no role
holds create or write, and the machine writes past it.

Two legs, because they fail for different reasons and a reader must be told which:

  1. the shipped JSON — what the app installs on a fresh site;
  2. the live site — what the framework actually refuses, resolved through DocPerm rows,
     the ``project_scoped_has_permission`` hook and the real insert path.

``in_create`` does NOT make leg 2 pass on its own: ``frappe/utils/user.py`` moves the DocType
out of ``can_create`` and folds it back into ``can_write``, which hides the desk's New button
and refuses nothing server-side. Neither does the DocType's ``read_only``, which is a form
affordance. The refusal has to come from the DocPerm rows, so those are what is read.

Leg 2 runs as a real Fleet Manager. Running it as Administrator would prove nothing:
``document.py`` exempts Administrator from the permission check outright.
"""

import json
import pathlib
import unittest

import frappe

import apex
from apex.tests._helpers import _user, as_user
from apex.tests.factories import (
    make_driver_chain,
    make_masar_building,
    make_project,
    make_worker_employee,
    make_worker_trip,
    purge_doc,
)

_JSON = (
    pathlib.Path(apex.__file__).resolve().parent
    / "salis"
    / "doctype"
    / "trip_start_log"
    / "trip_start_log.json"
)

DOCTYPE = "Trip Start Log"
WRITE_PTYPES = ("create", "write")


def _shipped_permissions():
    """The DocPerm rows the app ships for Trip Start Log."""
    return json.loads(_JSON.read_text())["permissions"]


def _grants(row):
    """The write-granting flags this row carries at permlevel 0.

    A row with no ``permlevel`` key is a permlevel 0 row — the level ordinary DocPerm
    governs. A raised permlevel only ever RESTRICTS a subset of fields, so a row above 0
    can neither grant nor withhold the document-level create/write this asserts on.
    """
    if int(row.get("permlevel") or 0) != 0:
        return []
    return [ptype for ptype in WRITE_PTYPES if row.get(ptype) == 1]


class TestTripStartLogShippedDocPerms(unittest.TestCase):
    """The JSON leg — no site required."""

    def test_no_role_is_shipped_create_or_write(self):
        rows = _shipped_permissions()
        # A DocType with no permission rows at all would pass the loop below having
        # graded nothing; the shipped file has rows and the count is the proof it read them.
        self.assertTrue(rows, f"{_JSON} carries no permission rows to grade")

        offenders = sorted(
            (row.get("role"), ptype) for row in rows for ptype in _grants(row)
        )
        self.assertEqual(
            offenders,
            [],
            f"{DOCTYPE} is machine-written; these shipped DocPerm rows grant a write at "
            f"permlevel 0: {offenders}",
        )


class TestTripStartLogRefusesARoleHolder(unittest.TestCase):
    """The live leg — what the framework refuses on the site."""

    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cls.fleet_manager = _user("a526.fleet.manager@example.com", "Fleet Manager")
        cls.project = make_project("A526 Trip Start Log Project")
        cls.building = make_masar_building("A526 Trip Start Log Building")
        cls.driver, _email = make_driver_chain("a526.driver@example.com", "A526 Driver")
        cls.worker = make_worker_employee("A526 Worker")
        cls.tr, cls.rp, cls.dt = make_worker_trip(
            cls.driver,
            cls.project,
            cls.building,
            [cls.worker],
            "A526 Trip Start Log Route",
        )

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        for log in frappe.get_all(
            DOCTYPE, filters={"dispatch_trip": cls.dt.name}, pluck="name"
        ):
            purge_doc(DOCTYPE, log)
        purge_doc("Dispatch Trip", cls.dt.name)
        purge_doc("Route Plan", cls.rp.name)
        purge_doc("Transport Request", cls.tr.name)

    def setUp(self):
        frappe.set_user("Administrator")
        self.addCleanup(frappe.set_user, "Administrator")

    def test_has_permission_refuses_a_fleet_manager(self):
        """The gate the framework consults before any write."""
        for ptype in WRITE_PTYPES:
            with self.subTest(ptype=ptype):
                self.assertFalse(
                    frappe.has_permission(DOCTYPE, ptype, user=self.fleet_manager),
                    f"a Fleet Manager holds {ptype} on {DOCTYPE}; it is machine-written",
                )

    def test_a_fleet_manager_cannot_insert_one(self):
        """The end-to-end refusal: ``Document.insert`` checks create before validate,
        so a role that cannot create is stopped before any field rule is reached."""
        doc = frappe.get_doc(
            {
                "doctype": DOCTYPE,
                "dispatch_trip": self.dt.name,
                "status": "Started",
                "start_datetime": frappe.utils.now_datetime(),
            }
        )
        with as_user(self.fleet_manager):
            self.assertNotEqual(
                frappe.session.user,
                "Administrator",
                "this leg must not run as Administrator — document.py exempts it",
            )
            with self.assertRaises(frappe.PermissionError):
                doc.insert()

        if doc.get("name") and frappe.db.exists(DOCTYPE, doc.name):
            self.addCleanup(purge_doc, DOCTYPE, doc.name)


if __name__ == "__main__":
    unittest.main()
