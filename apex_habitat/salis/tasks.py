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

import frappe
from frappe import _

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
    # Compliance documents (driver licences) need at least 30 days' lead
    # notice. Prefer a dedicated ``license_alert_lead_days`` (default 30); else
    # fall back to the generic ``alert_lead_days`` but never below 30 days.
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

    A vehicle is idle if it has no submitted Dispatch Trip (status
    Dispatched/Completed) on or after the cutoff (``idle_vehicle_days``; Salis
    Settings, default 7). Previously this ran one ``get_all`` per vehicle (N+1);
    now a single grouped query returns the set of vehicles WITH a recent trip,
    and the idle set is the difference in memory — same behaviour, one DB round
    trip for the trip data instead of one per vehicle.
    """
    from frappe.utils import add_days, today

    today_str = today()
    logger = frappe.logger()
    idle_days = _settings_int("idle_vehicle_days", 7)
    cutoff = add_days(today_str, -idle_days)

    # One grouped read: every vehicle with at least one qualifying recent trip.
    try:
        rows = frappe.db.sql(
            """
            SELECT vehicle
            FROM `tabDispatch Trip`
            WHERE docstatus = 1
              AND status IN ('Dispatched', 'Completed')
              AND trip_date >= %(cutoff)s
              AND vehicle IS NOT NULL
            GROUP BY vehicle
            """,
            {"cutoff": cutoff},
            as_dict=True,
        )
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            message=frappe.get_traceback(),
            title="Idle vehicle watch: recent-trip aggregate failed"[:140],
        )
        return
    vehicles_with_recent_trip = {r["vehicle"] for r in rows}

    start = 0
    while True:
        vehicles = frappe.get_all(
            "Salis Vehicle",
            filters={"status": "Active"},
            fields=["name"],
            limit_start=start,
            limit_page_length=BATCH_SIZE,
        )
        if not vehicles:
            break

        for v in vehicles:
            try:
                if v.name in vehicles_with_recent_trip:
                    continue
                # Reference the vehicle by docname only — never embed
                # plate_number (PII-adjacent) in alert text; the alert links
                # the vehicle record.
                msg = (f"idle_vehicle_watch: vehicle {v.name} has had no dispatch "
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
    then raise an alert for each.

    Reads Fuel Topup Request ``{is_temporary: 1, reverted: 0,
    status in [Approved, Done], revert_due_date: < today}``. For each overdue
    row it loads the document, sets ``reverted = 1`` and ``status = Reverted``,
    saves it (the change is captured natively by Version / track_changes), and
    still raises a Critical "Excessive Topup" alert.

    Each row is guarded in its own ``try/except`` (rollback + log) so one
    failure never aborts the batch. No ``commit()`` inside the loop — the
    scheduler commits the job transaction on success.
    """
    from frappe.utils import today

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
                doc.add_comment(
                    "Info",
                    _("Auto-reverted: overdue temporary top-up (was due {0}).").format(
                        t.revert_due_date
                    ),
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

    # One grouped read: every driver who already has a submitted attendance
    # today. Previously this ran one ``exists`` per active driver (N+1); now the
    # "has attendance" set is fetched once and the gap set is the difference in
    # memory — same behaviour, one DB round trip for the attendance data.
    try:
        rows = frappe.db.sql(
            """
            SELECT driver
            FROM `tabDriver Attendance`
            WHERE docstatus = 1
              AND attendance_date = %(today)s
              AND driver IS NOT NULL
            GROUP BY driver
            """,
            {"today": today_str},
            as_dict=True,
        )
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            message=frappe.get_traceback(),
            title="Missing attendance watch: attendance aggregate failed"[:140],
        )
        return
    drivers_with_attendance = {r["driver"] for r in rows}

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
                if d.name in drivers_with_attendance:
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


