# Copyright (c) 2026, afmcoltd
"""Apex Integration Settings controller.

Single DocType that documents and surfaces how an external frontend integrates
with this Frappe backend over HTTP. The real linking always uses native Frappe
tools (User API Access tokens, OAuth Client, Webhook); this DocType holds only
app-specific coordination config, with the starter guidance in its own intro field.
There is no business logic and no custom authentication here by design.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class ApexIntegrationSettings(Document):
    def validate(self):
        """Validates that a non-blank Frontend Base URL starts with http:// or https://."""
        self._validate_frontend_base_url()

    def _validate_frontend_base_url(self):
        """Ensure the frontend base URL looks like an http(s) URL when set."""
        url = (self.frontend_base_url or "").strip()
        if not url:
            return
        if not (url.startswith("http://") or url.startswith("https://")):
            frappe.throw(
                _("Frontend Base URL must start with http:// or https:// (for example https://salis-fleet.com).")
            )
