# Copyright (c) 2026, AFMCO and contributors
"""tasks package.

Split into per-domain submodules. This __init__ re-exports every job and
helper so the historical ``apex_habitat.habitat.tasks.<name>`` import path and every
scheduler dotted path keep resolving unchanged.
"""

from __future__ import annotations

from apex_habitat.habitat.tasks.common import (
    _notify_operational,
    _notify_role_system,
    _notify_user_system,
)
from apex_habitat.habitat.tasks.safety import (
    _instance_priority,
    _raise_safety_alert,
    audit_remediation_deadline_watch,
    daily_safety_task_compliance_scan,
    weekly_safety_coverage_gate,
)
from apex_habitat.habitat.tasks.custody import (
    _raise_consumable_alert,
    consumable_custody_expiry_watch,
    weekly_custody_digest,
)
from apex_habitat.habitat.tasks.cost import (
    allocate_building_accommodation_cost,
    backdate_assignment_cost,
    daily_accommodation_cost_allocation,
)
from apex_habitat.habitat.tasks.maintenance import (
    _raise_maintenance_alert,
    daily_building_license_expiry_check,
    open_maintenance_escalation,
)
from apex_habitat.habitat.tasks.residency import (
    idle_resident_aging,
    lease_expiry_watchlist,
    temporary_stay_checkout_watchlist,
)
from apex_habitat.habitat.tasks.occupancy import (
    daily_occupancy_snapshot,
    weekly_occupancy_sync,
)
from apex_habitat.habitat.tasks.cleaning import (
    auto_create_cleaning_logs,
    daily_cleaning_log_generator,
)
from apex_habitat.habitat.tasks.scheduled_tasks import (
    daily_scheduled_task_instance_generator,
)

__all__ = [
    "_instance_priority",
    "_notify_operational",
    "_notify_role_system",
    "_notify_user_system",
    "_raise_consumable_alert",
    "_raise_maintenance_alert",
    "_raise_safety_alert",
    "allocate_building_accommodation_cost",
    "audit_remediation_deadline_watch",
    "auto_create_cleaning_logs",
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
    "temporary_stay_checkout_watchlist",
    "weekly_custody_digest",
    "weekly_occupancy_sync",
    "weekly_safety_coverage_gate",
]
