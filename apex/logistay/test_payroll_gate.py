# Copyright (c) 2026, AFMCO and contributors
"""Unit tests for the pure payroll-gate helpers.

Only ``valid_sa_iban`` is bench-free (a pure format rule), so it is unit-tested
here directly. The consent gate and release gate need a Frappe bench and are
covered by integration tests once P-190/P-193 are integrated. No real IBAN value
appears - only structural shapes.
"""

from __future__ import annotations

import unittest

from apex.logistay.payroll_gate import valid_sa_iban


class TestValidSaIban(unittest.TestCase):
    def test_none_and_empty_fail_closed(self):
        self.assertFalse(valid_sa_iban(None))
        self.assertFalse(valid_sa_iban(""))
        self.assertFalse(valid_sa_iban("   "))

    def test_wrong_country_or_length_fail(self):
        self.assertFalse(valid_sa_iban("AE" + "0" * 22))  # wrong country
        self.assertFalse(valid_sa_iban("SA" + "0" * 21))  # too short
        self.assertFalse(valid_sa_iban("SA" + "0" * 23))  # too long
        self.assertFalse(valid_sa_iban("SA" + "0" * 21 + "X"))  # non-digit body

    def test_well_formed_structure_passes(self):
        # 'SA' + 22 digits; a structural placeholder, not a real account.
        self.assertTrue(valid_sa_iban("SA" + "1" * 22))
        self.assertTrue(valid_sa_iban("sa " + "2" * 22))  # normalized (case/space)


if __name__ == "__main__":
    unittest.main()
