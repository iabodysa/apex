# Copyright (c) 2026, afmcoltd
"""Import-path bridge for the stock engine's policy, now owned by Habitat Settings.

Apex Stock Settings is folded and deleted (``apex.patches.v2_8.fold_apex_stock_settings``);
this directory carries no DocType JSON any more and ``frappe.get_controller`` never
resolves it to one. ``policy`` and ``validate_posting_allowed`` live in
``apex.apex_core.doctype.habitat_settings.habitat_settings``, which reads the fields
from Habitat Settings; this module re-exports them under their old import path so
``apex.habitat.doctype.accommodation_stock_ledger.accommodation_stock_ledger`` — and
every controller that imports the engine through it — keeps resolving without a
change on that side. Deleting this file breaks that import, and
``frappe.model.sync.remove_orphan_doctypes`` reads any resulting ``ImportError`` as
"this DocType's code is gone" and deletes the DocType record of every controller in
that import chain on the next migrate, though the underlying table and its rows are
left standing. Retire this bridge only together with updating that import.
"""

from apex.apex_core.doctype.habitat_settings.habitat_settings import (
    policy,
    validate_posting_allowed,
)

__all__ = ["policy", "validate_posting_allowed"]
