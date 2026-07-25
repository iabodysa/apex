# Copyright (c) 2026, AFMCO and contributors
"""Colocated tests for the Rental Settlement controller — the accrual-stamping
half of the reconciliation, viewed from the settlement side.

The cross-role Workflow controls (Reconcile/Approve/Mark Paid role gates, the
Segregation-of-Duties conditions, the no-GL boundary) are covered in
``apex/tests/test_rental_settlement_workflow.py``. These colocated tests
add the settlement -> Rental Accrual Ledger stamping behavior the controller now
owns: on reaching a settled state it stamps its office+period accrual rows, and
on cancel it releases them. They also carry the ``test_ignore`` that lets
``bench run-tests --doctype "Rental Settlement"`` resolve dependencies without
the ERPNext finance chain (Salis Payment Request -> Payment Entry -> Payment
Gateway) that is not installed in the CI bench.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import get_first_day, getdate, today

from apex.salis import rental_engine
from apex.tests._helpers import _user
from apex.tests._helpers import approve_rental_settlement
from apex.tests.factories import make_rental_office, make_vehicle

LEDGER = "Rental Accrual Ledger"

# [#qd5yeu]
test_ignore = [
    "Company",
    "Cost Center",
    "Employee",
    "Mode of Payment",
    "Payment Entry",
    "Payment Gateway",
    "Project",
    "Salis Payment Request",
    "Salis Vehicle",
    "Role",
    "Supplier",
    "User",
]


def _settled(name):
    return frappe.db.get_value(LEDGER, name, ["settled", "rental_settlement"], as_dict=True)


class TestRentalSettlementStamping(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        # [#41w3ao]
        self.requester = _user("rss_req@example.com", "Fleet Project Manager")
        self.manager = _user("rss_mgr@example.com", "Fleet Manager")
        self.office = make_rental_office("RSS Stamp Office")
        self.vehicle = make_vehicle("RSS STAMP 1", ownership="Rented")
        self.period = today()[:7]
        self.accrual_date = str(get_first_day(getdate(today())))

    def tearDown(self):
        frappe.set_user("Administrator")

    def _accrual_row(self, amount=100.0):
        row = frappe.get_doc(
            {
                "doctype": LEDGER,
                "vehicle": self.vehicle,
                "rental_office": self.office,
                "accrual_date": self.accrual_date,
                "daily_rate": amount,
                "amount": amount,
                "settled": 0,
            }
        ).insert(ignore_permissions=True)
        self.addCleanup(lambda n=row.name: frappe.db.delete(LEDGER, {"name": n}))
        return row.name

    def _settlement(self, claimed=1000):
        rs = frappe.get_doc(
            {
                "doctype": "Rental Settlement",
                "rental_office": self.office,
                "period_month": self.period,
                "claimed_total": claimed,
                "requested_by": self.requester,
                "status": "Draft",
            }
        ).insert(ignore_permissions=True)
        self.addCleanup(lambda n=rs.name: self._purge(n))
        return rs

    def _purge(self, name):
        frappe.set_user("Administrator")
        if not frappe.db.exists("Rental Settlement", name):
            return
        rental_engine.release_settlement(name)
        doc = frappe.get_doc("Rental Settlement", name)
        if doc.docstatus == 1:
            doc.cancel()
        frappe.delete_doc("Rental Settlement", name, force=True, ignore_permissions=True)

    def test_submit_stamps_then_cancel_releases(self):
        row = self._accrual_row()
        rs = self._settlement()

        # [#ffzyph]
        self.assertEqual(_settled(row).settled, 0)
        self.assertIsNone(_settled(row).rental_settlement)

        approve_rental_settlement(rs, self.manager)
        s = _settled(row)
        self.assertEqual(s.settled, 1, "Approve/submit must stamp the accrual row settled.")
        self.assertEqual(s.rental_settlement, rs.name, "The row must link back to the settlement.")

        frappe.set_user("Administrator")
        frappe.get_doc("Rental Settlement", rs.name).cancel()
        s2 = _settled(row)
        self.assertEqual(s2.settled, 0, "Cancel must release the row.")
        self.assertIsNone(s2.rental_settlement, "Cancel must clear the link.")

    def test_validate_cross_checks_ledger_total(self):
        # [#3o3afb]
        self._accrual_row(amount=100)
        r2 = frappe.get_doc(
            {
                "doctype": LEDGER, "vehicle": self.vehicle, "rental_office": self.office,
                "accrual_date": str(getdate(self.accrual_date).replace(day=2)),
                "daily_rate": 200, "amount": 200, "settled": 0,
            }
        ).insert(ignore_permissions=True)
        self.addCleanup(lambda: frappe.db.delete(LEDGER, {"name": r2.name}))

        rs = self._settlement(claimed=300)
        rs.reload()
        self.assertEqual(rs.ledger_accrued_total, 300.0,
                         "ledger_accrued_total must sum the linked accrual rows.")
        self.assertEqual(rs.accrued_total, 300.0,
                         "With no vehicle lines, accrued_total derives from the ledger.")
        self.assertEqual(rs.ledger_variance, 0.0)
