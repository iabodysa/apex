"""Scheduled tasks for the Habitat module."""

from __future__ import annotations

import calendar

import frappe


def _notify_operational(source_doctype: str, source_name: str, message: str) -> None:
    """Post an operational notice to the source document's timeline, gated by the
    Habitat Settings "Enable Operational Notifications" toggle.

    This replaces the deprecated Habitat Operations Alert inserts: native Frappe
    timeline Comments (plus the configured Notification emails) carry operational
    notices. When the toggle is OFF the scheduler jobs run silently. Technical
    exceptions go to the standard Error Log, not here.
    """
    if not frappe.db.get_single_value("Habitat Settings", "enable_operational_notifications"):
        return
    if not (source_doctype and source_name):
        return
    try:
        frappe.get_doc(source_doctype, source_name).add_comment("Comment", message)
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            message=frappe.get_traceback(),
            title=f"Operational notification comment failed for {source_name}"[:140],
        )


def daily_accommodation_cost_allocation() -> None:
    """Allocate daily accommodation costs to the Accommodation Ledger.

    Iterates active Accommodation Assignments, computes each employee's
    daily cost share using the capacity-denominator algorithm, and writes
    an Operational Memo row to Accommodation Ledger.
    """
    from frappe.utils import today, flt

    posting_date = today()
    logger = frappe.logger()

    year = int(posting_date[:4])
    days_in_year = 366 if calendar.isleap(year) else 365

    cost_type_mapping = {
        "Rent": "annual_rent_sar",
        "Electricity": "annual_electricity_sar",
        "Water": "annual_water_sar",
        "Cleaning Staff Salary": "annual_cleaning_staff_sar",
        "Supervisor Salary": "annual_supervision_sar",
        "Other": "annual_other_expenses_sar"
    }

    # TODO(scale): enqueue per building via frappe.enqueue(per_building_cost_allocation,
    #   queue="long", timeout=3600) so the scheduler thread is not blocked on large datasets.
    #   Safe to do once building count grows beyond ~50; idempotency guard (frappe.db.exists)
    #   already protects against duplicate inserts from overlapping runs.

    # Paginate active submitted Accommodation Assignments at 500/batch
    building_cache: dict = {}  # T-01: cache building docs to avoid repeated get_doc per assignment
    start = 0
    batch_size = 500
    while True:
        active_assignments = frappe.get_all(
            "Accommodation Assignment",
            filters={
                "docstatus": 1,
                "check_out_date": ["is", "not set"]
            },
            fields=["name", "employee", "building", "project", "cost_center", "billed_to_supplier"],
            limit_start=start,
            limit_page_length=batch_size,
        )
        if not active_assignments:
            break

        for asgn in active_assignments:
            if not asgn.building:
                logger.warning(
                    f"daily_accommodation_cost_allocation: Assignment {asgn.name} has no building specified. Skipping."
                )
                continue

            if not asgn.employee:
                logger.warning(
                    f"daily_accommodation_cost_allocation: Assignment {asgn.name} has no employee specified. Skipping."
                )
                continue

            # T-01: fetch building from cache; only hit the DB on the first miss per building
            if asgn.building not in building_cache:
                try:
                    building_cache[asgn.building] = frappe.get_doc("Accommodation Building", asgn.building)
                except frappe.DoesNotExistError:
                    building_cache[asgn.building] = None

            building = building_cache[asgn.building]
            if building is None:
                logger.warning(
                    f"daily_accommodation_cost_allocation: Building {asgn.building} not found for assignment {asgn.name}. Skipping."
                )
                continue

            capacity = flt(building.total_capacity)
            if capacity <= 0:
                logger.warning(
                    f"daily_accommodation_cost_allocation: Building {building.name} has invalid capacity {capacity}. Skipping assignment {asgn.name}."
                )
                continue

            for ledger_type, building_field in cost_type_mapping.items():
                annual_cost = flt(building.get(building_field))
                if annual_cost <= 0:
                    continue

                # Compute employee daily share using leap-year-aware denominator
                daily_cost = flt(annual_cost / days_in_year, 5)
                daily_share = flt(daily_cost / capacity, 5)

                # Idempotence check: check if a ledger entry already exists
                exists = frappe.db.exists(
                    "Accommodation Ledger",
                    {
                        "employee": asgn.employee,
                        "posting_date": posting_date,
                        "assignment": asgn.name,
                        "building": asgn.building,
                        "ledger_type": ledger_type
                    }
                )

                if exists:
                    continue

                try:
                    ledger_entry = frappe.get_doc({
                        "doctype": "Accommodation Ledger",
                        "posting_date": posting_date,
                        "employee": asgn.employee,
                        "assignment": asgn.name,
                        "building": asgn.building,
                        "project": asgn.project,
                        "cost_center": asgn.cost_center,
                        "billed_to_supplier": asgn.billed_to_supplier,
                        "ledger_type": ledger_type,
                        "total_site_cost": annual_cost,
                        "capacity_denominator": int(capacity),
                        "employee_daily_share": daily_share,
                        "posting_mode": "Operational Memo",
                        "source_doctype": "Accommodation Assignment",
                        "source_name": asgn.name,
                        "allocation_basis": "Capacity",
                        "allocation_period_start": posting_date,
                        "allocation_period_end": posting_date,
                    })
                    ledger_entry.insert(ignore_permissions=True)
                except Exception as e:
                    frappe.db.rollback()  # T-02: rollback before log_error to avoid aborted-transaction errors
                    logger.error(
                        f"daily_accommodation_cost_allocation: Failed to insert ledger row for assignment {asgn.name}, cost {ledger_type}: {e}"
                    )
                    frappe.log_error(
                        message=frappe.get_traceback(),
                        title=f"Cost allocation: ledger insert failed ({asgn.name}/{ledger_type})"[:140],
                    )

        start += batch_size


