# Copyright (c) 2026, afmcoltd

import frappe
from frappe import _
from frappe.model.document import Document

from apex.apex_core.utils.portal_token_security import DRIVER, WORKER
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
