# Copyright (c) 2026, AFMCO and contributors
"""Building License controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, getdate, today


class BuildingLicense(Document):
    def validate(self) -> None:
        self._validate_dates()
        self._stamp_renewal_date()

    def _validate_dates(self) -> None:
        # Expiry must fall after issue; a backwards range is a data-entry error.
        if self.issue_date and self.expiry_date and getdate(self.expiry_date) <= getdate(self.issue_date):
            frappe.throw(_("Expiry Date must be after the Issue Date."))

    def _stamp_renewal_date(self) -> None:
        """Stamp ``last_renewal_date`` whenever the license is renewed.

        A renewal is recorded when the validity (``expiry_date``) is pushed
        forward versus the previously-recorded value — the operator has
        extended the license. Two real renewal paths are covered:

        * editing a still-draft license and pushing ``expiry_date`` forward; and
        * amending a submitted license (cancel -> amend) with a later expiry,
          where the prior value is read from the ``amended_from`` original.

        ``last_renewal_date`` is read-only in the form, so it is only ever
        written here (or by the ``renew`` action below), never by a human.
        """
        if not self.expiry_date:
            return

        if self.is_new():
            # [#nkhxjc]
            amended_from = getattr(self, "amended_from", None)
            previous_expiry = (
                frappe.db.get_value("Building License", amended_from, "expiry_date")
                if amended_from
                else None
            )
        else:
            previous_expiry = frappe.db.get_value("Building License", self.name, "expiry_date")

        if previous_expiry and getdate(self.expiry_date) > getdate(previous_expiry):
            self.last_renewal_date = today()


@frappe.whitelist(methods=["POST"])
def renew(name: str, new_expiry_date: str | None = None, extend_days: int | None = None) -> dict:
    """Renew a Building License: roll ``expiry_date`` forward, stamp
    ``last_renewal_date`` = today, and reset ``status`` to ``Active``.

    Pass either an explicit ``new_expiry_date`` or ``extend_days`` (number of
    days to add to the current expiry). Used by the "Renew License" form button
    on a draft license; a submitted license is renewed by amending it (the
    controller stamps ``last_renewal_date`` from the amended expiry).
    """
    frappe.has_permission("Building License", "write", doc=name, throw=True)
    doc = frappe.get_doc("Building License", name)

    if doc.docstatus == 1:
        frappe.throw(
            _("This license is submitted. Amend it (Cancel, then Amend) with the new expiry date to renew.")
        )

    if new_expiry_date:
        new_expiry = getdate(new_expiry_date)
    elif extend_days:
        base = getdate(doc.expiry_date) if doc.expiry_date else getdate(today())
        new_expiry = getdate(add_days(base, int(extend_days)))
    else:
        frappe.throw(_("Provide either a new expiry date or the number of days to extend."))

    if doc.expiry_date and new_expiry <= getdate(doc.expiry_date):
        frappe.throw(_("The new expiry date must be later than the current expiry date."))

    doc.expiry_date = new_expiry
    doc.last_renewal_date = today()
    doc.status = "Active"
    doc.save()
    # No explicit commit: the request transaction commits on a successful response,
    # so an early commit here would defeat rollback if a later step in the request fails.
    return {"name": doc.name, "expiry_date": str(new_expiry), "last_renewal_date": doc.last_renewal_date}