def daily_building_license_expiry_check() -> None:
    """Warn when Building License documents are approaching or past expiry.

    Updates status of Building License records:
    - Expired: if today is past or equal to expiry_date.
    - Expiring Soon: if today is within renewal_lead_days (default 60) of expiry_date.
    """
    from frappe.utils import today, date_diff

    today_str = today()
    logger = frappe.logger()

    # Paginate submitted active licenses at 500/batch
    start = 0
    batch_size = 500
    while True:
        licenses = frappe.get_all(
            "Building License",
            filters={
                "docstatus": 1,
                "status": ["in", ["Active", "Expiring Soon"]]
            },
            fields=["name", "expiry_date", "renewal_lead_days", "status", "license_number", "license_type"],
            limit_start=start,
            limit_page_length=batch_size,
        )
        if not licenses:
            break

        for lic in licenses:
            expiry_date = lic.expiry_date
            if not expiry_date:
                continue

            try:
                default_lead = frappe.db.get_single_value("Habitat Settings", "license_expiry_days_before") or 60
                lead_days = lic.renewal_lead_days if lic.renewal_lead_days is not None else default_lead
                days_to_expiry = date_diff(expiry_date, today_str)

                if days_to_expiry <= 0:
                    if lic.status != "Expired":
                        frappe.db.set_value("Building License", lic.name, "status", "Expired")
                        msg = f"Building License {lic.name} ({lic.license_type} {lic.license_number}) has expired on {expiry_date}."
                        logger.warning(msg)
                        _notify_operational("Building License", lic.name, msg)
                elif days_to_expiry <= lead_days:
                    if lic.status != "Expiring Soon":
                        frappe.db.set_value("Building License", lic.name, "status", "Expiring Soon")
                        msg = f"Building License {lic.name} ({lic.license_type} {lic.license_number}) is expiring soon on {expiry_date} ({days_to_expiry} days remaining)."
                        logger.warning(msg)
                        _notify_operational("Building License", lic.name, msg)
            except Exception:
                frappe.db.rollback()  # T-05: rollback before log_error to avoid aborted-transaction errors
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"License expiry check failed for {lic.name}"[:140],
                )

        start += batch_size


