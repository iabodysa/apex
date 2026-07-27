# Copyright (c) 2026, AFMCO and contributors
"""Scheduled tasks for the Salis fleet module (split by domain)."""

from __future__ import annotations

import frappe

from apex.salis.tasks.common import (
    BATCH_SIZE,
    _raise_alert,
    _settings_int,
)

# Constant name, re-issued each iteration: MariaDB replaces a same-named savepoint
# rather than stacking one per row. Distinct from _raise_alert's own name.
_ROW_SAVEPOINT = "salis_driver_row"


def driver_license_expiry_watch() -> None:
    """Warn when an active driver's licence is at or past its expiry window.

    Reads Salis Driver ``{status: Active, license_expiry: set}`` paginated. If
    the licence has expired (``days < 0``) raises a Critical "License Expiry"
    alert; if it expires within ``alert_lead_days`` raises a Warning.
    """
    from frappe.utils import date_diff, today

    today_str = today()
    logger = frappe.logger()
    # [#5iz5cq]
    LICENSE_MIN_LEAD_DAYS = 30
    license_lead = _settings_int("license_alert_lead_days", LICENSE_MIN_LEAD_DAYS)
    lead_days = max(license_lead, _settings_int("alert_lead_days", 7), LICENSE_MIN_LEAD_DAYS)

    start = 0
    while True:
        drivers = frappe.get_all(
            "Salis Driver",
            filters={"status": "Active", "license_expiry": ["is", "set"]},
            fields=["name", "license_expiry"],
            limit_start=start,
            limit_page_length=BATCH_SIZE,
        )
        if not drivers:
            break

        for d in drivers:
            frappe.db.savepoint(_ROW_SAVEPOINT)
            try:
                days = date_diff(d.license_expiry, today_str)
                # [#bces73]
                who = d.name
                if days < 0:
                    msg = (f"driver_license_expiry_watch: driver {who} licence expired "
                           f"{abs(days)} days ago ({d.license_expiry}).")
                    logger.warning(msg)
                    _raise_alert("License Expiry", "Critical", msg,
                                 "Salis Driver", d.name, driver=d.name)
                elif days <= lead_days:
                    msg = (f"driver_license_expiry_watch: driver {who} licence expires in "
                           f"{days} days ({d.license_expiry}).")
                    logger.warning(msg)
                    _raise_alert("License Expiry", "Warning", msg,
                                 "Salis Driver", d.name, driver=d.name)
            except Exception:
                frappe.db.rollback(save_point=_ROW_SAVEPOINT)
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Driver licence watch failed for {d.name}"[:140],
                )

        start += BATCH_SIZE
