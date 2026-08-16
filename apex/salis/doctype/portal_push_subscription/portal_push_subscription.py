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
        """One endpoint belongs to one subscription, enforced here because the column cannot.

        The field is declared ``unique`` in the DocType JSON, and that declaration is dropped in
        silence: ``endpoint`` is a Small Text, which maps to a MySQL ``text`` column, and Frappe's
        schema builder refuses a unique index on ``text``/``longtext``
        (frappe/database/schema.py:212, :229, :241). ``SHOW INDEX`` on the table returns no row for
        the column, so nothing at the database level ever refused a duplicate and
        ``DuplicateEntryError`` could not fire.

        The type cannot simply become ``Data``: a push endpoint is a service URL well past that
        field's 140-character ceiling. So the guarantee moves to the controller, where the length
        is not a constraint, and the JSON keeps its ``unique`` flag as the DECLARATION of intent
        that this check honours.

        A browser that re-registers its push endpoint would otherwise create a second row instead
        of replacing the first, and every notification would arrive twice.
        """
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