def open_maintenance_escalation() -> None:
    """Escalate overdue open Maintenance Requests.

    Checks open requests (docstatus != 2, status in ('Open', 'Assigned', 'In Progress', 'Reopened'))
    and logs escalations based on priority and elapsed time.
    """
    from frappe.utils import now_datetime, get_datetime

    now = now_datetime()
    logger = frappe.logger()

    # Rules: (Hours open threshold)
    # Critical: > 24 hours
    # High: > 72 hours
    # Medium: > 168 hours
    # Low: > 336 hours
    thresholds = {
        "Critical": 24,
        "High": 72,
        "Medium": 168,
        "Low": 336
    }

    # Paginate non-cancelled open maintenance requests at 500/batch
    start = 0
    batch_size = 500
    while True:
        open_requests = frappe.get_all(
            "Maintenance Request",
            filters={
                "docstatus": ["!=", 2],
                "status": ["in", ["Open", "Assigned", "In Progress", "Reopened"]]
            },
            fields=["name", "priority", "creation", "status", "issue_type"],
            limit_start=start,
            limit_page_length=batch_size,
        )
        if not open_requests:
            break

        for req in open_requests:
            try:  # T-03: isolate per-row errors so one bad row does not abort the whole batch
                priority = req.priority or "Medium"
                threshold_hours = thresholds.get(priority, 168)

                creation_dt = get_datetime(req.creation)
                elapsed_hours = (now - creation_dt).total_seconds() / 3600.0

                if elapsed_hours > threshold_hours:
                    logger.warning(
                        f"Maintenance Request {req.name} ({req.issue_type}, status: {req.status}) "
                        f"is overdue! Priority: {priority}, hours open: {elapsed_hours:.1f} (threshold: {threshold_hours} hours)."
                    )
            except Exception:
                frappe.db.rollback()
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Maintenance escalation failed for {req.name}"[:140],
                )
                continue

        start += batch_size


def lease_expiry_watchlist() -> None:
    """Alert on buildings with leases expiring within 90 days.

    Reads Accommodation Building.lease_end_date (v2.3 calibration field).
    Sets lease_renewal_status = Expired for past-due leases.
    Email notifications are handled by Phase 7 Notification DocType config.
    """
    from frappe.utils import date_diff, today

    today_str = today()
    logger = frappe.logger()

    # Paginate active buildings with a lease_end_date at 500/batch
    start = 0
    batch_size = 500
    while True:
        buildings = frappe.get_all(
            "Accommodation Building",
            filters={"status": "Active", "lease_end_date": ["is", "set"]},
            fields=["name", "building_name", "lease_end_date", "lease_renewal_status"],
            limit_start=start,
            limit_page_length=batch_size,
        )
        if not buildings:
            break

        for b in buildings:
            try:
                lease_lead = frappe.db.get_single_value("Habitat Settings", "lease_expiry_days_before") or 90
                days = date_diff(b.lease_end_date, today_str)
                if days < 0 and b.lease_renewal_status != "Expired":
                    frappe.db.set_value(
                        "Accommodation Building", b.name, "lease_renewal_status", "Expired"
                    )
                    msg = f"lease_expiry_watchlist: {b.building_name} lease expired {abs(days)} days ago."
                    logger.warning(msg)
                    _notify_operational("Accommodation Building", b.name, msg)
                elif 0 <= days <= lease_lead:
                    msg = f"lease_expiry_watchlist: {b.building_name} lease expires in {days} days ({b.lease_end_date})."
                    logger.warning(msg)
                    _notify_operational("Accommodation Building", b.name, msg)
            except Exception:
                frappe.db.rollback()  # T-05: rollback before log_error to avoid aborted-transaction errors
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Lease expiry watchlist failed for {b.name}"[:140],
                )

        start += batch_size


