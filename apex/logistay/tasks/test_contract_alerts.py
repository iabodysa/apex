# Copyright (c) 2026, AFMCO and contributors
"""``contract_expiry_watch`` is the only code that can move a submitted Telecom
Contract out of Active once time, not a save, is what changed. ``validate``
derives the same Active/Expired split but Frappe never calls it again after
submit, so a contract submitted Active with a still-future end date is stuck
there once that date passes unless this task runs. The end date is pushed into
the past with a direct DB write (never a ``save()``) so the case reproduces
"time passed under a submitted, unvisited document" rather than "validate ran
again", which is the bug this task exists to close.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from apex.logistay.tasks.contract_alerts import contract_expiry_watch
from apex.tests import factories

test_ignore = ["Company", "Supplier", "Currency", "Cost Center", "Project"]


class TestContractExpiryWatch(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = factories.make_company("Test AFMCO").name

    def setUp(self):
        frappe.db.savepoint("contract_expiry_watch_test")

    def tearDown(self):
        frappe.db.rollback(save_point="contract_expiry_watch_test")

    def _contract(self, **kw):
        doc = frappe.get_doc(
            {
                "doctype": "Telecom Contract",
                "naming_series": "TEL-CTR-.YYYY.-.#####",
                "company": self.company,
                "supplier": "QA-TELECOM-SUPPLIER",
                "contract_start_date": "2026-01-01",
                "contract_end_date": add_days(today(), 30),
                "billing_frequency": "Monthly",
                "recurring_amount": 100,
                "currency": "SAR",
                **kw,
            }
        )
        doc.insert(ignore_permissions=True, ignore_links=True)
        doc.submit()
        return doc

    def test_an_active_contract_past_its_end_date_is_flipped_to_expired(self):
        doc = self._contract()
        self.assertEqual(doc.status, "Active")
        # Time passes under the submitted document: nothing re-validates it, so a
        # plain DB write is the only way to reach "Active with a past end date"
        # without the bug already re-deriving the status for us.
        frappe.db.set_value("Telecom Contract", doc.name, "contract_end_date", add_days(today(), -1))

        contract_expiry_watch()

        self.assertEqual(
            frappe.db.get_value("Telecom Contract", doc.name, "status"), "Expired"
        )

    def test_a_contract_still_within_its_period_is_left_active(self):
        doc = self._contract()
        contract_expiry_watch()
        self.assertEqual(
            frappe.db.get_value("Telecom Contract", doc.name, "status"), "Active"
        )

    def test_a_terminated_contract_is_never_reopened_into_expired(self):
        doc = self._contract()
        frappe.db.set_value("Telecom Contract", doc.name, "contract_end_date", add_days(today(), -1))
        doc.reload()
        doc.cancel()
        self.assertEqual(
            frappe.db.get_value("Telecom Contract", doc.name, "status"), "Terminated"
        )

        contract_expiry_watch()

        self.assertEqual(
            frappe.db.get_value("Telecom Contract", doc.name, "status"), "Terminated",
            "the expiry watch must never overwrite a Terminated contract",
        )
