# Copyright (c) 2026, afmcoltd
"""Subcontractor Service Contract controller.

Why Finance Manager holds a permlevel-1 row here and NO permlevel-0 row.
It is a deliberate field overlay, not an omission: the role may read and set the
commercial terms (``rate_per_visit``, ``monthly_retainer``) on a contract that
Accommodation Manager opens, and may not open, create, submit or cancel it. Document
access is resolved from permlevel-0 rows only, field access is resolved separately and
unions every permlevel across the user's roles, so the two are independent grants --
the row activates the moment one user holds both roles, with no DocPerm edit. No
shipped role profile bundles them today, so this overlay is dormant until an
administrator does. Proof and the framework citations are in
``apex/habitat/doctype/custody_damage_assessment/test_finance_manager_field_overlay.py``.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate


class SubcontractorServiceContract(Document):
    def validate(self):
        """Blocks saving when the Contract End date falls before the Contract Start date."""
        if self.contract_start_date and self.contract_end_date:
            if getdate(self.contract_end_date) < getdate(self.contract_start_date):
                frappe.throw(_("Contract End cannot be before Contract Start."))