def weekly_occupancy_sync() -> None:
    """Recalculate occupancy counters on all Accommodation Rooms and Buildings.

    Runs a full reconciliation pass to correct any counter drift caused by
    out-of-band data changes.
    """
    # --- Room pass ---
    # Paginate rooms at 500/batch; use frappe.db.set_value to avoid per-row .save()
    start = 0
    batch_size = 500
    while True:
        room_names = frappe.get_all(
            "Accommodation Room",
            pluck="name",
            limit_start=start,
            limit_page_length=batch_size,
        )
        if not room_names:
            break

        for room_name in room_names:
            try:
                active = frappe.db.count(
                    "Accommodation Assignment",
                    {"room": room_name, "docstatus": 1, "check_out_date": ["is", "not set"]},
                )
                capacity = frappe.db.get_value("Accommodation Room", room_name, "bed_capacity") or 0
                if active <= 0:
                    new_status = "Available"
                elif capacity and active >= capacity:
                    new_status = "Full"
                else:
                    new_status = "Partially Occupied"

                frappe.db.set_value(
                    "Accommodation Room",
                    room_name,
                    {
                        "current_occupancy": active,
                        "status": new_status,
                    },
                    update_modified=False,
                )
            except Exception:
                frappe.db.rollback()  # T-05: rollback before log_error to avoid aborted-transaction errors
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Occupancy sync failed for room {room_name}"[:140],
                )

        start += batch_size

    frappe.logger().info("weekly_occupancy_sync: room occupancy counters refreshed.")

    # --- Building pass ---
    # Guard: skip buildings with no rooms to avoid division by zero in
    # occupancy_percent calculation.
    start = 0
    while True:
        building_names = frappe.get_all(
            "Accommodation Building",
            pluck="name",
            limit_start=start,
            limit_page_length=batch_size,
        )
        if not building_names:
            break

        for building_name in building_names:
            try:
                total_rooms = frappe.db.count(
                    "Accommodation Room",
                    {"building": building_name},
                )
                if not total_rooms:
                    # Building has no rooms — skip to avoid division by zero.
                    continue

                active = frappe.db.count(
                    "Accommodation Assignment",
                    {"building": building_name, "docstatus": 1, "check_out_date": ["is", "not set"]},
                )
                total_capacity = (
                    frappe.db.get_value("Accommodation Building", building_name, "total_capacity") or 0
                )
                occupancy_pct = (active / total_capacity * 100) if total_capacity else 0.0
                frappe.db.set_value(
                    "Accommodation Building",
                    building_name,
                    {
                        "current_occupants": active,
                        "occupancy_percent": round(occupancy_pct, 2),
                    },
                    update_modified=False,
                )
            except Exception:
                frappe.db.rollback()  # T-05: rollback before log_error to avoid aborted-transaction errors
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Occupancy sync failed for building {building_name}"[:140],
                )

        start += batch_size

    frappe.logger().info("weekly_occupancy_sync: building occupancy counters refreshed.")


def weekly_safety_task_compliance_scan() -> None:
    """Scan for overdue Scheduled Task Instances and flag them as Overdue."""
    from frappe.utils import today, getdate

    today_date = getdate(today())
    logger = frappe.logger()

    total_overdue = 0

    # Paginate overdue instances at 500/batch
    start = 0
    batch_size = 500
    while True:
        overdue = frappe.get_all(
            "Scheduled Task Instance",
            filters={"docstatus": 0, "status": ["in", ["Open", "In Progress"]], "due_date": ["<", str(today_date)]},
            fields=["name", "due_date", "template"],
            limit_start=start,
            limit_page_length=batch_size,
        )
        if not overdue:
            break

        for inst in overdue:
            try:
                frappe.db.set_value("Scheduled Task Instance", inst.name, "status", "Overdue")
                _notify_operational(
                    "Scheduled Task Instance", inst.name,
                    f"Scheduled task {inst.name} ({inst.template}) is overdue (was due {inst.due_date}).",
                )
            except Exception:
                frappe.db.rollback()  # T-05: rollback before log_error to avoid aborted-transaction errors
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Safety compliance scan failed for {inst.name}"[:140],
                )

        total_overdue += len(overdue)
        start += batch_size

    if total_overdue:
        logger.warning(
            f"weekly_safety_task_compliance_scan: Marked {total_overdue} Scheduled Task Instances as Overdue."
        )
    else:
        logger.info("weekly_safety_task_compliance_scan: No overdue instances found.")


