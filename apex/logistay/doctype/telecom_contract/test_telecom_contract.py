# Copyright (c) 2026, afmcoltd
"""What a Telecom Contract guarantees, asserted against the DocType itself.

``status`` is server-derived and read-only: Draft while unsubmitted, Active or
Expired from the contract period once submitted, Terminated on cancel and never
overwritten after that. These assertions pin that derivation end to end, plus the
one refusal ``validate`` raises on an inverted contract period and the boundary
right beside it.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate

test_dependencies = []


class TestTelecomContract(FrappeTestCase):
    def test_a_contract_end_date_earlier_than_the_start_date_is_refused(self):
        """An inverted contract period describes no real agreement."""
        contract = frappe.copy_doc(frappe.get_test_records("Telecom Contract")[0])
        contract.contract_start_date = nowdate()
        contract.contract_end_date = add_days(nowdate(), -1)
        self.assertRaisesRegex(
            frappe.ValidationError,
            "cannot be earlier than Contract Start Date",
            contract.insert,
        )

    def test_a_contract_end_date_equal_to_the_start_date_is_accepted(self):
        """A same-day contract is not inverted, only degenerate, and the controller lets it through."""
        contract = frappe.copy_doc(frappe.get_test_records("Telecom Contract")[0])
        contract.contract_start_date = nowdate()
        contract.contract_end_date = nowdate()
        contract.insert()
        self.assertEqual(contract.contract_end_date, contract.contract_start_date)

    def test_an_unsubmitted_contract_reads_draft(self):
        """A contract that is not yet submitted must not read as in force."""
        contract = frappe.copy_doc(frappe.get_test_records("Telecom Contract")[0])
        contract.insert()
        self.assertEqual(contract.status, "Draft")

    def test_submitting_a_contract_whose_period_is_still_open_marks_it_active(self):
        """Submit is what makes a contract in force, and Active is that state's name."""
        contract = frappe.copy_doc(frappe.get_test_records("Telecom Contract")[0])
        contract.contract_start_date = nowdate()
        contract.contract_end_date = add_days(nowdate(), 30)
        contract.insert()
        contract.submit()
        self.assertEqual(contract.status, "Active")

    def test_submitting_a_contract_whose_period_has_passed_marks_it_expired(self):
        """A contract submitted after its own end date must not read Active."""
        contract = frappe.copy_doc(frappe.get_test_records("Telecom Contract")[0])
        contract.contract_start_date = add_days(nowdate(), -400)
        contract.contract_end_date = add_days(nowdate(), -1)
        contract.insert()
        contract.submit()
        self.assertEqual(contract.status, "Expired")

    def test_cancelling_a_contract_sets_status_terminated(self):
        """Cancel is the only path to Terminated, and it must reach it every time."""
        contract = frappe.copy_doc(frappe.get_test_records("Telecom Contract")[0])
        contract.contract_start_date = nowdate()
        contract.contract_end_date = add_days(nowdate(), 30)
        contract.insert()
        contract.submit()
        contract.cancel()
        self.assertEqual(contract.status, "Terminated")
