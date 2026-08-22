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
administrator does. The framework's rule, written here rather than pointed at: permlevel access is the UNION
of the caller's roles (frappe/permissions.py get_role_permissions), so a user holding both
roles reads the union of both field sets and no DocPerm edit is needed to widen him.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate

from apex.apex_core.utils.vat import apply_vat


class SubcontractorServiceContract(Document):
    def validate(self):
        """Blocks saving when the Contract End date falls before the Contract Start date."""
        if self.contract_start_date and self.contract_end_date:
            if getdate(self.contract_end_date) < getdate(self.contract_start_date):
                frappe.throw(_("Contract End cannot be before Contract Start."))

        if not self.company:
            from apex.apex_core.doctype.habitat_settings.habitat_settings import get_default_company
            self.company = get_default_company()

        apply_vat(self, flt(self.monthly_retainer) or flt(self.rate_per_visit))
