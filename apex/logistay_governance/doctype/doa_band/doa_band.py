# Copyright (c) 2026, AFMCO and contributors
"""DoA Band controller.

An amount-band -> approver-role map for one governed action, effective-dated. The
band bounds carry NO real value in the repo; they are seeded out-of-repo. The
controller only guards schema integrity (a coherent amount band and effective
window); the fail-closed authority resolution itself lives in the shared
``enforce_gate`` service so 190/191/192 all resolve authority identically.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate


class DoABand(Document):
    def validate(self) -> None:
        self._validate_amount_bounds()
        self._validate_effective_window()

    def _validate_amount_bounds(self) -> None:
        # A blank upper bound is the legitimate open-ended top band; only compare
        # when both bounds are present.
        if self.gov_amount_to and flt(self.gov_amount_from) > flt(self.gov_amount_to):
            frappe.throw(_("Amount From cannot exceed Amount To."))

    def _validate_effective_window(self) -> None:
        if (
            self.gov_effective_from
            and self.gov_effective_to
            and getdate(self.gov_effective_from) > getdate(self.gov_effective_to)
        ):
            frappe.throw(_("Effective From cannot be after Effective To."))
