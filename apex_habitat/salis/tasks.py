# Copyright (c) 2026, AFMCO and contributors
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

# [#661ibk]
ALERT_DOCTYPE = "Operations Alert"


def _settings_int(fieldname: str, default: int) -> int:
    """Read an Int from the Salis Settings single, falling back to ``default``.

    Thin alias over the canonical ``get_salis_int`` coalesce helper, kept for the
    existing in-module call sites."""
    from apex_habitat.apex_core.doctype.salis_settings.salis_settings import get_salis_int

    return get_salis_int(fieldname, default)


def _resolve_project_supervisor(vehicle: str | None) -> str | None:
    """Resolve the vehicle's project supervisor User, or None.

    Denormalised onto the Operations Alert so the Critical-alert Notification can
    reach the specific project's supervisor (a User Permission holder) — Frappe
    notification recipients cannot follow the vehicle -> project -> supervisor
    chain declaratively. Never raises: a lookup failure must not abort the job.
    """
    if not vehicle:
        return None
    try:
        from apex_habitat.salis.permissions import _project_supervisor

        project = frappe.db.get_value("Salis Vehicle", vehicle, "project")
        return _project_supervisor(project)
    except Exception:
        # Best-effort denorm: never abort the job, but log so a real
        # misconfiguration is not silently invisible.
        frappe.log_error(title="Salis: resolve project supervisor failed")
        return None


def _vehicle_project(vehicle: str | None) -> str | None:
    """The vehicle's project, or None. Never raises (a lookup must not abort the job)."""
    if not vehicle:
        return None
    try:
        return frappe.db.get_value("Salis Vehicle", vehicle, "project")
    except Exception:
        # Best-effort denorm: never abort the job, but log the failure.
        frappe.log_error(title="Salis: resolve vehicle project failed")
        return None


