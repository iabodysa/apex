# Copyright (c) 2026, AFMCO and contributors
"""the register for the resident request queue.

Resident Request had no report. A coordinator saw the queue only as a list view, which
shows rows but not the two things that decide what to do next: how long each has waited,
and which of them nobody has taken.

Two rules this report turns on, and each is a test because each is easy to get wrong:

* SETTLED IS A NAMED STATUS SET, not a date. A Rejected request is settled without ever
  being closed, so reading `closed_on` alone leaves it in the queue forever.
* UNASSIGNED IS NOT A STATUS. A request can be Triaged, In Progress or Waiting Evidence
  and still carry no assignee — the state where a queue quietly stops moving because
  everyone assumes someone else has it.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime

from apex.habitat.report.resident_request_register.resident_request_register import execute

REPORT = "Resident Request Register"


def _h(n=12):
    return frappe.generate_hash(length=n).upper()


class TestTheResidentRequestRegister(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.site = frappe.get_doc(
            {"doctype": "Site", "site_name": "RR " + _h()}
        ).insert(ignore_permissions=True).name
        self.addCleanup(
            frappe.delete_doc, "Site", self.site, force=True, ignore_permissions=True
        )
        self.building = frappe.get_doc(
            {
                "doctype": "Building",
                "building_name": "RR " + _h(),
                "site": self.site,
                "status": "Active",
                "total_capacity": 2,
            }
        ).insert(ignore_permissions=True, ignore_mandatory=True).name
        self.addCleanup(
            frappe.delete_doc, "Building", self.building, force=True, ignore_permissions=True
        )

    def _request(self, *, status="New", priority="Medium", assigned=None, days_old=0):
        doc = frappe.get_doc(
            {
                "doctype": "Resident Request",
                "building": self.building,
                "worker_name": "RR " + _h(12),
                "priority": priority,
                "status": status,
                "assigned_to": assigned,
                # Resident Request refuses to close or resolve without notes — its own
                # guard, not this report's subject.
                "resolution_notes": "RR fixture" if status in ("Resolved", "Closed") else None,
            }
        )
        doc.insert(ignore_permissions=True, ignore_mandatory=True)
        if days_old:
            frappe.db.set_value(
                "Resident Request",
                doc.name,
                "creation",
                add_to_date(now_datetime(), days=-days_old),
                update_modified=False,
            )
        self.addCleanup(
            frappe.delete_doc, "Resident Request", doc.name, force=True, ignore_permissions=True
        )
        return doc.name

    def _run(self, **filters):
        filters.setdefault("building", self.building)
        return execute(filters)[:5]

    def test_the_report_is_registered_against_resident_request(self):
        self.assertTrue(frappe.db.exists("Report", REPORT))
        self.assertEqual(
            frappe.db.get_value("Report", REPORT, "ref_doctype"), "Resident Request"
        )

    def test_an_open_request_is_listed_with_its_age(self):
        name = self._request(days_old=3)
        _c, data, _m, _ch, _s = self._run()
        self.assertEqual([r["name"] for r in data], [name])
        self.assertEqual(data[0]["days_waiting"], 3)

    def test_a_rejected_request_leaves_the_queue_without_ever_being_closed(self):
        """The trap: settled is a named status set, not a date. A Rejected request has no
        closed_on, so a report reading the date would keep it in the queue forever."""
        self._request(status="Rejected")
        _c, data, _m, _ch, _s = self._run()
        self.assertEqual(data, [])

    def test_a_settled_request_can_still_be_asked_for(self):
        name = self._request(status="Closed")
        _c, data, _m, _ch, _s = self._run(include_settled=1)
        self.assertEqual([r["name"] for r in data], [name])

    def test_unassigned_is_counted_across_statuses_not_just_new(self):
        """A request can be In Progress and still carry no assignee — the state where a
        queue stops moving because everyone assumes someone else has it."""
        self._request(status="In Progress", assigned=None)
        self._request(status="New", assigned="Administrator")
        _c, data, _m, _ch, summary = self._run()
        self.assertEqual(len(data), 2)
        by_label = {c["label"]: c["value"] for c in summary}
        self.assertEqual(by_label["Unassigned"], 1)

    def test_the_unassigned_filter_narrows_to_them(self):
        self._request(assigned=None)
        self._request(assigned="Administrator")
        _c, all_rows, _m, _ch, _s = self._run()
        _c, only, _m, _ch, _s = self._run(unassigned_only=1)
        self.assertEqual(len(all_rows), 2)
        self.assertEqual(len(only), 1)
        self.assertEqual(only[0]["owner_taken"], "No")

    def test_the_strip_counts_urgent_and_ageing(self):
        self._request(priority="Critical", days_old=10)
        self._request(priority="Low", days_old=1)
        _c, data, _m, _ch, summary = self._run()
        by_label = {c["label"]: c["value"] for c in summary}
        self.assertEqual(by_label["Requests"], 2)
        self.assertEqual(by_label["High or Critical"], 1)
        self.assertEqual(by_label["Waiting Over a Week"], 50.0)

    def test_an_empty_queue_reads_zero_rather_than_blank(self):
        _c, data, _m, _ch, summary = self._run()
        self.assertEqual(data, [])
        self.assertTrue(summary)
        self.assertEqual({c["value"] for c in summary}, {0, 0.0})
