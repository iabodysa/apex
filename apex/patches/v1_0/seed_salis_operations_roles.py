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

UNREGISTERED-PATCH: execute() is an unconditional `return`, so registering this
    module in patches.txt would run a guaranteed no-op and write an empty Patch
    Log row — running it and not running it are indistinguishable. It was
    de-registered on 2026-07-25; only the patches.txt entry was dropped.
COVERED-BY: ``apex/salis/setup.py`` imports this module and calls execute() in
    the after_install Salis seed chain, and ``apex/tests/test_release_hygiene.py``
    reads this file BY PATH for OPERATIONS_ROLES. Both references are why the
    module must stay on disk even though registering it is pointless.
"""

import frappe  # noqa: F401  (kept for parity with the seed module contract)

# [#kctdks]
OPERATIONS_ROLES: list[str] = []


def execute():
    # [#g68487]
    return
