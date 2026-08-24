# Copyright (c) 2026, afmcoltd
from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, now_datetime

from apex.salis.tasks.dispatch import generate_for_assignment


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
        generate_for_assignment(self.name)

    def on_cancel(self):
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
