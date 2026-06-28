# Copyright (c) 2026, AFMCO and contributors
"""Apex Settings controller.

App-wide configuration shared by every Apex module (Habitat and Salis). Holds
settings that are not scoped to a single domain, such as the finance integration
defaults (``default_payment_method``, ``enable_gl_posting``) that govern how the
app generates payment documents and whether it posts to the General Ledger.
"""

from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe.utils import cint


class ApexSettings(Document):
    pass


def gl_posting_enabled() -> bool:
    """Single source of truth for the ``enable_gl_posting`` finance gate.

    Read via ``frappe.db.get_single_value`` (no full-doc load) so every caller -
    the Payment Router, the housing ledger, a report - reads the flag the same
    way. When this is falsy (the factory default), financial side effects stay
    OFF: the housing ledger keeps writing operational memos and the Payment
    Router routes the payment record without driving a GL-posting submit.
    """
    return bool(cint(frappe.db.get_single_value("Apex Settings", "enable_gl_posting")))
