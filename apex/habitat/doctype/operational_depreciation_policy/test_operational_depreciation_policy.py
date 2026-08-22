# Copyright (c) 2026, afmcoltd
"""What an Operational Depreciation Policy guarantees, asserted against the DocType itself.

Patterned on frappe's own document-validation tests (``frappe/tests/test_document.py``,
``test_mandatory`` / ``test_validate``): the only guarantee this DocType carries beyond its
schema is ``validate``'s two refusals — a non-positive useful life, and a residual value
percent outside 0-100 — so those are pinned here, each against an accepted sibling that
proves the refusal is really testing the rule and not a typo in the test itself.

``autoname`` is ``field:policy_name``, and the standing fixtures already occupy the two
``test_records.json`` names, so every case here gives its subject a policy_name of its
own rather than colliding on the primary key.
"""

import frappe
from frappe.tests.utils import FrappeTestCase


class TestOperationalDepreciationPolicy(FrappeTestCase):
    def test_a_policy_with_a_positive_useful_life_and_a_valid_residual_is_accepted(self):
        """The acceptance baseline the refusals below deviate from — if this ever stops
        inserting, the refusal tests are not exercising the rule they claim to."""
        policy = frappe.copy_doc(frappe.get_test_records("Operational Depreciation Policy")[0])
        policy.policy_name = "_Test Valid Policy Copy"
        policy.insert()

        self.assertEqual(
            frappe.db.get_value(
                "Operational Depreciation Policy", policy.name, "useful_life_years"
            ),
            5,
        )

    def test_a_non_positive_useful_life_is_refused(self):
        """A zero or negative useful life divides by zero everywhere book value is derived
        from it (Operational Depreciation Snapshot's ``_compute_book_values``), so it is
        refused at the source instead."""
        policy = frappe.copy_doc(frappe.get_test_records("Operational Depreciation Policy")[0])
        policy.policy_name = "_Test Zero Life Policy"
        policy.useful_life_years = 0

        with self.assertRaisesRegex(frappe.ValidationError, "greater than zero"):
            policy.insert()

    def test_a_residual_value_percent_above_100_is_refused(self):
        """A residual above the original cost would make depreciation add value instead of
        removing it, so a percent outside 0-100 is refused."""
        policy = frappe.copy_doc(frappe.get_test_records("Operational Depreciation Policy")[0])
        policy.policy_name = "_Test Over Residual Policy"
        policy.residual_value_pct = 150

        with self.assertRaisesRegex(frappe.ValidationError, "between 0 and 100"):
            policy.insert()
