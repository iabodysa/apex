# Copyright (c) 2026, afmcoltd
from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class RouteTemplate(Document):
    def validate(self):
        if not self.stops:
            frappe.throw(_("Add at least one route stop."))

        keys = set()
        for index, stop in enumerate(self.stops, start=1):
            if not (stop.stop_name or "").strip():
                frappe.throw(_("Row {0}: Stop Name is required.").format(index))
            if not stop.get("stop_key"):
                stop.set("stop_key", f"stop-{index}")
            if stop.get("stop_key") in keys:
                frappe.throw(_("Route stop keys must be unique."))
            keys.add(stop.get("stop_key"))
