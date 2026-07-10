# Copyright (c) 2026, AFMCO and contributors
"""tasks package.

Split into per-domain submodules. This __init__ re-exports every job and
helper so the historical ``apex_habitat.salis.tasks.<name>`` import path and every
scheduler dotted path keep resolving unchanged.
"""

from __future__ import annotations

from apex_habitat.salis.tasks.common import (
    ALERT_DOCTYPE,
    BATCH_SIZE,
    _publish_operations_alert,
    _raise_alert,
    _resolve_alert,
    _resolve_project_supervisor,
    _settings_int,
    _vehicle_project,
)
from apex_habitat.salis.tasks.driver import (
    driver_license_expiry_watch,
)
from apex_habitat.salis.tasks.vehicle import (
    idle_vehicle_watch,
    vehicle_compliance_expiry_watch,
    vehicle_utilization_summary,
)
from apex_habitat.salis.tasks.fuel import (
    overdue_fuel_request_watch,
    resolve_excessive_topup_alerts,
    unreverted_topup_watch,
)
from apex_habitat.salis.tasks.attendance import (
    missing_attendance_watch,
)
from apex_habitat.salis.tasks.alerts import (
    daily_open_alerts_digest,
    reconcile_operations_alerts,
)
from apex_habitat.salis.tasks.workshop import (
    _overstay_stops,
    get_workshop_overstay_count,
    workshop_overstay_watch,
)

__all__ = [
    "ALERT_DOCTYPE",
    "BATCH_SIZE",
    "_overstay_stops",
    "_publish_operations_alert",
    "_raise_alert",
    "_resolve_alert",
    "_resolve_project_supervisor",
    "_settings_int",
    "_vehicle_project",
    "daily_open_alerts_digest",
    "driver_license_expiry_watch",
    "get_workshop_overstay_count",
    "idle_vehicle_watch",
    "missing_attendance_watch",
    "overdue_fuel_request_watch",
    "reconcile_operations_alerts",
    "resolve_excessive_topup_alerts",
    "unreverted_topup_watch",
    "vehicle_compliance_expiry_watch",
    "vehicle_utilization_summary",
    "workshop_overstay_watch",
]
