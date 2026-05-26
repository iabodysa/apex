"""Scheduled tasks for the Salis fleet-management module.

Mirrors the Habitat ``tasks.py`` operating shape:
- a shared notifier (``_raise_alert``) that is idempotent and never aborts a job,
- paginated ORM reads (500/batch) via ``frappe.get_all`` with filters,
- per-row ``try/except`` with ``frappe.db.rollback()`` *before* ``frappe.log_error``
  (avoids "current transaction is aborted" cascades),
- ``frappe.logger().warning`` for operational signal,
- every public job wrapped so one failure logs and the next job still runs.

Salis difference vs Habitat: Salis owns a real ``Operations Alert`` DocType, so
``_raise_alert`` both (a) inserts an Operations Alert record and (b) drops a
timeline Comment on the source document.
"""

from __future__ import annotations

import json

import frappe

BATCH_SIZE = 500

#: DocType that backs operational alerts (module Salis, NOT submittable).
ALERT_DOCTYPE = "Operations Alert"


def _settings_int(fieldname: str, default: int) -> int:
    """Read an Int from the Salis Settings single, falling back to ``default``."""
    try:
        value = frappe.db.get_single_value("Salis Settings", fieldname)
    except Exception:
        return default
    if value in (None, ""):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _raise_alert(
    alert_type: str,
    severity: str,
    message: str,
    source_doctype: str | None = None,
    source_name: str | None = None,
    vehicle: str | None = None,
    driver: str | None = None,
) -> str | None:
    """Insert an Operations Alert and post a timeline comment on the source doc.

    Idempotent: skips if an Open alert of the same ``alert_type`` for the same
    vehicle/driver already exists today (idempotency key =
    ``(alert_type, vehicle or driver, date(raised_on))``). This prevents the
    daily jobs from spamming duplicate alerts on every run.

    Both the insert and the timeline comment are wrapped so a notify failure
    rolls back and logs but never aborts the calling job.

    Returns the new alert name, or ``None`` if a duplicate was skipped or the
    insert failed.
    """
    from frappe.utils import now_datetime, today

    # --- Idempotency guard: one Open alert per (type, subject, day) -----------
    dedupe_filters = {
        "alert_type": alert_type,
        "status": "Open",
        "raised_on": ["between", [f"{today()} 00:00:00", f"{today()} 23:59:59"]],
    }
    if vehicle:
        dedupe_filters["vehicle"] = vehicle
    elif driver:
        dedupe_filters["driver"] = driver

    try:
        if frappe.db.exists(ALERT_DOCTYPE, dedupe_filters):
            return None
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            message=frappe.get_traceback(),
            title=f"Salis alert dedupe check failed ({alert_type})"[:140],
        )
        return None

    # --- Insert the alert record ---------------------------------------------
    alert_name = None
    try:
        alert = frappe.get_doc(
            {
                "doctype": ALERT_DOCTYPE,
                "alert_type": alert_type,
                "severity": severity,
                "status": "Open",
                "raised_on": now_datetime(),
                "vehicle": vehicle,
                "driver": driver,
                "message": message[:2000],
            }
        )
        alert.insert(ignore_permissions=True)  # audit-ok
        alert_name = alert.name
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            message=frappe.get_traceback(),
            title=f"Salis alert insert failed ({alert_type})"[:140],
        )
        return None

    # --- Drop a timeline comment on the source doc (best-effort) -------------
    if source_doctype and source_name:
        try:
            frappe.get_doc(source_doctype, source_name).add_comment("Comment", message)
        except Exception:
            frappe.db.rollback()
            frappe.log_error(
                message=frappe.get_traceback(),
                title=f"Salis alert comment failed for {source_name}"[:140],
            )

    return alert_name


# ---------------------------------------------------------------------------
# Daily jobs
# ---------------------------------------------------------------------------


def driver_license_expiry_watch() -> None:
    """Warn when an active driver's licence is at or past its expiry window.

    Reads Salis Driver ``{status: Active, license_expiry: set}`` paginated. If
    the licence has expired (``days < 0``) raises a Critical "License Expiry"
    alert; if it expires within ``alert_lead_days`` raises a Warning.
    """
    from frappe.utils import date_diff, today

    today_str = today()
    logger = frappe.logger()
    lead_days = _settings_int("alert_lead_days", 7)

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
            try:
                days = date_diff(d.license_expiry, today_str)
                # Reference the driver by docname only — never embed PII
                # (full_name / national_id / phone) in alert text.
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
                frappe.db.rollback()
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Driver licence watch failed for {d.name}"[:140],
                )

        start += BATCH_SIZE