def daily_scheduled_task_instance_generator() -> None:
    """Generate Scheduled Task Instance records for active templates due today.

    Runs daily. For each active Scheduled Task Template, checks whether a
    Scheduled Task Instance already exists for the current period before creating.
    Phase 7 — requires Scheduled Task Template and Scheduled Task Instance DocTypes.
    """
    from frappe.utils import today, get_first_day, getdate

    today_str = today()
    today_date = getdate(today_str)
    logger = frappe.logger()

    # Paginate active templates at 500/batch
    start = 0
    batch_size = 500
    while True:
        templates = frappe.get_all(
            "Scheduled Task Template",
            filters={"is_active": 1},
            fields=["name", "template_name", "frequency", "building", "assigned_to"],
            limit_start=start,
            limit_page_length=batch_size,
        )
        if not templates:
            break

        for tmpl in templates:
            # Skip templates pointing at a building that no longer exists, so the
            # generator does not log a LinkValidationError on every run.
            if tmpl.building and not frappe.db.exists("Accommodation Building", tmpl.building):
                logger.warning(
                    "daily_scheduled_task_instance_generator: skipping template %s — building %s not found.",
                    tmpl.name,
                    tmpl.building,
                )
                continue

            freq = tmpl.frequency or "Monthly"
            if freq == "Daily":
                period_key = today_str
            elif freq == "Weekly":
                week_start = today_date - __import__("datetime").timedelta(days=today_date.weekday())
                period_key = str(week_start)
            elif freq == "Monthly":
                period_key = str(get_first_day(today_date))
            elif freq == "Quarterly":
                month = today_date.month
                quarter_start_month = ((month - 1) // 3) * 3 + 1
                period_key = str(today_date.replace(month=quarter_start_month, day=1))
            elif freq == "Annually":
                period_key = str(today_date.replace(month=1, day=1))
            else:
                period_key = today_str

            existing = frappe.db.exists(
                "Scheduled Task Instance",
                {"template": tmpl.name, "due_date": period_key, "docstatus": ["!=", 2]},
            )
            if existing:
                continue

            try:
                sti = frappe.get_doc({
                    "doctype": "Scheduled Task Instance",
                    "template": tmpl.name,
                    "due_date": period_key,
                    "assigned_to": tmpl.assigned_to,
                    "status": "Open",
                })
                sti.insert(ignore_permissions=True)
                logger.info(
                    "daily_scheduled_task_instance_generator: Created STI %s for template %s due %s.",
                    sti.name,
                    tmpl.name,
                    period_key,
                )
            except Exception as e:  # noqa: BLE001
                frappe.db.rollback()  # T-05: rollback before log_error to avoid aborted-transaction errors
                logger.error(
                    "daily_scheduled_task_instance_generator: Failed to create STI for template %s: %s",
                    tmpl.name,
                    e,
                )
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"STI generator failed for template {tmpl.name}"[:140],
                )

        start += batch_size


def monthly_rent_due_alert() -> None:
    """Alert on Rent Payment Schedule rows due this month.

    Manual-reminder only: logs every unpaid row due this month so Finance can
    process payment. Automatic Payment Entry creation was removed because it
    was a dead branch — paid_from / paid_to accounts were never configured, so
    the guard always skipped. Re-introduce automation only with explicit,
    configured accounts and an idempotency/reversal policy.
    """
    from frappe.utils import getdate, get_first_day, get_last_day, today

    today_date = getdate(today())
    month_start = get_first_day(today_date)
    month_end = get_last_day(today_date)
    logger = frappe.logger()

    # Paginate active leases at 500/batch
    start = 0
    batch_size = 500
    while True:
        leases = frappe.get_all(
            "Accommodation Lease",
            filters={"docstatus": 1, "status": "Active"},
            fields=["name", "building", "supplier", "rent_amount"],
            limit_start=start,
            limit_page_length=batch_size,
        )
        if not leases:
            break

        for lease in leases:
            try:  # T-04: isolate per-lease errors so one bad row does not abort the whole batch
                schedule_rows = frappe.get_all(
                    "Rent Payment Schedule",
                    filters={
                        "parent": lease.name,
                        "parenttype": "Accommodation Lease",
                        "status": "Unpaid",
                        "due_date": ["between", [str(month_start), str(month_end)]],
                    },
                    fields=["name", "due_date", "amount", "payment_entry"],
                )

                for row in schedule_rows:
                    # Idempotency: skip rows already linked to a Payment Entry.
                    if row.get("payment_entry"):
                        continue

                    # Manual-reminder only. Finance settles rent manually; this job
                    # only surfaces what is due. No Payment Entry is created here.
                    logger.warning(
                        "monthly_rent_due_alert: Lease %s (building %s) — SAR %.2f due %s "
                        "requires manual payment by Finance.",
                        lease.name,
                        lease.building,
                        row.amount,
                        row.due_date,
                    )
            except Exception:
                frappe.db.rollback()  # T-04: rollback before log_error to avoid aborted-transaction errors
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Rent due alert failed for lease {lease.name}"[:140],
                )
                continue

        start += batch_size
