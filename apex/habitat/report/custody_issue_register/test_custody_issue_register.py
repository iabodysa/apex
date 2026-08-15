# Copyright (c) 2026, AFMCO and contributors
"""A-372 — the register for what was issued, to whom, and whether it came back.

Custody Issue had no report. `Custody Outstanding by Worker` answers a different question
from a different source — a net BALANCE per (item, worker) out of the stock ledger — and a
balance cannot say which issue document a holding came from, whether it was signed for, or
whether it is past its return date.

Two states this register exists to surface, and each gets a test:

* AN ISSUE THAT WAS NEVER ACKNOWLEDGED — goods left the store against no signature.
* AN ISSUE PAST ITS EXPECTED RETURN DATE and still not Returned, which is what turns into
  a damage assessment and a payroll deduction.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, now_datetime, today

from apex.habitat.report.custody_issue_register.custody_issue_register import execute

REPORT = "Custody Issue Register"


def _h(n=8):
    return frappe.generate_hash(length=n).upper()


class TestTheCustodyIssueRegister(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.site = frappe.get_doc(
            {"doctype": "Site", "site_name": "CI " + _h()}
        ).insert(ignore_permissions=True).name
        self.addCleanup(
            frappe.delete_doc, "Site", self.site, force=True, ignore_permissions=True
        )
        self.building = frappe.get_doc(
            {
                "doctype": "Building",
                "building_name": "CI " + _h(),
                "site": self.site,
                "status": "Active",
                "total_capacity": 2,
            }
        ).insert(ignore_permissions=True, ignore_mandatory=True).name
        self.addCleanup(
            frappe.delete_doc, "Building", self.building, force=True, ignore_permissions=True
        )
        # A Custody Issue refuses to save with no item row — its own guard, not this
        # report's subject, so the fixture supplies one article for every issue.
        self.article = frappe.get_doc(
            {"doctype": "Custody Article", "article_name": "CI " + _h()}
        ).insert(ignore_permissions=True, ignore_mandatory=True).name
        self.addCleanup(
            frappe.delete_doc, "Custody Article", self.article, force=True, ignore_permissions=True
        )

    def _issue(self, *, acknowledged, return_in_days, status="Issued"):
        doc = frappe.get_doc(
            {
                "doctype": "Custody Issue",
                "issue_date": add_days(today(), -20),
                "building": self.building,
                "expected_return_date": add_days(today(), return_in_days),
                "status": status,
                "items": [{"article": self.article, "qty": 1}],
            }
        )
        if acknowledged:
            doc.acknowledged_on = now_datetime()
        doc.insert(ignore_permissions=True, ignore_mandatory=True)
        frappe.db.set_value(
            "Custody Issue", doc.name, "docstatus", 1, update_modified=False
        )
        self.addCleanup(self._drop, doc.name)
        return doc.name

    def _drop(self, name):
        frappe.db.set_value("Custody Issue", name, "docstatus", 0, update_modified=False)
        frappe.delete_doc("Custody Issue", name, force=True, ignore_permissions=True)

    def _run(self, **filters):
        filters.setdefault("building", self.building)
        return execute(filters)[:5]

    def test_the_report_is_registered_against_custody_issue(self):
        self.assertTrue(frappe.db.exists("Report", REPORT))
        self.assertEqual(
            frappe.db.get_value("Report", REPORT, "ref_doctype"), "Custody Issue"
        )

    def test_an_unacknowledged_issue_is_flagged(self):
        """Goods left the store against no signature — a balance cannot show this."""
        name = self._issue(acknowledged=False, return_in_days=30)
        _c, data, _m, _ch, summary = self._run()
        self.assertEqual([r["name"] for r in data], [name])
        self.assertEqual(data[0]["acknowledged"], "No")
        self.assertEqual({c["label"]: c["value"] for c in summary}["Not Acknowledged"], 1)

    def test_an_acknowledged_issue_is_not_flagged(self):
        self._issue(acknowledged=True, return_in_days=30)
        _c, data, _m, _ch, summary = self._run()
        self.assertEqual(data[0]["acknowledged"], "Yes")
        by_label = {c["label"]: c["value"] for c in summary}
        self.assertEqual(by_label["Not Acknowledged"], 0)
        self.assertEqual(by_label["Acknowledged"], 100.0)

    def test_an_overdue_issue_carries_its_days(self):
        self._issue(acknowledged=True, return_in_days=-5)
        _c, data, _m, _ch, summary = self._run()
        self.assertEqual(data[0]["days_overdue"], 5)
        self.assertEqual({c["label"]: c["value"] for c in summary}["Overdue"], 1)

    def test_a_returned_issue_is_never_overdue(self):
        """Past its date but already back — counting it would send a supervisor chasing
        goods that are on the shelf."""
        self._issue(acknowledged=True, return_in_days=-5, status="Returned")
        _c, data, _m, _ch, summary = self._run()
        self.assertEqual(data[0]["days_overdue"], 0)
        self.assertEqual({c["label"]: c["value"] for c in summary}["Overdue"], 0)

    def test_the_overdue_filter_narrows_to_them(self):
        self._issue(acknowledged=True, return_in_days=-5)
        self._issue(acknowledged=True, return_in_days=30)
        _c, all_rows, _m, _ch, _s = self._run()
        _c, overdue, _m, _ch, _s = self._run(overdue_only=1)
        self.assertEqual(len(all_rows), 2)
        self.assertEqual(len(overdue), 1)

    def test_an_empty_register_reads_zero_rather_than_blank(self):
        _c, data, _m, _ch, summary = self._run()
        self.assertEqual(data, [])
        self.assertTrue(summary)
        self.assertEqual({c["value"] for c in summary}, {0, 0.0})