def idle_vehicle_watch() -> None:
    """Flag Active vehicles with no dispatch trip in the last ``idle_vehicle_days``.

    For each Salis Vehicle ``{status: Active}`` finds the latest submitted
    Dispatch Trip (status Dispatched/Completed). If the most recent trip is
    older than ``idle_vehicle_days`` (Salis Settings; default 7) — or there is
    no trip at all — raises an Info "Idle Vehicle" alert.
    """
    from frappe.utils import add_days, today

    today_str = today()
    logger = frappe.logger()
    idle_days = _settings_int("idle_vehicle_days", 7)
    cutoff = add_days(today_str, -idle_days)

    start = 0
    while True:
        vehicles = frappe.get_all(
            "Salis Vehicle",
            filters={"status": "Active"},
            fields=["name", "plate_number"],
            limit_start=start,
            limit_page_length=BATCH_SIZE,
        )
        if not vehicles:
            break

        for v in vehicles:
            try:
                recent = frappe.get_all(
                    "Dispatch Trip",
                    filters={
                        "vehicle": v.name,
                        "docstatus": 1,
                        "status": ["in", ["Dispatched", "Completed"]],
                        "trip_date": [">=", cutoff],
                    },
                    fields=["name"],
                    limit_page_length=1,
                )
                if recent:
                    continue
                plate = v.plate_number or v.name
                msg = (f"idle_vehicle_watch: vehicle {plate} has had no dispatch "
                       f"trip in the last {idle_days} days.")
                logger.warning(msg)
                _raise_alert("Idle Vehicle", "Info", msg,
                             "Salis Vehicle", v.name, vehicle=v.name)
            except Exception:
                frappe.db.rollback()
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Idle vehicle watch failed for {v.name}"[:140],
                )

        start += BATCH_SIZE


def unreverted_topup_watch() -> None:
    """Auto-revert temporary fuel top-ups that are past their revert-due date,
    then raise an alert for each (G42).

    Reads Fuel Topup Request ``{is_temporary: 1, reverted: 0,
    status in [Approved, Done], revert_due_date: < today}``. For each overdue
    row it loads the document, sets ``reverted = 1`` and ``status = Reverted``,
    saves it, writes a Salis Activity Log entry, and still raises a Critical
    "Excessive Topup" alert.

    Each row is guarded in its own ``try/except`` (rollback + log) so one
    failure never aborts the batch. No ``commit()`` inside the loop — the
    scheduler commits the job transaction on success.
    """
    from frappe.utils import today

    from apex_habitat.salis.salis_lib import log_activity

    today_str = today()
    logger = frappe.logger()

    start = 0
    while True:
        topups = frappe.get_all(
            "Fuel Topup Request",
            filters={
                "is_temporary": 1,
                "reverted": 0,
                "status": ["in", ["Approved", "Done"]],
                "revert_due_date": ["<", today_str],
            },
            fields=["name", "vehicle", "driver", "revert_due_date", "topup_litres"],
            limit_start=start,
            limit_page_length=BATCH_SIZE,
        )
        if not topups:
            break

        for t in topups:
            try:
                # --- Auto-revert the overdue temporary top-up ----------------
                doc = frappe.get_doc("Fuel Topup Request", t.name)
                doc.reverted = 1
                doc.status = "Reverted"
                doc.save(ignore_permissions=True)  # audit-ok
                log_activity(
                    "fuel_topup_auto_reverted",
                    "Fuel Topup Request",
                    t.name,
                    {
                        "reason": "overdue temporary top-up",
                        "revert_due_date": str(t.revert_due_date),
                        "topup_litres": t.topup_litres,
                    },
                )

                # --- Still raise the alert -----------------------------------
                msg = (f"unreverted_topup_watch: temporary top-up {t.name} "
                       f"({t.topup_litres} L) was due to be reverted on "
                       f"{t.revert_due_date}; it has now been auto-reverted.")
                logger.warning(msg)
                _raise_alert("Excessive Topup", "Critical", msg,
                             "Fuel Topup Request", t.name,
                             vehicle=t.vehicle, driver=t.driver)
            except Exception:
                frappe.db.rollback()
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Unreverted top-up watch failed for {t.name}"[:140],
                )

        start += BATCH_SIZE


def overdue_fuel_request_watch() -> None:
    """Flag fuel requests stuck in Pending past ``fuel_pending_max_days``.

    Reads submitted Fuel Request ``{status: Pending}`` whose ``request_date`` is
    older than ``fuel_pending_max_days`` (Salis Settings; default 2) and raises
    a Warning "Forgotten Request" alert per row.
    """
    from frappe.utils import add_days, date_diff, today

    today_str = today()
    logger = frappe.logger()
    max_days = _settings_int("fuel_pending_max_days", 2)
    cutoff = add_days(today_str, -max_days)

    start = 0
    while True:
        requests = frappe.get_all(
            "Fuel Request",
            filters={
                "status": "Pending",
                "docstatus": 1,
                "request_date": ["<", cutoff],
            },
            fields=["name", "vehicle", "driver", "request_date"],
            limit_start=start,
            limit_page_length=BATCH_SIZE,
        )
        if not requests:
            break

        for r in requests:
            try:
                age = date_diff(today_str, r.request_date) if r.request_date else 0
                msg = (f"overdue_fuel_request_watch: fuel request {r.name} has been "
                       f"Pending for {age} days (since {r.request_date}).")
                logger.warning(msg)
                _raise_alert("Forgotten Request", "Warning", msg,
                             "Fuel Request", r.name,
                             vehicle=r.vehicle, driver=r.driver)
            except Exception:
                frappe.db.rollback()
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Overdue fuel request watch failed for {r.name}"[:140],
                )

        start += BATCH_SIZE


