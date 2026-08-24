# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, date_diff, getdate, today

_TRANSITION_SAVEPOINT = "building_license_transition"


def derive_license_status(
    expiry_date: str,
    renewal_lead_days: int | None,
    on_date: str | None = None,
) -> str:
    days_to_expiry = date_diff(expiry_date, on_date or today())
    if days_to_expiry <= 0:
        return "Expired"
    lead_days = max(int(renewal_lead_days or 0), 0)
    if days_to_expiry <= lead_days:
        return "Expiring Soon"
    return "Active"


class BuildingLicense(Document):
    def validate(self) -> None:
        self._validate_dates()
        self._stamp_renewal_date()
        self._sync_status()

    def _sync_status(self) -> None:
        previous = None if self.is_new() else self.get_doc_before_save()
        if previous and previous.status == "Revoked":
            self.status = "Revoked"
            return
        if self.expiry_date:
            self.status = derive_license_status(
                self.expiry_date,
                self.renewal_lead_days,
            )

    def _validate_dates(self) -> None:
        if self.issue_date and self.expiry_date and getdate(self.expiry_date) <= getdate(self.issue_date):
            frappe.throw(_("Expiry Date must be after the Issue Date."))

    def before_cancel(self) -> None:
        if self.status == "Revoked":
            frappe.throw(_("A revoked Building License cannot be cancelled or reinstated."))

    def _stamp_renewal_date(self) -> None:
        if not self.expiry_date:
            return

        if self.is_new():
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
    frappe.has_permission("Building License", "write", doc=name, throw=True)
    doc = frappe.get_doc("Building License", name)

    if doc.status == "Revoked":
        frappe.throw(_("A revoked Building License cannot be renewed."))
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
    doc.status = derive_license_status(
        new_expiry,
        doc.renewal_lead_days,
    )
    doc.save()
    return {"name": doc.name, "expiry_date": str(new_expiry), "last_renewal_date": doc.last_renewal_date}


@frappe.whitelist(methods=["POST"])
def mark_revoked(name: str, reason: str) -> dict:
    reason = str(reason or "").strip()
    if not reason:
        frappe.throw(_("A reason is required to revoke a Building License."))

    doc = frappe.get_doc("Building License", name, for_update=True)
    doc.check_permission("write")
    if doc.docstatus != 1:
        frappe.throw(_("Only submitted Building Licenses can be revoked."))
    if doc.status == "Revoked":
        frappe.throw(_("This Building License is already revoked."))

    frappe.db.savepoint(_TRANSITION_SAVEPOINT)
    try:
        doc.db_set("status", "Revoked")
        doc.add_comment(
            "Comment",
            _("Building License revoked: {0}").format(reason),
        )
    except Exception:
        frappe.db.rollback(save_point=_TRANSITION_SAVEPOINT)
        raise
    return {"name": doc.name, "status": "Revoked"}
