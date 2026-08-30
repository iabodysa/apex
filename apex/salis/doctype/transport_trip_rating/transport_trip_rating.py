# Copyright (c) 2026, afmcoltd

import frappe
from frappe import _
from frappe.model.document import Document

from apex.salis.utils import worker_was_on_trip


class TransportTripRating(Document):

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        dispatch_trip: DF.Link
        employee: DF.Link
        feedback: DF.SmallText | None
        naming_series: DF.Literal["TTR-.####"]
        rating: DF.Rating
        transport_request: DF.Link | None

    def validate(self):
        self._require_trip_completed()
        self._require_employee_on_trip()

    def _require_trip_completed(self):
        status = frappe.db.get_value("Dispatch Trip", self.dispatch_trip, "status")
        if status != "Completed":
            frappe.throw(_("A trip can only be rated once it is completed."))

    def _require_employee_on_trip(self):
        if not worker_was_on_trip(self.employee, self.dispatch_trip):
            frappe.throw(
                _("You were not part of this trip's manifest."), frappe.PermissionError
            )


def on_doctype_update():
    frappe.db.add_unique(
        "Transport Trip Rating",
        ["employee", "dispatch_trip"],
        constraint_name="unique_ttr_employee_trip",
    )