def vehicle_compliance_expiry_watch() -> None:
    """Alert on vehicle compliance documents at or past their expiry window.

    Reads Salis Vehicle Compliance child rows whose ``expiry_date`` is within
    ``alert_lead_days`` (Salis Settings; default 30) of today. For each row
    raises a "License Expiry" alert referencing the parent vehicle and
    compliance type — Critical if already expired, otherwise Warning. Per-row
    de-dup is handled by ``_raise_alert`` (one Open alert per vehicle+type+day).
    """
    from frappe.utils import add_days, getdate, today

    today_str = today()
    today_date = getdate(today_str)
    logger = frappe.logger()
    lead_days = _settings_int("alert_lead_days", 30)
    horizon = add_days(today_str, lead_days)

    start = 0
    while True:
        rows = frappe.get_all(
            "Salis Vehicle Compliance",
            filters={"expiry_date": ["<=", horizon]},
            fields=["parent", "compliance_type", "expiry_date"],
            limit_start=start,
            limit_page_length=BATCH_SIZE,
        )
        if not rows:
            break

        for c in rows:
            try:
                expired = bool(c.expiry_date) and getdate(c.expiry_date) < today_date
                severity = "Critical" if expired else "Warning"
                state = "expired on" if expired else "expires on"
                msg = (f"vehicle_compliance_expiry_watch: vehicle {c.parent} "
                       f"{c.compliance_type} compliance {state} {c.expiry_date}.")
                logger.warning(msg)
                _raise_alert("License Expiry", severity, msg,
                             "Salis Vehicle", c.parent, vehicle=c.parent)
            except Exception:
                frappe.db.rollback()
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Vehicle compliance watch failed for {c.parent}"[:140],
                )

        start += BATCH_SIZE


# ---------------------------------------------------------------------------
# Alert reconciliation (auto-resolve)
# ---------------------------------------------------------------------------


def _resolve_alert(alert_name: str, reason: str) -> None:
    """Set an Operations Alert to Resolved and drop an audit comment. Idempotent:
    a re-run that finds the alert already Resolved is a no-op. Per-alert error
    isolation is the caller's responsibility."""
    frappe.db.set_value(ALERT_DOCTYPE, alert_name, "status", "Resolved", update_modified=True)
    try:
        frappe.get_doc(ALERT_DOCTYPE, alert_name).add_comment(
            "Info", _("Auto-resolved: {0}").format(reason)
        )
    except Exception:
        # The status flip is the source of truth; a failed comment must not
        # roll it back. Log and carry on.
        frappe.log_error(
            message=frappe.get_traceback(),
            title=f"Alert resolve comment failed for {alert_name}"[:140],
        )