def missing_attendance_watch() -> None:
    """Flag active drivers with no Driver Attendance recorded today.

    For each Salis Driver ``{status: Active}`` checks for a submitted Driver
    Attendance for today. If none exists, raises an Info "Supervisor Delay"
    alert (the Operations Alert DocType has no dedicated "Attendance Gap"
    option, so the nearest existing option is reused).
    """
    from frappe.utils import today

    today_str = today()
    logger = frappe.logger()

    start = 0
    while True:
        drivers = frappe.get_all(
            "Salis Driver",
            filters={"status": "Active"},
            fields=["name"],
            limit_start=start,
            limit_page_length=BATCH_SIZE,
        )
        if not drivers:
            break

        for d in drivers:
            try:
                has_attendance = frappe.db.exists(
                    "Driver Attendance",
                    {"driver": d.name, "attendance_date": today_str, "docstatus": 1},
                )
                if has_attendance:
                    continue
                # Reference the driver by docname only — never embed PII
                # (full_name / national_id / phone) in alert text.
                who = d.name
                msg = (f"missing_attendance_watch: no attendance recorded today for "
                       f"active driver {who}.")
                logger.warning(msg)
                _raise_alert("Supervisor Delay", "Info", msg,
                             "Salis Driver", d.name, driver=d.name)
            except Exception:
                frappe.db.rollback()
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Missing attendance watch failed for {d.name}"[:140],
                )

        start += BATCH_SIZE


# ---------------------------------------------------------------------------
# Weekly job
# ---------------------------------------------------------------------------


def vehicle_utilization_summary() -> None:
    """Write a trailing-7-day utilisation summary per Active vehicle.

    For each Active vehicle, aggregates the count of Dispatch Trips and the
    distance (sum of ``odometer_end - odometer_start``) over the last 7 days and
    writes a Salis Activity Log row (action ``vehicle_utilization_summary``,
    details = JSON). Vehicles with zero trips additionally get an Info
    "Idle Vehicle" alert as a weekly recap. Idempotent per day via the alert
    dedupe; the Activity Log is append-only history.
    """
    from frappe.utils import add_days, now_datetime, today

    today_str = today()
    window_start = add_days(today_str, -7)
    logger = frappe.logger()

    start = 0
    while True:
        vehicles = frappe.get_all(
            "Salis Vehicle",
            filters={"status": "Active"},
            fields=["name", "plate_number"],
            limit_start=start,
            limit_page_length=BATCH_SIZE,
        )
        if not vehicles:
            break

        for v in vehicles:
            try:
                trips = frappe.get_all(
                    "Dispatch Trip",
                    filters={
                        "vehicle": v.name,
                        "docstatus": 1,
                        "status": ["in", ["Dispatched", "Completed"]],
                        "trip_date": ["between", [window_start, today_str]],
                    },
                    fields=["odometer_start", "odometer_end"],
                )
                trip_count = len(trips)
                distance = 0
                for tr in trips:
                    s_odo = tr.odometer_start or 0
                    e_odo = tr.odometer_end or 0
                    if e_odo > s_odo:
                        distance += e_odo - s_odo

                details = {
                    "window_start": window_start,
                    "window_end": today_str,
                    "trip_count": trip_count,
                    "distance": distance,
                }
                frappe.get_doc(
                    {
                        "doctype": "Salis Activity Log",
                        "action": "vehicle_utilization_summary",
                        "entity_type": "Salis Vehicle",
                        "entity_name": v.name,
                        "user": "Administrator",
                        "logged_at": now_datetime(),
                        "details": json.dumps(details),
                    }
                ).insert(ignore_permissions=True)  # audit-ok

                plate = v.plate_number or v.name
                logger.info(
                    f"vehicle_utilization_summary: {plate} — {trip_count} trips, "
                    f"{distance} km over the last 7 days."
                )

                if trip_count == 0:
                    msg = (f"vehicle_utilization_summary: vehicle {plate} logged no "
                           f"dispatch trips in the last 7 days.")
                    _raise_alert("Idle Vehicle", "Info", msg,
                                 "Salis Vehicle", v.name, vehicle=v.name)
            except Exception:
                frappe.db.rollback()
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Vehicle utilisation summary failed for {v.name}"[:140],
                )

        start += BATCH_SIZE

    logger.info("vehicle_utilization_summary: weekly summaries written.")
