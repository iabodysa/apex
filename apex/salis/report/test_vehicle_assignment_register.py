# Copyright (c) 2026, AFMCO and contributors
"""A-372 — the register that answers "who has vehicle X today".

Vehicle Assignment had no report at all, so the current holder could only be read off the
vehicle one at a time and the history could only be reached by filtering a list view by
hand. It is the example the card itself names.

The rule this report turns on is easy to get wrong and is tested directly: an assignment
is LIVE when it is submitted, its status is Active AND it carries no end date. A submitted
row that someone ended keeps its Active status, so reading the status alone shows a
vehicle as held by a driver who already returned it.

The vehicle is the shipped fixture — the report filters on it, and every case drops the
assignments it hung off it, so each case sees the same empty register the fixture ships.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from apex.salis.report.vehicle_assignment_register.vehicle_assignment_register import execute

test_dependencies = ["Salis Vehicle"]

REPORT = "Vehicle Assignment Register"
PLATE = "_T ABC 1001"


class TestTheVehicleAssignmentRegister(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.vehicle = frappe.db.get_value("Salis Vehicle", {"plate_number": PLATE}, "name")

    def _assignment(self, *, ended, keep_active_status=False):
        """One submitted assignment.

        Vehicle Assignment refuses a second row while any row on the vehicle has status
        Active — its guard reads the STATUS alone, which is precisely the ambiguity this
        report resolves. So an ended fixture is moved to status Ended after insert unless
        the test is specifically about the Active-with-an-end-date row.
        """
        doc = frappe.get_doc(
            {
                "doctype": "Vehicle Assignment",
                "vehicle": self.vehicle,
                "start_date": add_days(today(), -10),
                "status": "Active",
            }
        )
        if ended:
            doc.end_date = today()
        doc.insert(ignore_permissions=True, ignore_mandatory=True)
        frappe.db.set_value(
            "Vehicle Assignment", doc.name, "docstatus", 1, update_modified=False
        )
        if ended and not keep_active_status:
            frappe.db.set_value(
                "Vehicle Assignment", doc.name, "status", "Ended", update_modified=False
            )
        self.addCleanup(self._drop, doc.name)
        return doc.name

    def _drop(self, name):
        frappe.db.set_value(
            "Vehicle Assignment", name, "docstatus", 0, update_modified=False
        )
        frappe.delete_doc(
            "Vehicle Assignment", name, force=True, ignore_permissions=True
        )

    def _rows(self, **filters):
        filters.setdefault("vehicle", self.vehicle)
        _cols, data, _msg, _chart, _summary = execute(filters)[:5]
        return data

    def test_the_report_is_registered_and_standard(self):
        self.assertTrue(frappe.db.exists("Report", REPORT))
        self.assertEqual(frappe.db.get_value("Report", REPORT, "ref_doctype"), "Vehicle Assignment")

    def test_a_live_assignment_is_listed(self):
        name = self._assignment(ended=False)
        rows = self._rows()
        self.assertEqual([r["name"] for r in rows], [name])
        self.assertEqual(rows[0]["held"], "Yes")

    def test_an_ended_assignment_is_hidden_by_default(self):
        """The defect the card names: an ended row keeps its Active status, so a report
        reading the status alone shows a vehicle as held by whoever returned it."""
        self._assignment(ended=True, keep_active_status=True)
        self.assertEqual(self._rows(), [])

    def test_an_ended_assignment_appears_with_its_history_when_asked(self):
        name = self._assignment(ended=True, keep_active_status=True)
        rows = self._rows(include_ended=1)
        self.assertEqual([r["name"] for r in rows], [name])
        self.assertEqual(rows[0]["held"], "No")
        self.assertEqual(rows[0]["days_held"], 10)

    def test_the_strip_counts_only_what_is_still_held(self):
        # Ended first: Vehicle Assignment refuses a second LIVE assignment on one
        # vehicle, which is its own guard and not this report's subject.
        self._assignment(ended=True)
        self._assignment(ended=False)
        _cols, data, _msg, _chart, summary = execute(
            {"vehicle": self.vehicle, "include_ended": 1}
        )[:5]
        self.assertEqual(len(data), 2)
        by_label = {c["label"]: c["value"] for c in summary}
        self.assertEqual(by_label["Assignments"], 2)
        self.assertEqual(by_label["Currently Held"], 1)
        self.assertEqual(by_label["Vehicles"], 1)
        self.assertEqual(by_label["Still Held"], 50.0)

    def test_an_empty_register_reads_zero_rather_than_blank(self):
        _cols, data, _msg, _chart, summary = execute({"vehicle": self.vehicle})[:5]
        self.assertEqual(data, [])
        self.assertTrue(summary)
        self.assertEqual({c["value"] for c in summary}, {0, 0.0})
