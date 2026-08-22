# Copyright (c) 2026, afmcoltd
"""What a Freelancer guarantees, asserted against the DocType itself.

A Freelancer is an accounting-party master with no workflow: ``validate`` refuses
a contract window that does not close forward and a salary that is not positive,
then derives ``status`` from the contract end date. Each refusal carries a sibling
that proves the boundary it drew is exactly where the controller says it is.

``national_id_or_iqama`` carries a DB-level UNIQUE constraint (``on_doctype_update``
in the controller), and the two rows in ``test_records.json`` are standing fixture
rows for the whole test run, not per-test scratch — so any test that inserts a real
copy gives it its own ``national_id_or_iqama``, distinct from the fixtures' and from
every other test's, or it collides with whichever row got the shared value first.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate

test_dependencies = []


class TestFreelancer(FrappeTestCase):
    def test_a_contract_end_date_not_after_the_start_date_is_refused(self):
        """A window that does not close forward is not a contract window."""
        freelancer = frappe.copy_doc(frappe.get_test_records("Freelancer")[0])
        freelancer.contract_start_date = nowdate()
        freelancer.contract_end_date = nowdate()
        self.assertRaisesRegex(
            frappe.ValidationError,
            "must be after Contract Start Date",
            freelancer.insert,
        )

    def test_a_contract_end_date_exactly_one_day_after_the_start_date_is_accepted(self):
        """The very next day is the narrowest window the controller allows to close forward."""
        freelancer = frappe.copy_doc(frappe.get_test_records("Freelancer")[0])
        freelancer.national_id_or_iqama = "_T-9000000001"
        freelancer.contract_start_date = nowdate()
        freelancer.contract_end_date = add_days(nowdate(), 1)
        freelancer.insert()
        self.assertEqual(freelancer.contract_end_date, add_days(nowdate(), 1))

    def test_a_zero_or_negative_salary_is_refused(self):
        """A Freelancer exists to be paid; a non-positive salary is not a salary."""
        freelancer = frappe.copy_doc(frappe.get_test_records("Freelancer")[0])
        freelancer.monthly_salary = 0
        self.assertRaisesRegex(
            frappe.ValidationError,
            "Monthly Salary must be greater than zero",
            freelancer.insert,
        )

    def test_a_small_positive_salary_is_accepted(self):
        """Just above zero must clear the same gate that zero itself is refused by."""
        freelancer = frappe.copy_doc(frappe.get_test_records("Freelancer")[0])
        freelancer.national_id_or_iqama = "_T-9000000002"
        freelancer.monthly_salary = 0.01
        freelancer.insert()
        self.assertEqual(freelancer.monthly_salary, 0.01)

    def test_status_derives_to_expired_once_the_contract_end_date_has_passed(self):
        """A Freelancer whose contract already ended must not still read Active."""
        freelancer = frappe.copy_doc(frappe.get_test_records("Freelancer")[0])
        freelancer.national_id_or_iqama = "_T-9000000003"
        freelancer.contract_start_date = add_days(nowdate(), -400)
        freelancer.contract_end_date = add_days(nowdate(), -1)
        freelancer.insert()
        self.assertEqual(freelancer.status, "Expired")

    def test_a_terminated_status_is_not_overwritten_by_expiry_derivation(self):
        """Termination is a decision an operator made; a lapsed date must not undo it."""
        freelancer = frappe.copy_doc(frappe.get_test_records("Freelancer")[0])
        freelancer.national_id_or_iqama = "_T-9000000004"
        freelancer.contract_start_date = add_days(nowdate(), -400)
        freelancer.contract_end_date = add_days(nowdate(), -1)
        freelancer.status = "Terminated"
        freelancer.insert()
        self.assertEqual(freelancer.status, "Terminated")
