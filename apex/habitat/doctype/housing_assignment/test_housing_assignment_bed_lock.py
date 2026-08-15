# Copyright (c) 2026, AFMCO and contributors
"""Two residents must never be handed the same bed.

``on_submit`` decides on the bed's status. Serialising the writers is not enough on its
own: this transaction's REPEATABLE READ view is established before the lock is taken, so a
``FOR UPDATE`` whose result is discarded followed by a plain read still answers from the
old snapshot — the winner's committed row is invisible and both assignments take the bed.
The lock and the decision therefore have to be the SAME statement, which is what
``for_update=True`` on the deciding read gives.

Concurrency is not reproduced here — two connections inside one test transaction would
deadlock on the fixture rows. What is graded is the property that makes the race
impossible: the SQL the production submit path actually emits. That is the same way the
fuel-quota lock is graded in ``apex/salis/utils/test_salis_utils.py``.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Bed", "Employee"]

BUILDING = "_Test Building"
ROOM = "_T-101"


class TestHousingAssignmentBedLock(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        self.company = frappe.db.get_value("Building", BUILDING, "company")
        # ERPNext's Project fixture is not idempotent (autoname mints a new name while
        # project_name carries a unique index), so the one already on the site is read.
        self.project = frappe.db.get_value("Project", {"project_name": "_Test Project"})
        self.bed = frappe.db.get_value("Bed", {"room": ROOM, "status": "Available"})
        self.assertTrue(self.bed, "the shipped Bed fixture must provide a free bed")
        # Shared fixtures are handed back: FrappeTestCase rolls back once per CLASS
        # (frappe/tests/utils.py:46), so a bed left Occupied outlives this method.
        self.addCleanup(frappe.db.set_value, "Bed", self.bed, "status", "Available")

    def _employee(self):
        """A fresh Employee every time: the controller refuses a second live assignment
        for the same worker, so a shared one makes this file's result depend on whatever
        else on the bench is currently housing him."""
        return frappe.get_doc({
            "doctype": "Employee",
            "first_name": "_T Bed Lock " + frappe.generate_hash(length=8),
            "company": self.company,
            "status": "Active",
            "gender": "Male",
            "date_of_birth": "1990-01-01",
            "date_of_joining": "2020-01-01",
        }).insert(ignore_permissions=True, ignore_mandatory=True).name

    def _assignment(self, check_in="2026-05-01"):
        doc = frappe.get_doc({
            "doctype": "Housing Assignment",
            "party_type": "Employee",
            "party": self._employee(),
            "building": BUILDING,
            "room": ROOM,
            "bed": self.bed,
            "assignment_type": "New Assignment",
            "stay_type": "Permanent",
            "check_in_date": check_in,
            "project": self.project,
        })
        doc.insert(ignore_permissions=True)
        return doc

    def _submit_capturing_sql(self, doc):
        captured: list[str] = []
        real_sql = frappe.db.sql

        def _recording_sql(query, *args, **kwargs):
            captured.append(str(query))
            return real_sql(query, *args, **kwargs)

        frappe.db.sql = _recording_sql
        try:
            doc.submit()
        finally:
            frappe.db.sql = real_sql
        return captured

    def test_the_bed_status_is_decided_by_a_locking_read(self):
        captured = self._submit_capturing_sql(self._assignment())
        locking = [
            q for q in captured
            if "`tabBed`" in q and "FOR UPDATE" in q.upper() and "SELECT" in q.upper()
        ]
        self.assertTrue(
            locking,
            "submitting an assignment must read Bed.status FOR UPDATE — a plain read "
            f"answers from a snapshot taken before the lock. Captured: {captured}",
        )

    def test_a_bed_taken_after_validate_is_refused_at_submit(self):
        """The other half: the lock is only worth taking if the decision refuses.

        Both drafts are inserted while the bed is free, so the validate-time occupancy
        check passes on both — exactly the window the race opens. Only the submit-time
        locked read stands between them and a double allocation.
        """
        first = self._assignment()
        second = self._assignment(check_in="2026-05-02")

        first.submit()
        self.assertEqual(frappe.db.get_value("Bed", self.bed, "status"), "Occupied")

        with self.assertRaises(frappe.ValidationError) as caught:
            second.submit()
        message = str(caught.exception)
        self.assertIn(self.bed, message)
        self.assertIn(first.name, message)
