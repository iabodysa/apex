# Copyright (c) 2026, AFMCO and contributors
"""Unit tests for logistay.utils.normalize (SIM identifier comparison keys).

Pure stdlib ``re`` — no DB / live site — so a plain unittest TestCase that
exercises the strip / leading-plus / upper-case rules directly.
"""

from __future__ import annotations

import unittest

from apex.logistay.utils.normalize import normalize_iccid, normalize_msisdn


class TestNormalizeMsisdn(unittest.TestCase):
    def test_strips_spaces_dashes_and_parentheses(self):
        self.assertEqual(normalize_msisdn("055 123 4567"), "0551234567")
        self.assertEqual(normalize_msisdn("(055) 123-4567"), "0551234567")

    def test_keeps_only_a_single_leading_plus(self):
        self.assertEqual(normalize_msisdn("+966 55 123 4567"), "+966551234567")
        self.assertEqual(normalize_msisdn("++966"), "+966")

    def test_internal_plus_is_dropped(self):
        self.assertEqual(normalize_msisdn("00+55"), "0055")

    def test_empty_none_and_noise_return_none(self):
        self.assertIsNone(normalize_msisdn(None))
        self.assertIsNone(normalize_msisdn(""))
        self.assertIsNone(normalize_msisdn("   "))
        self.assertIsNone(normalize_msisdn("abc"))


class TestNormalizeIccid(unittest.TestCase):
    def test_strips_separators_and_uppercases(self):
        self.assertEqual(normalize_iccid("8996 1100 0000 0000 001"), "8996110000000000001")
        self.assertEqual(normalize_iccid("89ab-cd"), "89ABCD")

    def test_empty_none_and_all_separators_return_none(self):
        self.assertIsNone(normalize_iccid(None))
        self.assertIsNone(normalize_iccid(""))
        self.assertIsNone(normalize_iccid("----"))


if __name__ == "__main__":
    unittest.main()
