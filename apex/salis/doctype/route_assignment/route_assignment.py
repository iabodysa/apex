# Copyright (c) 2026, afmcoltd
from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, now_datetime


class RouteAssignment(Document):
    def validate(self):
        self._set_assignment_name()
        if self.get("ends_on") and getdate(self.ends_on) < getdate(self.starts_on):
            frappe.throw(_("Ends On cannot be earlier than Starts On."))

    def before_submit(self):
        missing = [
            label
            for fieldname, label in (
                ("route_template", _("Route Template")),
                ("work_shift", _("Work Shift")),
                ("project", _("Project")),
                ("driver", _("Default Driver")),
                ("vehicle", _("Default Vehicle")),
                ("route_supervisor", _("Route Supervisor")),
                ("starts_on", _("Starts On")),
            )
            if not self.get(fieldname)
        ]
        if missing:
            frappe.throw(
                _("Complete these fields before approval: {0}.").format(
                    ", ".join(missing)
                )
            )
        if self.status != "Approved":
            frappe.throw(
                _("Use the Approve workflow action to approve this assignment.")
            )
        self.approved_by = frappe.session.user
        self.approved_on = now_datetime()

    def on_submit(self):
        from apex.salis.tasks.dispatch import generate_for_assignment

        generate_for_assignment(self.name)

    def on_cancel(self):
        """Withdraw what ``on_submit`` created: the unrun trips and the watermark.

        ``generate_for_assignment`` writes up to fourteen days of Dispatch Trips ahead
        AND stamps ``generated_through`` so the daily job does not re-cover those days.
        Without a reversal the trips outlive the assignment that justified them and the
        dispatch board keeps offering a shift nobody approved any more.

        Only a DRAFT trip still at Planned is withdrawn. Once a trip is submitted it has
        been dispatched or completed, and cancelling a recurrence must not rewrite an
        operational record. Deleting rather than cancelling the draft is deliberate:
        ``DispatchTrip.on_trash`` releases the Transport Requests the draft had claimed,
        which nothing else can free.

        No permission bypass: the shipped workflow restricts the Cancel transition to
        Fleet Manager, and Fleet Manager is the role that holds ``delete`` on Dispatch
        Trip, so the acting user's own rights carry the delete.

        The watermark is cleared last so an amendment — which copies ``generated_through``
        forward — starts from ``starts_on`` again instead of skipping the days just
        deleted and leaving them uncovered forever.
        """
        for trip in frappe.get_all(
            "Dispatch Trip",
            filters={
                "route_assignment": self.name,
                "docstatus": 0,
                "status": "Planned",
            },
            pluck="name",
        ):
            frappe.delete_doc("Dispatch Trip", trip)

        self.db_set("generated_through", None)

    def _set_assignment_name(self):
        labels = (
            self._label("Route Template", self.route_template, "template_name"),
            self._label("Work Shift", self.work_shift, "shift_name"),
            self._label("Project", self.project, "project_name"),
        )
        self.assignment_name = " · ".join(label for label in labels if label)

    @staticmethod
    def _label(doctype, name, fieldname):
        if not name:
            return None
        return frappe.db.get_value(doctype, name, fieldname) or name
