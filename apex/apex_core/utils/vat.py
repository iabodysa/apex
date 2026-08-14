# Copyright (c) 2026, afmcoltd
from frappe.utils import flt

DEFAULT_RATE = 15.0


def apply_vat(doc, base):
    """Fill ``tax_amount`` and ``grand_total`` from ``base`` and the document's ``tax_rate``.

    Contracts here are no-GL operational records, so ERPNext's tax-template machinery
    would drag in a charges table and a valuation path this app has no use for. What a
    signed contract must state is narrower: the rate applied, the tax on the stated
    amount, and the total the counterparty owes. Both derived fields are read-only, so
    a document can never disagree with its own arithmetic. The caller passes the base
    amount because each contract states its money differently — a rent cycle, a monthly
    retainer, a per-visit rate, a recurring telecom charge.
    """
    base = flt(base)
    rate = flt(doc.get("tax_rate"))
    doc.tax_amount = flt(base * rate / 100.0, doc.precision("tax_amount"))
    doc.grand_total = flt(base + doc.tax_amount, doc.precision("grand_total"))
