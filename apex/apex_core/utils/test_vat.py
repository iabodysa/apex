# Copyright (c) 2026, afmcoltd
"""Contract test for ``apply_vat`` fills ``tax_amount``/``grand_total``
from ``base`` and the document's own ``tax_rate``, both derived and read-only."""

from __future__ import annotations

from frappe.tests.utils import FrappeTestCase

from apex.apex_core.utils.vat import apply_vat


class _StubContract:
    """A minimal stand-in for a no-GL contract doc: ``get``/``precision`` plus
    plain attributes, without depending on any real DocType's fixtures."""

    def __init__(self, tax_rate):
        self.tax_rate = tax_rate
        self.tax_amount = None
        self.grand_total = None

    def get(self, fieldname):
        return getattr(self, fieldname, None)

    def precision(self, fieldname):
        return 2


class TestApplyVat(FrappeTestCase):
    def test_computes_tax_amount_and_grand_total(self):
        doc = _StubContract(tax_rate=15)
        apply_vat(doc, 1000)
        self.assertEqual(doc.tax_amount, 150.0)
        self.assertEqual(doc.grand_total, 1150.0)

    def test_zero_base_yields_zero_tax_and_grand_total(self):
        doc = _StubContract(tax_rate=15)
        apply_vat(doc, 0)
        self.assertEqual(doc.tax_amount, 0.0)
        self.assertEqual(doc.grand_total, 0.0)

    def test_zero_rate_yields_grand_total_equal_to_base(self):
        doc = _StubContract(tax_rate=0)
        apply_vat(doc, 500)
        self.assertEqual(doc.tax_amount, 0.0)
        self.assertEqual(doc.grand_total, 500.0)

    def test_rounds_to_the_document_precision(self):
        doc = _StubContract(tax_rate=15)
        apply_vat(doc, 33.333)
        # 33.333 * 15 / 100 = 4.99995 -> rounds to 2 dp.
        self.assertEqual(doc.tax_amount, 5.0)
        self.assertEqual(doc.grand_total, 38.33)

    def test_string_base_is_coerced_to_float(self):
        doc = _StubContract(tax_rate=15)
        apply_vat(doc, "1000")
        self.assertEqual(doc.tax_amount, 150.0)
        self.assertEqual(doc.grand_total, 1150.0)
