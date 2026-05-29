"""Salis Authority Tier (child table).

A configurable tier -> Role mapping row stored on Salis Settings. Lets the
Delegation-of-Authority ladder be extended as data instead of being hardcoded
in ``salis_lib.ROLE_TIER``. Roles stay native Frappe Role records; this row only
associates an existing Role with a DoA tier name.
"""

from __future__ import annotations

from frappe.model.document import Document


class SalisAuthorityTier(Document):
    pass
