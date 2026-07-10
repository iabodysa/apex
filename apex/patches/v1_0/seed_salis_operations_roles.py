# Copyright (c) 2026, AFMCO and contributors
"""Seed the Salis Operations-side approval-tier roles. Install-safe and idempotent.

Consolidated (v1.x): the generic Operations approval roles this seed used to
create — "Project Manager", "Regional Operations Manager", and
"Operations Manager" — are NO LONGER seeded. They were generic names the app
did not own (Frappe/ERPNext/HRMS do not ship them; ERPNext owns the near-identical
"Projects Manager"), so seeding them created confusing duplicate-looking roles
for a small company. The Salis Delegation-of-Authority ladder now uses the
Fleet-prefixed roles instead:
    Project tier      -> Fleet Project Manager
    Regional/Ops tier -> Fleet Manager
The consolidation is enforced purely by NOT seeding the old generic names (this
module is now a guarded no-op). There is no consolidate_salis_roles patch — the
earlier reference to one was stale; re-pointing any existing user off an old role
name (on a legacy site that still has them) is an owner decision, not automated.

This module is intentionally retained as a guarded no-op so the entry in
patches.txt keeps resolving on already-installed sites; it seeds nothing.
"""

import frappe  # noqa: F401  (kept for parity with the seed module contract)

# [#kctdks]
OPERATIONS_ROLES: list[str] = []


def execute():
    # [#g68487]
    return