def reconcile_operations_alerts() -> None:
    """Auto-resolve open/acknowledged Operations Alerts whose underlying condition
    no longer holds, so alerts do not accumulate forever.

    Nothing previously closed alerts (License Expiry / Idle Vehicle / overdue
    request / attendance-gap rows piled up indefinitely). This daily pass
    re-evaluates the live condition that originally raised each open alert and
    flips it to ``Resolved`` once cleared:

    * **Idle Vehicle** — the vehicle now has a submitted Dispatch Trip
      (Dispatched/Completed) within ``idle_vehicle_days``, or is no longer Active.
    * **License Expiry** — (vehicle) no Salis Vehicle Compliance row is expired or
      within ``alert_lead_days``; (driver) the driver's licence is beyond the lead
      window, or the driver is no longer Active.
    * **Forgotten Request** — no submitted Fuel Request remains Pending past
      ``fuel_pending_max_days`` for the alert's vehicle/driver.
    * **Supervisor Delay** — the driver has a submitted Driver Attendance for the
      day the alert was raised, or is no longer Active.

    "Excessive Topup" is intentionally NOT auto-resolved: it flags a financial
    overage / overdue temporary top-up that a human must acknowledge and clear.

    Idempotent (already-Resolved rows are skipped by the status filter; a re-run
    resolves nothing new once conditions are stable) and never aborts: each alert
    is handled in its own try/except with rollback-before-log.
    """
    from frappe.utils import add_days, getdate, today

    today_str = today()
    today_date = getdate(today_str)
    logger = frappe.logger()
    resolved_count = 0

    # --- Bulk pre-computation (no per-alert N+1) -----------------------------
    idle_days = _settings_int("idle_vehicle_days", 7)
    lead_days = _settings_int("alert_lead_days", 30)
    license_lead = max(
        _settings_int("license_alert_lead_days", 30),
        _settings_int("alert_lead_days", 7),
        30,
    )
    pending_max_days = _settings_int("fuel_pending_max_days", 2)
    idle_cutoff = add_days(today_str, -idle_days)
    pending_cutoff = add_days(today_str, -pending_max_days)

    # Vehicles with a qualifying recent trip (Idle Vehicle clears).
    vehicles_with_recent_trip = {
        r["vehicle"]
        for r in frappe.db.sql(
            """
            SELECT vehicle FROM `tabDispatch Trip`
            WHERE docstatus = 1 AND status IN ('Dispatched', 'Completed')
              AND trip_date >= %(cutoff)s AND vehicle IS NOT NULL
            GROUP BY vehicle
            """,
            {"cutoff": idle_cutoff},
            as_dict=True,
        )
    }

    # Vehicles that STILL have an expired/expiring compliance row (License Expiry
    # stays open). The set of "clear" vehicles is the complement.
    horizon = add_days(today_str, lead_days)
    vehicles_with_open_compliance = {
        r["parent"]
        for r in frappe.db.sql(
            """
            SELECT DISTINCT parent FROM `tabSalis Vehicle Compliance`
            WHERE expiry_date IS NOT NULL AND expiry_date <= %(horizon)s
            """,
            {"horizon": horizon},
            as_dict=True,
        )
    }

    # Vehicles / drivers that STILL have an overdue Pending fuel request.
    overdue_request_vehicles = set()
    overdue_request_drivers = set()
    for r in frappe.db.sql(
        """
        SELECT vehicle, driver FROM `tabFuel Request`
        WHERE docstatus = 1 AND status = 'Pending' AND request_date < %(cutoff)s
        """,
        {"cutoff": pending_cutoff},
        as_dict=True,
    ):
        if r["vehicle"]:
            overdue_request_vehicles.add(r["vehicle"])
        if r["driver"]:
            overdue_request_drivers.add(r["driver"])

    def _vehicle_active(vehicle: str | None) -> bool:
        return bool(vehicle) and frappe.db.get_value("Salis Vehicle", vehicle, "status") == "Active"

    def _driver_active(driver: str | None) -> bool:
        return bool(driver) and frappe.db.get_value("Salis Driver", driver, "status") == "Active"

    # --- Iterate open alerts and resolve the cleared ones --------------------
    start = 0
    while True:
        alerts = frappe.get_all(
            ALERT_DOCTYPE,
            filters={"status": ["in", ["Open", "Acknowledged"]]},
            fields=["name", "alert_type", "vehicle", "driver", "raised_on"],
            limit_start=start,
            limit_page_length=BATCH_SIZE,
        )
        if not alerts:
            break

        for a in alerts:
            try:
                clear = False
                reason = ""
                atype = a.alert_type

                if atype == "Idle Vehicle":
                    if not _vehicle_active(a.vehicle):
                        clear, reason = True, "vehicle is no longer Active"
                    elif a.vehicle in vehicles_with_recent_trip:
                        clear, reason = True, "vehicle has a recent dispatch trip"

                elif atype == "License Expiry":
                    if a.vehicle:
                        if not _vehicle_active(a.vehicle):
                            clear, reason = True, "vehicle is no longer Active"
                        elif a.vehicle not in vehicles_with_open_compliance:
                            clear, reason = True, "vehicle compliance is no longer expiring"
                    elif a.driver:
                        if not _driver_active(a.driver):
                            clear, reason = True, "driver is no longer Active"
                        else:
                            expiry = frappe.db.get_value("Salis Driver", a.driver, "license_expiry")
                            if expiry and getdate(expiry) > add_days(today_date, license_lead):
                                clear, reason = True, "driver licence renewed"

                elif atype == "Forgotten Request":
                    if a.vehicle and a.vehicle not in overdue_request_vehicles:
                        clear, reason = True, "no fuel request remains overdue for the vehicle"
                    elif a.driver and not a.vehicle and a.driver not in overdue_request_drivers:
                        clear, reason = True, "no fuel request remains overdue for the driver"

                elif atype == "Supervisor Delay":
                    if not _driver_active(a.driver):
                        clear, reason = True, "driver is no longer Active"
                    elif a.driver:
                        raised_day = str(a.raised_on)[:10] if a.raised_on else today_str
                        if frappe.db.exists(
                            "Driver Attendance",
                            {"driver": a.driver, "attendance_date": raised_day, "docstatus": 1},
                        ):
                            clear, reason = True, "attendance has since been recorded"

                if clear:
                    _resolve_alert(a.name, reason)
                    resolved_count += 1
            except Exception:
                frappe.db.rollback()
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Alert reconciliation failed for {a.name}"[:140],
                )

        start += BATCH_SIZE

    logger.info(
        f"reconcile_operations_alerts: resolved {resolved_count} alert(s) whose "
        f"condition has cleared."
    )


