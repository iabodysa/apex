# Copyright (c) 2026, afmcoltd

import frappe
from frappe import _
from frappe.model.document import Document

from apex.apex_core.utils.portal_identity import DRIVER, WORKER
from apex.salis.api.web_push import is_allowed_push_endpoint


class PortalPushSubscription(Document):
    def validate(self):
        if self.holder_type == WORKER:
            if not self.employee or self.driver:
                frappe.throw(_("Worker notification devices require one employee."))
        elif self.holder_type == DRIVER:
            if not self.driver or self.employee:
                frappe.throw(_("Driver notification devices require one driver."))
        else:
            frappe.throw(_("Notification holder type must be Worker or Driver."))

        if not is_allowed_push_endpoint(self.endpoint):
            frappe.throw(_("The notification endpoint is not an approved push service."))
        if not self.p256dh or not self.auth:
            frappe.throw(_("Notification subscription keys are required."))
        self._refuse_a_second_row_for_one_endpoint()

    def _refuse_a_second_row_for_one_endpoint(self):
        twin = frappe.db.get_value(
            "Portal Push Subscription",
            {"endpoint": self.endpoint, "name": ["!=", self.name or ""]},
            "name",
        )
        if twin:
            frappe.throw(
                _("This notification endpoint is already registered as {0}.").format(twin),
                frappe.DuplicateEntryError,
            )
