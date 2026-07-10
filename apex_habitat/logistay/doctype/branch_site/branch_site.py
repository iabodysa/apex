# Copyright (c) 2026, AFMCO and contributors
"""Branch Site controller.

A Client's operating location. Scopes a Mapping Profile / Timesheet Period below
the Client level. Site codes are only unique within their Client, so the record
is named by an opaque series and the (Client, Site Code) pair is not schema-
enforced unique here; the ingestion layer resolves the pair explicitly. Stub
controller until a real per-Client uniqueness invariant is required.
"""

from __future__ import annotations

from frappe.model.document import Document


class BranchSite(Document):
    pass
