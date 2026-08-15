# Copyright (c) 2026, AFMCO and contributors
"""the register for what came back, and in what condition.

Custody Return had no report, so the condition an article returned in was visible only by
opening one return at a time. That condition is the field with money behind it: a line
returned Damaged or Lost is what a Custody Damage Assessment is raised from, and that
assessment becomes a payroll deduction.

THE ROWS ARE ITEM LINES, NOT DOCUMENTS, and that is the decision this report turns on. A
return of three articles where one is damaged is ONE document and THREE lines. Rolling it
up to the document would let the register say "returned" about a return that carries a
loss — the single line that matters would disappear inside a header.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from apex.habitat.report.custody_return_register.custody_return_register import execute

REPORT = "Custody Return Register"


def _h(n=8):
    return frappe.generate_hash(length=n).upper()


class TestTheCustodyReturnRegister(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.site = frappe.get_doc(
            {"doctype": "Site", "site_name": "CR " + _h()}
        ).insert(ignore_permissions=True).name
        self.addCleanup(
            frappe.delete_doc, "Site", self.site, force=True, ignore_permissions=True
        )
        self.building = frappe.get_doc(
            {
                "doctype": "Building",
                "building_name": "CR " + _h(),
                "site": self.site,
                "status": "Active",
                "total_capacity": 2,
            }
        ).insert(ignore_permissions=True, ignore_mandatory=True).name
        self.addCleanup(
            frappe.delete_doc, "Building", self.building, force=True, ignore_permissions=True
        )
        self.article = frappe.get_doc(
            {"doctype": "Custody Article", "article_name": "CR " + _h()}
        ).insert(ignore_permissions=True, ignore_mandatory=True).name
        self.addCleanup(
            frappe.delete_doc, "Custody Article", self.article, force=True, ignore_permissions=True
        )

    def _return(self, conditions):
        """One submitted return carrying one line per condition given."""
        doc = frappe.get_doc(
            {
                "doctype": "Custody Return",
                "return_date": today(),
                "building": self.building,
                "items": [
                    {"article": self.article, "qty": 1, "condition_on_return": c}
                    for c in conditions
                ],
            }
        )
        doc.insert(ignore_permissions=True, ignore_mandatory=True)
        frappe.db.set_value(
            "Custody Return", doc.name, "docstatus", 1, update_modified=False
        )
        self.addCleanup(self._drop, doc.name)
        return doc.name

    def _drop(self, name):
        frappe.db.set_value("Custody Return", name, "docstatus", 0, update_modified=False)
        frappe.delete_doc("Custody Return", name, force=True, ignore_permissions=True)

    def _run(self, **filters):
        filters.setdefault("building", self.building)
        return execute(filters)[:5]

    def test_the_report_is_registered_against_custody_return(self):
        self.assertTrue(frappe.db.exists("Report", REPORT))
        self.assertEqual(
            frappe.db.get_value("Report", REPORT, "ref_doctype"), "Custody Return"
        )

    def test_one_document_with_three_articles_is_three_rows(self):
        """The decision the report turns on. Rolled up to the document, the damaged line
        would vanish inside a header that reads 'returned'."""
        name = self._return(["Good", "Good", "Damaged"])
        _c, data, _m, _ch, summary = self._run()
        self.assertEqual(len(data), 3)
        self.assertEqual({r["name"] for r in data}, {name})
        by_label = {c["label"]: c["value"] for c in summary}
        self.assertEqual(by_label["Returned Lines"], 3)
        self.assertEqual(by_label["Returns"], 1)

    def test_a_damaged_line_is_chargeable(self):
        self._return(["Damaged"])
        _c, data, _m, _ch, summary = self._run()
        self.assertEqual(data[0]["chargeable"], "Yes")
        self.assertEqual({c["label"]: c["value"] for c in summary}["Damaged or Lost"], 1)

    def test_a_lost_line_is_chargeable_too(self):
        self._return(["Lost"])
        _c, data, _m, _ch, _s = self._run()
        self.assertEqual(data[0]["chargeable"], "Yes")

    def test_a_fair_line_is_not_chargeable(self):
        """Fair is worn, not owed for — charging it would bill a worker for normal use."""
        self._return(["Fair"])
        _c, data, _m, _ch, summary = self._run()
        self.assertEqual(data[0]["chargeable"], "No")
        self.assertEqual({c["label"]: c["value"] for c in summary}["Damaged or Lost"], 0)

    def test_the_chargeable_filter_narrows_to_them(self):
        self._return(["Good", "Lost"])
        _c, all_rows, _m, _ch, _s = self._run()
        _c, only, _m, _ch, _s = self._run(chargeable_only=1)
        self.assertEqual(len(all_rows), 2)
        self.assertEqual(len(only), 1)
        self.assertEqual(only[0]["condition_on_return"], "Lost")

    def test_the_good_order_share_counts_lines(self):
        self._return(["Good", "Good", "Damaged", "Lost"])
        _c, _data, _m, _ch, summary = self._run()
        self.assertEqual(
            {c["label"]: c["value"] for c in summary}["Returned in Good Order"], 50.0
        )

    def test_an_empty_register_reads_zero_rather_than_blank(self):
        _c, data, _m, _ch, summary = self._run()
        self.assertEqual(data, [])
        self.assertTrue(summary)
        self.assertEqual({c["value"] for c in summary}, {0, 0.0})