def _publish_operations_alert(project: str | None = None) -> None:
    """Signal the operations board to refetch its alert strip/queue. Broadcast to
    the site room; the board filters by project client-side (a None project reloads
    every open board). after_commit so subscribers read committed state. Best-effort:
    a publish failure must never abort the scheduler job."""
    try:
        frappe.publish_realtime("operations_alert", {"project": project}, after_commit=True)
    except Exception:
        pass


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
    from frappe.utils import add_days, now_datetime, today

    # [#91pwgy] raised_on is a Datetime; a "today" window must derive both bounds
    # from ONE today() call. A "<= 23:59:59" upper bound silently drops a row stamped
    # 23:59:59.xxxxxx (the column keeps microseconds), and two separate today() calls
    # could straddle midnight — both reopen the duplicate alert the dedupe suppresses.
    # The upper bound is next-day-midnight (between is inclusive, but now_datetime()
    # never lands on exactly .000000, so tomorrow's first row is not falsely matched).
    day = today()
    dedupe_filters = {
        "alert_type": alert_type,
        "status": "Open",
        "raised_on": ["between", [f"{day} 00:00:00", f"{add_days(day, 1)} 00:00:00"]],
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

    # [#sqhguz]
    alert_name = None
    project_supervisor = _resolve_project_supervisor(vehicle)
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
                "project_supervisor": project_supervisor,
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

    # Push the operations board to refetch when a new alert lands on a project in
    # view (ahead of its poll). after_commit so subscribers read committed state;
    # client filters by project, so a vehicle-less alert (no project) reloads all.
    _publish_operations_alert(_vehicle_project(vehicle))

    # [#gg8xk4]
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


# [#mv9l4k]


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

    # [#r94w3h]
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
                # [#q9q3e3]
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

    Reads Fuel Request ``{request_type: Top-up, is_temporary: 1, reverted: 0,
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
            "Fuel Request",
            filters={
                "request_type": "Top-up",
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
                # [#6vxo7i]
                doc = frappe.get_doc("Fuel Request", t.name)
                doc.reverted = 1
                doc.status = "Reverted"
                doc.save(ignore_permissions=True)  # audit-ok
                doc.add_comment(
                    "Info",
                    _("Auto-reverted: overdue temporary top-up (was due {0}).").format(
                        t.revert_due_date
                    ),
                )

                # [#n5yd9u]
                msg = (f"unreverted_topup_watch: temporary top-up {t.name} "
                       f"({t.topup_litres} L) was due to be reverted on "
                       f"{t.revert_due_date}; it has now been auto-reverted.")
                logger.warning(msg)
                _raise_alert("Excessive Topup", "Critical", msg,
                             "Fuel Request", t.name,
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

    # [#hww2kb]
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
                # [#bces73]
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


def daily_open_alerts_digest() -> None:
    """Email each Fleet Supervisor a daily roll-up of their open Operations Alerts.

    Complements the per-alert Critical notification (fires once on raise) with a
    standing summary: every Open/Acknowledged alert, grouped by the denormalised
    ``project_supervisor`` (the owning supervisor of the alert's project). Each
    supervisor receives only their own bucket, so the digest respects the same
    project boundary as the desk without re-deriving scope here.

    Alerts with no ``project_supervisor`` (e.g. driver-only alerts that resolve no
    project) have no owning supervisor and are skipped — oversight roles already
    see every alert. Per-supervisor delivery is isolated (rollback before log) so
    one bad recipient never aborts the rest. Idempotent enough for daily cadence:
    re-running re-sends the current snapshot, it never mutates state.
    """
    from collections import defaultdict

    from frappe.utils import escape_html, get_url_to_list

    from apex_habitat.apex_core.utils.email_gate import email_enabled

    logger = frappe.logger()

    # Master email kill-switch (default OFF): without it the daily send floods
    # OutgoingEmailError on a site with no outgoing Email Account configured.
    if not email_enabled():
        logger.info("daily_open_alerts_digest: email disabled (Habitat Settings); skipped.")
        return

    by_supervisor: dict[str, list] = defaultdict(list)
    start = 0
    while True:
        alerts = frappe.get_all(
            ALERT_DOCTYPE,
            filters={
                "status": ["in", ["Open", "Acknowledged"]],
                "project_supervisor": ["is", "set"],
            },
            fields=["name", "alert_type", "severity", "vehicle", "driver",
                    "message", "project_supervisor"],
            order_by="severity asc, raised_on asc",
            limit_start=start,
            limit_page_length=BATCH_SIZE,
        )
        if not alerts:
            break
        for a in alerts:
            by_supervisor[a.project_supervisor].append(a)
        start += BATCH_SIZE

    if not by_supervisor:
        logger.info("daily_open_alerts_digest: no open alerts with an owning supervisor.")
        return

    list_url = get_url_to_list(ALERT_DOCTYPE)
    severities = ("Critical", "Warning", "Info")
    sent = 0
    for supervisor, rows in by_supervisor.items():
        try:
            if not frappe.db.get_value("User", supervisor, "enabled"):
                continue
            counts = {s: sum(1 for r in rows if r.severity == s) for s in severities}
            summary = ", ".join(
                _("{0}: {1}").format(_(s), counts[s]) for s in severities if counts[s]
            )
            items = "".join(
                "<li>[{severity}] {atype} — {target}: {msg}</li>".format(
                    severity=escape_html(_(r.severity)),
                    atype=escape_html(_(r.alert_type)),
                    target=escape_html(r.vehicle or r.driver or "—"),
                    msg=escape_html((r.message or "")[:200]),
                )
                for r in rows
            )
            message = "{intro} ({summary}).<br><ul>{items}</ul><br><a href='{url}'>{cta}</a>".format(
                intro=_("You have {0} open operations alert(s)").format(len(rows)),
                summary=summary,
                items=items,
                url=list_url,
                cta=_("Open the operations alert list"),
            )
            frappe.sendmail(
                recipients=[supervisor],
                subject=_("Daily Open Operations Alerts: {0}").format(len(rows)),
                message=message,
            )
            sent += 1
        except Exception:
            frappe.db.rollback()
            frappe.log_error(
                message=frappe.get_traceback(),
                title=f"Open-alerts digest failed for {supervisor}"[:140],
            )

    logger.info(f"daily_open_alerts_digest: sent {sent} supervisor digest(s).")


# [#9kfa8z]


def _resolve_alert(alert_name: str, reason: str) -> bool:
    """Resolve an Operations Alert: set ``status = Resolved`` and stamp
    ``resolved_on`` + ``resolution_note``, then drop an audit comment.

    Idempotent: an alert that is already ``Resolved`` is left untouched (no
    status flip, no fresh ``resolved_on``, no duplicate comment) so a re-run
    cannot flip-flop the row or rewrite its resolution timestamp. Returns
    ``True`` only when this call performed the resolution. Per-alert error
    isolation is the caller's responsibility.
    """
    from frappe.utils import now_datetime

    current = frappe.db.get_value(ALERT_DOCTYPE, alert_name, "status")
    if current == "Resolved":
        return False

    # [#r0ukij]
    frappe.db.set_value(
        ALERT_DOCTYPE,
        alert_name,
        {
            "status": "Resolved",
            "resolved_on": now_datetime(),
            "resolution_note": reason[:140],
        },
        update_modified=True,
    )
    try:
        frappe.get_doc(ALERT_DOCTYPE, alert_name).add_comment(
            "Info", _("Auto-resolved: {0}").format(reason)
        )
    except Exception:
        # [#qh1i7r]
        frappe.log_error(
            message=frappe.get_traceback(),
            title=f"Alert resolve comment failed for {alert_name}"[:140],
        )
    return True


def resolve_excessive_topup_alerts(vehicle: str | None, reason: str) -> int:
    """Resolve any open/acknowledged ``Excessive Topup`` alert for ``vehicle``.

    Event-driven counterpart to the periodic resolver: callers fire this from a
    clean source event (e.g. a temporary top-up is reverted) so the alert clears
    immediately rather than waiting for the next daily reconciliation pass. Safe
    to call even when no matching alert exists (returns 0) and idempotent
    (already-Resolved rows are filtered out). Never raises: a failure is logged
    and swallowed so it cannot abort the source-document save that triggered it.

    Returns the number of alerts this call resolved.
    """
    if not vehicle:
        return 0
    resolved = 0
    try:
        open_alerts = frappe.get_all(
            ALERT_DOCTYPE,
            filters={
                "alert_type": "Excessive Topup",
                "vehicle": vehicle,
                "status": ["in", ["Open", "Acknowledged"]],
            },
            pluck="name",
        )
        for name in open_alerts:
            if _resolve_alert(name, reason):
                resolved += 1
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            message=frappe.get_traceback(),
            title=f"Excessive-topup alert resolve-on-event failed ({vehicle})"[:140],
        )
    return resolved


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
    * **Excessive Topup** — neither source still breaches for the vehicle: no
      unreverted temporary top-up remains past its revert-due date AND current-
      month ledgered consumption is back within the active quota (+ margin). The
      overdue-top-up variant is also resolved immediately on the revert event
      (``Fuel Request.on_update_after_submit``); this pass is the catch-up.

    Idempotent (already-Resolved rows are skipped by the status filter; a re-run
    resolves nothing new once conditions are stable) and never aborts: each alert
    is handled in its own try/except with rollback-before-log.
    """
    from frappe.utils import add_days, getdate, today

    today_str = today()
    today_date = getdate(today_str)
    logger = frappe.logger()
    resolved_count = 0

    # [#dh8hm0]
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

    # [#e2kiah]
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

    # [#ckt0ba]
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

    # [#2yh1kv]
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

    # [#4oiqbl]
    excessive_topup_vehicles = {
        r["vehicle"]
        for r in frappe.db.sql(
            """
            SELECT DISTINCT vehicle FROM `tabFuel Request`
            WHERE request_type = 'Top-up' AND is_temporary = 1 AND reverted = 0
              AND docstatus = 1 AND status IN ('Approved', 'Done')
              AND revert_due_date < %(today)s AND vehicle IS NOT NULL
            """,
            {"today": today_str},
            as_dict=True,
        )
    }
    from apex_habitat.salis.fuel_engine import _period_month, get_overage_margin

    overage_margin = get_overage_margin()
    period_month = _period_month(today_str)
    for r in frappe.db.sql(
        """
        SELECT q.vehicle AS vehicle, q.monthly_litres AS quota,
               COALESCE(SUM(l.litres), 0) AS consumed
        FROM `tabFuel Quota` q
        LEFT JOIN `tabFuel Consumption Ledger` l
          ON l.vehicle = q.vehicle AND l.period_month = q.period_month
        WHERE q.docstatus = 1 AND q.status = 'Active'
          AND q.period_month = %(period)s AND q.vehicle IS NOT NULL
        GROUP BY q.name, q.vehicle, q.monthly_litres
        """,
        {"period": period_month},
        as_dict=True,
    ):
        quota = float(r["quota"] or 0)
        consumed = float(r["consumed"] or 0)
        if quota > 0 and consumed > quota * (1 + overage_margin):
            excessive_topup_vehicles.add(r["vehicle"])

    def _vehicle_active(vehicle: str | None) -> bool:
        return bool(vehicle) and frappe.db.get_value("Salis Vehicle", vehicle, "status") == "Active"

    def _driver_active(driver: str | None) -> bool:
        return bool(driver) and frappe.db.get_value("Salis Driver", driver, "status") == "Active"

    # [#dkxfl4]
    resolved_projects: set[str | None] = set()
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

                elif atype == "Excessive Topup":
                    # [#1hftuh]
                    if a.vehicle and a.vehicle not in excessive_topup_vehicles:
                        clear, reason = True, "no fuel overage or unreverted top-up remains for the vehicle"

                if clear and _resolve_alert(a.name, reason):
                    resolved_count += 1
                    resolved_projects.add(_vehicle_project(a.vehicle))
            except Exception:
                frappe.db.rollback()
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Alert reconciliation failed for {a.name}"[:140],
                )

        start += BATCH_SIZE

    # Push the operations board to refetch once per project whose alert(s) cleared,
    # so a resolved alert disappears without a manual Refresh.
    for project in resolved_projects:
        _publish_operations_alert(project)

    logger.info(
        f"reconcile_operations_alerts: resolved {resolved_count} alert(s) whose "
        f"condition has cleared."
    )


# [#7jd34a]


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

    # [#gdp7wq]
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

                # [#rsz9o4]
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


def _overstay_stops() -> list:
    """Submitted Maintenance Vehicle Stops still open past the overstay cutoff,
    for vehicles still out of service.

    A vehicle is overstaying if it is still Stopped / Under Maintenance and
    carries a submitted Vehicle Stop (reason Maintenance) with no ``return_date``
    whose ``stop_date`` is on or before the cutoff (``workshop_overstay_days``;
    Salis Settings, default 14). Shared by ``workshop_overstay_watch`` (the alert)
    and ``get_workshop_overstay_count`` (the number card) so the rule cannot drift
    between them. Returns the Vehicle Stop rows (name, vehicle, stop_date).
    """
    from frappe.utils import add_days, today

    days = _settings_int("workshop_overstay_days", 14)
    cutoff = add_days(today(), -days)
    rows = frappe.get_all(
        "Vehicle Stop",
        filters={
            "stop_reason": "Maintenance",
            "docstatus": 1,
            # canonical "still open" check: matches NULL or empty return_date
            "return_date": ["is", "not set"],
            "stop_date": ["<=", cutoff],
        },
        fields=["name", "vehicle", "stop_date"],
    )
    # [#3pcbzi] Bulk-prefetch the vehicles' status in one query keyed on the stops'
    # vehicle ids, instead of one get_value per stop (N+1). Filter the still-out-of-
    # service set in memory — same rows as before.
    vehicle_ids = {r.vehicle for r in rows if r.vehicle}
    statuses = (
        {
            v["name"]: v["status"]
            for v in frappe.get_all(
                "Salis Vehicle", filters={"name": ["in", list(vehicle_ids)]}, fields=["name", "status"]
            )
        }
        if vehicle_ids
        else {}
    )
    return [
        r
        for r in rows
        if r.vehicle and statuses.get(r.vehicle) in ("Stopped", "Under Maintenance")
    ]


def workshop_overstay_watch() -> None:
    """Flag vehicles in the workshop longer than ``workshop_overstay_days``.

    Raises one "Maintenance Overdue" Operations Alert per overstaying vehicle
    (see ``_overstay_stops`` for the rule), deduped daily by ``_raise_alert``.
    """
    days = _settings_int("workshop_overstay_days", 14)
    logger = frappe.logger()
    for r in _overstay_stops():
        try:
            msg = _("Vehicle {0} has been in the workshop since {1} (over {2} days).").format(
                r.vehicle, r.stop_date, days
            )
            logger.warning(
                f"workshop_overstay_watch: vehicle {r.vehicle} in workshop since "
                f"{r.stop_date} (over {days} days)."
            )
            _raise_alert(
                "Maintenance Overdue", "Warning", msg,
                source_doctype="Vehicle Stop", source_name=r.name, vehicle=r.vehicle,
            )
        except Exception:
            frappe.db.rollback()
            frappe.log_error(
                message=frappe.get_traceback(),
                title=f"Workshop overstay watch failed for {r.name}"[:140],
            )


@frappe.whitelist()
def get_workshop_overstay_count(filters=None) -> dict:
    """Custom Number Card: how many vehicles are overstaying in the workshop.

    Same rule as the Maintenance Overdue alert, shared via ``_overstay_stops`` so
    the card and the alert cannot disagree. Scoped to the viewer's permitted
    projects to match the other fleet number cards. ``filters`` is accepted and
    ignored (the Custom Number Card widget always passes it).
    """
    from apex_habitat.salis.api.dispatch_board import _permitted_projects

    # [#goe0en]
    frappe.has_permission("Salis Vehicle", "read", throw=True)
    vehicles = {r.vehicle for r in _overstay_stops()}
    if not vehicles:
        return {"value": 0}
    unscoped, projects = _permitted_projects()
    v_filters = {"name": ["in", list(vehicles)]}
    if not unscoped:
        if not projects:
            return {"value": 0}
        v_filters["project"] = ["in", projects]
    return {"value": frappe.db.count("Salis Vehicle", v_filters)}
