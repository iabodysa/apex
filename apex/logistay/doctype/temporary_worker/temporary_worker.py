# Copyright (c) 2026, AFMCO and contributors
"""Temporary Worker controller.

A Temporary Worker is an unregistered worker who has arrived on a passport
only — no Iqama and no Employee record yet. The record exists so the worker can
be housed and issued custody during the gap between arrival and Iqama issuance.

Party-link lifecycle
---------------------
This DocType is the standalone identity foundation for the Dynamic-Link
migration. In later batches the housing and custody DocTypes stop pointing at
``Employee`` directly and instead carry a ``party_type`` / ``party`` Dynamic
Link, so a stay or custody issue can reference EITHER an ``Employee`` OR a
``Temporary Worker``.

Once the Iqama issues and a permanent ``Employee`` record is created, a
scheduled task (built in a later batch) sets ``linked_employee`` and
``linked_on`` here and flips ``status`` to ``Linked``. Records whose window
lapses without a link are flipped to ``Expired`` by the same scheduler. This
controller stays deliberately minimal: it only owns the temporary-window math
and its guardrails. No party fields and no scheduler logic live here yet.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days

# [#di1y0q]
DEFAULT_WINDOW_DAYS = 30
# [#huqfyq]
MAX_WINDOW_DAYS = 90


class TemporaryWorker(Document):
    def validate(self) -> None:
        self._validate_window_days()
        self._compute_expiry_date()

    def _validate_window_days(self) -> None:
        if not self.window_days:
            self.window_days = DEFAULT_WINDOW_DAYS
        if self.window_days < 1:
            frappe.throw(_("Window Days must be at least 1 day."))
        if self.window_days > MAX_WINDOW_DAYS:
            frappe.throw(
                _("Window Days cannot exceed {0} days.").format(MAX_WINDOW_DAYS)
            )

    def _compute_expiry_date(self) -> None:
        if self.arrival_date:
            self.expiry_date = add_days(self.arrival_date, self.window_days)
