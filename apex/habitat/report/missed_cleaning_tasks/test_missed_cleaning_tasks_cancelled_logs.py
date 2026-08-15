# Copyright (c) 2026, AFMCO and contributors
"""A-416 — a cancelled cleaning log is not a missed cleaning task.

Missed Cleaning Tasks queried Cleaning Log with NO docstatus filter, so a log someone
cancelled was still reported as missed — sending a supervisor after a record that had been
withdrawn. Both of its queries now exclude docstatus 2.

Drafts are deliberately KEPT. The study guessed that one of this report and Daily Cleaning
Compliance had a wrong filter, because this one returns 30 rows and that one returns 0 from
what looked like the same data. Neither filter is wrong: Daily Cleaning Compliance reads the
Cleaning Compliance Ledger, which is only written on SUBMIT, and on the measured site all 15
cleaning logs are drafts and none has ever been submitted. Excluding drafts here would empty
this report too rather than correct it.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from apex.habitat.report.missed_cleaning_tasks.missed_cleaning_tasks import execute


def _h(n=8):
    return frappe.generate_hash(length=n).upper()


class TestMissedCleaningTasksIgnoresCancelled(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.site = frappe.get_doc(
            {"doctype": "Site", "site_name": "MC " + _h()}
        ).insert(ignore_permissions=True).name
        self.addCleanup(
            frappe.delete_doc, "Site", self.site, force=True, ignore_permissions=True
        )
        self.building = frappe.get_doc(
            {
                "doctype": "Building",
                "building_name": "MC " + _h(),
                "site": self.site,
                "status": "Active",
                "total_capacity": 2,
            }
        ).insert(ignore_permissions=True, ignore_mandatory=True).name
        self.addCleanup(
            frappe.delete_doc, "Building", self.building, force=True, ignore_permissions=True
        )

    def _log(self, *, docstatus, missed=1, rework=0):
        doc = frappe.get_doc(
            {
                "doctype": "Cleaning Log",
                "cleaning_date": today(),
                "building": self.building,
                "missed_cleaning": missed,
                "rework_required": rework,
                "missed_reason": "MC fixture" if missed else None,
            }
        )
        doc.insert(ignore_permissions=True, ignore_mandatory=True)
        if docstatus:
            frappe.db.set_value(
                "Cleaning Log", doc.name, "docstatus", docstatus, update_modified=False
            )
        self.addCleanup(self._drop, doc.name)
        return doc.name

    def _drop(self, name):
        frappe.db.set_value("Cleaning Log", name, "docstatus", 0, update_modified=False)
        frappe.delete_doc("Cleaning Log", name, force=True, ignore_permissions=True)

    def _rows(self):
        return execute({"building": self.building})[1]

    def test_a_cancelled_log_is_not_reported_as_missed(self):
        """The defect: a withdrawn record still sent a supervisor after it."""
        self._log(docstatus=2)
        self.assertEqual(self._rows(), [])

    def test_a_cancelled_log_is_not_reported_as_rework_either(self):
        """Both queries had the same hole, so both get the same test."""
        self._log(docstatus=2, missed=0, rework=1)
        self.assertEqual(self._rows(), [])

    def test_a_draft_log_is_still_reported(self):
        """Deliberate: on a site that never submits a cleaning log, excluding drafts
        would empty this report rather than correct it."""
        name = self._log(docstatus=0)
        self.assertEqual([r["name"] for r in self._rows()], [name])

    def test_a_submitted_log_is_reported(self):
        name = self._log(docstatus=1)
        self.assertEqual([r["name"] for r in self._rows()], [name])
