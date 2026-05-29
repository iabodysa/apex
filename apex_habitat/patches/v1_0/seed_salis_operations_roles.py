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
Existing users on the old names are migrated by
patches/v1_x/consolidate_salis_roles.py.

This module is intentionally retained as a guarded no-op so the entry in
patches.txt keeps resolving on already-installed sites; it seeds nothing.
"""

import frappe  # noqa: F401  (kept for parity with the seed module contract)

# Intentionally empty: these generic role names are no longer owned/seeded.
OPERATIONS_ROLES: list[str] = []


def execute():
    # No-op by design — see module docstring. Left as a function so the
    # patches.txt entry and after_install wiring continue to resolve.
    return
