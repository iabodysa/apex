# Copyright (c) 2026, afmcoltd
"""tasks package.

Split into per-domain submodules. This __init__ re-exports every job and
helper so the historical ``apex.habitat.tasks.<name>`` import path and every
scheduler dotted path keep resolving unchanged.
"""

from __future__ import annotations

from apex.habitat.tasks.common import (
    _notify_operational,
    _notify_role_system,
    _notify_user_system,
)
from apex.habitat.tasks.safety import (
    _instance_priority,
    audit_remediation_deadline_watch,
    daily_safety_task_compliance_scan,
    weekly_safety_coverage_gate,
)
from apex.habitat.tasks.custody import (
    consumable_custody_expiry_watch,
    weekly_custody_digest,
)
from apex.habitat.tasks.cost import (
    allocate_building_accommodation_cost,
    backdate_assignment_cost,
    daily_accommodation_cost_allocation,
)
from apex.habitat.tasks.maintenance import (
    daily_building_license_expiry_check,
    open_maintenance_escalation,
)
from apex.habitat.tasks.residency import (
    idle_resident_aging,
    lease_expiry_watchlist,
)
from apex.habitat.tasks.occupancy import (
    daily_occupancy_snapshot,
    weekly_occupancy_sync,
)
from apex.habitat.tasks.cleaning import (
    daily_cleaning_log_generator,
)
from apex.habitat.tasks.scheduled_tasks import (
    daily_scheduled_task_instance_generator,
)

__all__ = [
    "_instance_priority",
    "_notify_operational",
    "_notify_role_system",
    "_notify_user_system",
    "allocate_building_accommodation_cost",
    "audit_remediation_deadline_watch",
    "backdate_assignment_cost",
    "consumable_custody_expiry_watch",
    "daily_accommodation_cost_allocation",
    "daily_building_license_expiry_check",
    "daily_cleaning_log_generator",
    "daily_occupancy_snapshot",
    "daily_safety_task_compliance_scan",
    "daily_scheduled_task_instance_generator",
    "idle_resident_aging",
    "lease_expiry_watchlist",
    "open_maintenance_escalation",
    "weekly_custody_digest",
    "weekly_occupancy_sync",
    "weekly_safety_coverage_gate",
]
