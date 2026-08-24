# Copyright (c) 2026, afmcoltd
from frappe.utils import flt


def apply_vat(doc, base):
    base = flt(base)
    rate = flt(doc.get("tax_rate"))
    doc.tax_amount = flt(base * rate / 100.0, doc.precision("tax_amount"))
    doc.grand_total = flt(base + doc.tax_amount, doc.precision("grand_total"))
