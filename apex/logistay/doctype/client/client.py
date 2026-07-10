# Copyright (c) 2026, AFMCO and contributors
"""Client controller.

The billing counterparty for the Logistay timesheet flow: Mapping Profiles and
Timesheet Periods are scoped to a Client. Named by ``client_code`` so foreign
Links carry the readable business code. No lifecycle invariant beyond the
unique/immutable code enforced by the schema, so the controller stays a stub.
"""

from __future__ import annotations

from frappe.model.document import Document


class Client(Document):
    pass
