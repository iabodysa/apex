# Copyright (c) 2026, afmcoltd
"""What a Subcontractor Service Contract guarantees, asserted against the DocType itself.

Patterned on frappe's own document-validation tests (``frappe/tests/test_document.py``,
``test_validate`` / ``test_validate_from_to_dates``). ``validate`` carries three
behaviours: it refuses a Contract End before Contract Start, it defaults ``company`` to
the Habitat default when none is given, and it derives ``tax_amount``/``grand_total`` from
whichever base rate the contract states (``monthly_retainer`` or ``rate_per_visit``) via
the shared ``apply_vat`` helper — a no-GL contract states only the rate, the tax, and the
total, never a charges table.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

test_dependencies = ["Supplier"]


class TestSubcontractorServiceContract(FrappeTestCase):
    def test_a_contract_end_before_start_is_refused(self):
        """A contract that ends before it starts is a term nobody can act on."""
        contract = frappe.copy_doc(
            frappe.get_test_records("Subcontractor Service Contract")[0]
        )
        contract.contract_start_date = "2026-06-01"
        contract.contract_end_date = "2026-01-01"

        with self.assertRaisesRegex(
            frappe.ValidationError, "cannot be before Contract Start"
        ):
            contract.insert()

    def test_a_contract_with_a_valid_date_range_defaults_its_company_and_is_accepted(self):
        """The acceptance baseline the refusal above deviates from; also proves the
        default-company convenience actually fires when none is given, rather than
        leaving the field silently blank."""
        from apex.apex_core.doctype.habitat_settings.habitat_settings import (
            get_default_company,
        )

        contract = frappe.copy_doc(
            frappe.get_test_records("Subcontractor Service Contract")[0]
        )
        contract.insert()

        self.assertEqual(contract.company, get_default_company())

    def test_the_grand_total_is_computed_from_the_base_rate_and_tax_rate(self):
        """A signed contract must state a total that agrees with its own rate and tax —
        pins the arithmetic ``apply_vat`` performs on whichever base the contract uses."""
        contract = frappe.copy_doc(
            frappe.get_test_records("Subcontractor Service Contract")[1]
        )
        self.assertFalse(contract.rate_per_visit)
        self.assertEqual(contract.monthly_retainer, 1200)
        contract.tax_rate = 15

        contract.insert()

        self.assertEqual(contract.tax_amount, 180)
        self.assertEqual(contract.grand_total, 1380)
