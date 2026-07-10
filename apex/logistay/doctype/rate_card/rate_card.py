# Copyright (c) 2026, AFMCO and contributors
"""Rate Card controller.

Effective-dated, never-mutate, versioned price book. The three invariants the
controller actually enforces (so this is not merely a status Select):

* WINDOW        - effective_from cannot fall after effective_to.
* DIVISOR-PRESENT (C3) - when the card bills in package_day / attendance_day
  units, every day-rate line MUST name its own day-rate basis. There is no flat
  divisor default; the basis is a per-line decision carried on the child row.
* NEVER-MUTATE  - once a card is ``active`` (or ``superseded``) it is immutable.
  The ONLY write permitted is the single ``active -> superseded`` transition, and
  even that may not smuggle any other field change. A revision is a NEW version
  (a new record with a bumped ``rc_version``), never an in-place edit.

Money values (day rate, levy, charge fee, penalty amounts) live on the child
rows and are seeded out-of-repo; none is defaulted here.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate

# Card states whose rows/fields may still be edited in place.
_EDITABLE_STATES = ("draft", "pending_approval")
# Billing units that require a per-line day-rate basis (no flat divisor).
_DIVISOR_UNITS = ("package_day", "attendance_day")
# Layout fieldtypes carry no data and are ignored when diffing.
_LAYOUT_TYPES = ("Section Break", "Column Break", "HTML", "Heading")


class RateCard(Document):
    def validate(self) -> None:
        self._validate_window()
        self._validate_divisor_present()
        self._guard_never_mutate()

    def _validate_window(self) -> None:
        if (
            self.rc_effective_from
            and self.rc_effective_to
            and getdate(self.rc_effective_from) > getdate(self.rc_effective_to)
        ):
            frappe.throw(_("Effective From cannot be after Effective To."))

    def _validate_divisor_present(self) -> None:
        # C3: the flat divisor default is retired; each day-rate line names its basis.
        if self.rc_billing_unit not in _DIVISOR_UNITS:
            return
        for row in self.rc_components or []:
            if row.rc_component == "day_rate" and not row.rc_day_rate_basis:
                frappe.throw(
                    _(
                        "Rate line {0}: Day Rate Basis is required for a day-rate line "
                        "on a package-day / attendance-day card (no default divisor)."
                    ).format(row.idx)
                )

    def _guard_never_mutate(self) -> None:
        if self.is_new():
            return
        stored = frappe.get_doc("Rate Card", self.name)  # DB copy, not yet overwritten
        if stored.rc_status in _EDITABLE_STATES:
            return
        # Card is active or superseded: the sole legal write is active -> superseded.
        transitioning = stored.rc_status == "active" and self.rc_status == "superseded"
        if not transitioning:
            frappe.throw(
                _(
                    "Rate Card {0} is {1} and cannot be edited. Create a new version "
                    "instead of changing an active card."
                ).format(self.name, stored.rc_status)
            )
        if self._differs_beyond_status(stored):
            frappe.throw(
                _(
                    "Superseding a Rate Card may only change its status; edit anything "
                    "else by creating a new version."
                )
            )

    def _differs_beyond_status(self, stored: "RateCard") -> bool:
        for df in self.meta.fields:
            if df.fieldname == "rc_status" or df.fieldtype in _LAYOUT_TYPES:
                continue
            if df.fieldtype in ("Table", "Table MultiSelect"):
                if self._child_signature(self.get(df.fieldname)) != self._child_signature(
                    stored.get(df.fieldname)
                ):
                    return True
                continue
            if (self.get(df.fieldname) or None) != (stored.get(df.fieldname) or None):
                return True
        return False

    @staticmethod
    def _child_signature(rows) -> list:
        return [
            {k: v for k, v in (r.as_dict() if hasattr(r, "as_dict") else r).items()
             if k not in ("modified", "creation", "idx", "name", "parent")}
            for r in (rows or [])
        ]