# ---------------------------------------------------------------------------
# Weekly job
# ---------------------------------------------------------------------------


def vehicle_utilization_summary() -> None:
    """Write a trailing-7-day utilisation summary per Active vehicle.

    For each Active vehicle, aggregates the count of Dispatch Trips and the
    distance (sum of ``odometer_end - odometer_start``) over the last 7 days and
    logs the result. Vehicles with zero trips additionally get an Info
    "Idle Vehicle" alert as a weekly recap (the actionable output, idempotent per
    day via the alert dedupe).
    """
    from frappe.utils import add_days, today

    today_str = today()
    window_start = add_days(today_str, -7)
    logger = frappe.logger()

    # One grouped read: trip count and total distance per vehicle over the
    # window. Previously this ran one ``get_all`` per active vehicle (N+1); now
    # the per-vehicle aggregates are fetched once and looked up in memory. Only
    # positive odometer deltas count toward distance (mirrors the prior
    # ``e_odo > s_odo`` guard), so the SQL clamps negatives to zero.
    try:
        agg_rows = frappe.db.sql(
            """
            SELECT
                vehicle,
                COUNT(*) AS trip_count,
                SUM(CASE WHEN odometer_end > odometer_start
                         THEN odometer_end - odometer_start ELSE 0 END) AS distance
            FROM `tabDispatch Trip`
            WHERE docstatus = 1
              AND status IN ('Dispatched', 'Completed')
              AND trip_date BETWEEN %(start)s AND %(end)s
              AND vehicle IS NOT NULL
            GROUP BY vehicle
            """,
            {"start": window_start, "end": today_str},
            as_dict=True,
        )
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            message=frappe.get_traceback(),
            title="Vehicle utilisation summary: trip aggregate failed"[:140],
        )
        return
    util_by_vehicle = {
        r["vehicle"]: (int(r["trip_count"] or 0), int(r["distance"] or 0))
        for r in agg_rows
    }

    start = 0
    while True:
        vehicles = frappe.get_all(
            "Salis Vehicle",
            filters={"status": "Active"},
            fields=["name"],
            limit_start=start,
            limit_page_length=BATCH_SIZE,
        )
        if not vehicles:
            break

        for v in vehicles:
            try:
                trip_count, distance = util_by_vehicle.get(v.name, (0, 0))

                # Reference the vehicle by docname only — never embed
                # plate_number (PII-adjacent) in alert/log text.
                logger.info(
                    f"vehicle_utilization_summary: {v.name} — {trip_count} trips, "
                    f"{distance} km over the last 7 days."
                )

                if trip_count == 0:
                    msg = (f"vehicle_utilization_summary: vehicle {v.name} logged no "
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
