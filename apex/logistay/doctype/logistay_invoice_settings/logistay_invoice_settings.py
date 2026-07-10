# Copyright (c) 2026, AFMCO and contributors
"""Logistay Invoice Settings (Single) controller - deployment procurement enums.

Thin: names the procured ZATCA connector app and the statutory VAT template. No
custom logic; the connector fills inv_zatca_* on the Sales Invoice, and stock
ERPNext applies the VAT template.
"""

from __future__ import annotations

from frappe.model.document import Document


class LogistayInvoiceSettings(Document):
    pass
