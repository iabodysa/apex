"""Scheduled tasks for the Habitat module."""

from __future__ import annotations

import calendar

import frappe
from frappe import _


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


def _notify_role_system(role: str, subject: str, message: str | None = None) -> None:
    """Post an in-app (system) Notification Log of type Alert to every enabled user
    holding ``role``.

    Mirrors temporary_worker_engine._notify_hr: the in-desk alert the Wave-3 safety
    jobs raise for the Safety Officer / Operations Director. Best-effort — a failure
    rolls back and logs but never aborts the calling job. No recipients = no-op.
    """
    from frappe.utils.user import get_users_with_role

    body = message or subject
    try:
        for user in get_users_with_role(role) or []:
            frappe.get_doc({
                "doctype": "Notification Log",
                "for_user": user,
                "type": "Alert",
                "subject": subject[:140],
                "email_content": body,
            }).insert(ignore_permissions=True)  # audit-ok — scheduler-run system alert
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            message=frappe.get_traceback(),
            title=f"Safety system notify failed ({role})"[:140],
        )


def _notify_user_system(user: str | None, subject: str, message: str | None = None) -> None:
    """Post an in-app (system) Notification Log of type Alert to ONE specific user.

    Single-recipient sibling of _notify_role_system — used to reach the building's
    own responsible supervisor (not the whole role). Falsy/disabled user = no-op.
    """
    if not user or not frappe.db.get_value("User", user, "enabled"):
        return
    try:
        frappe.get_doc({
            "doctype": "Notification Log",
            "for_user": user,
            "type": "Alert",
            "subject": subject[:140],
            "email_content": message or subject,
        }).insert(ignore_permissions=True)  # audit-ok — scheduler-run system alert
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            message=frappe.get_traceback(),
            title=f"Safety user notify failed ({user})"[:140],
        )


def _raise_safety_alert(alert_type: str, severity: str, message: str, dedupe_token: str) -> str | None:
    """Insert an Operations Alert for a safety obligation breach (idempotent).

    Mirrors _raise_maintenance_alert: existence-guarded on
    ``(alert_type, status=Open, message LIKE %dedupe_token%, raised_on=today)`` so a
    daily job never spams a duplicate. ``alert_type``/``severity`` MUST be valid
    Operations Alert Select options (the DocType's option set is closed). Returns the
    new alert name, or None when a duplicate was skipped or the insert failed.
    """
    from frappe.utils import now_datetime, today

    today_str = today()
    try:
        if frappe.db.exists(
            "Operations Alert",
            {
                "alert_type": alert_type,
                "status": "Open",
                "message": ["like", f"%{dedupe_token}%"],
                "raised_on": ["between", [f"{today_str} 00:00:00", f"{today_str} 23:59:59"]],
            },
        ):
            return None
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            message=frappe.get_traceback(),
            title=f"Safety alert dedupe check failed ({dedupe_token})"[:140],
        )
        return None

    try:
        alert = frappe.get_doc(
            {
                "doctype": "Operations Alert",
                "alert_type": alert_type,
                "severity": severity,
                "status": "Open",
                "raised_on": now_datetime(),
                "message": message[:2000],
            }
        )
        alert.insert(ignore_permissions=True)  # audit-ok — scheduler-run safety escalation
        return alert.name
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            message=frappe.get_traceback(),
            title=f"Safety alert insert failed ({dedupe_token})"[:140],
        )
        return None


def _raise_consumable_alert(message: str, dedupe_token: str) -> str | None:
    """Raise a Consumable Expired Operations Alert (idempotent), via the shared helper.

    Existence-guarded on ``(alert_type=Consumable Expired, status=Open,
    message LIKE %dedupe_token%, raised_on=today)`` so the daily job never spams a
    duplicate for the same held position. The insert itself goes through
    ``insert_operations_alert`` (the one place that writes the record). Returns the
    new alert name, or None when a duplicate was skipped or the insert failed.
    """
    from frappe.utils import today

    from apex_habitat.apex_core.utils.operations_alert import insert_operations_alert

    today_str = today()
    try:
        if frappe.db.exists(
            "Operations Alert",
            {
                "alert_type": "Consumable Expired",
                "status": "Open",
                "message": ["like", f"%{dedupe_token}%"],
                "raised_on": ["between", [f"{today_str} 00:00:00", f"{today_str} 23:59:59"]],
            },
        ):
            return None
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            message=frappe.get_traceback(),
            title=f"Consumable alert dedupe check failed ({dedupe_token})"[:140],
        )
        return None

    return insert_operations_alert("Consumable Expired", "Warning", message)


def consumable_custody_expiry_watch() -> None:
    """Flag held custody consumables past their per-article lifespan.

    A held position is a net-positive (item, employee) balance in the
    Accommodation Stock Ledger; its age is months since the EARLIEST still-held
    issue posting. Articles carry their own ``consumable_lifespan_months`` (0 = no
    expiry) so linens/mattresses age out without hardcoding a flat year. One
    bounded grouped query; the alert is one Warning per over-age position per day.
    """
    from frappe.utils import getdate, today

    rows = frappe.db.sql(
        """
        SELECT sle.item AS article, sle.employee AS employee,
               SUM(sle.qty) AS net_qty, MIN(sle.posting_date) AS first_held,
               art.article_name AS article_name,
               art.consumable_lifespan_months AS lifespan
        FROM `tabAccommodation Stock Ledger` sle
        INNER JOIN `tabCustody Article` art ON art.name = sle.item
        WHERE sle.is_cancelled = 0
          AND sle.item_type = 'Custody Article'
          AND sle.employee IS NOT NULL AND sle.employee != ''
          AND art.consumable_lifespan_months > 0
        GROUP BY sle.item, sle.employee
        HAVING net_qty > 0
        """,
        as_dict=True,
    )

    today_date = getdate(today())
    # Bulk-prefetch the holders' employee names in one query keyed on the grouped
    # rows' employee ids, instead of one get_value per held position (N+1).
    emp_ids = {r.employee for r in rows if r.employee}
    emp_names = (
        {
            e["name"]: e["employee_name"]
            for e in frappe.get_all(
                "Employee", filters={"name": ["in", list(emp_ids)]}, fields=["name", "employee_name"]
            )
        }
        if emp_ids
        else {}
    )
    for r in rows:
        if not r.first_held:
            continue
        held = getdate(r.first_held)
        age_months = (today_date.year - held.year) * 12 + (today_date.month - held.month)
        if today_date.day < held.day:
            age_months -= 1
        if age_months < int(r.lifespan or 0):
            continue
        emp_name = emp_names.get(r.employee) or r.employee
        token = f"{r.employee}:{r.article}"
        # Token embedded so the message-LIKE dedupe in _raise_consumable_alert matches.
        message = _(
            "Consumable {0} held by {1} since {2} is {3} month(s) old, past its {4}-month lifespan."
        ).format(
            r.article_name or r.article, emp_name, r.first_held, age_months, int(r.lifespan or 0)
        ) + f" [{token}]"
        _raise_consumable_alert(message, dedupe_token=token)


def daily_accommodation_cost_allocation() -> None:
    """Scheduler entry — fan daily accommodation cost allocation out PER BUILDING
    to the native ``long`` queue, so the scheduler worker is never blocked on a
    large dataset and buildings allocate in parallel. Buildings are discovered
    once; one idempotent job is enqueued per building (safe to retry).
    """
    from frappe.utils import today

    posting_date = today()
    buildings = frappe.get_all(
        "Accommodation Assignment",
        filters={
            "docstatus": 1,
            "check_out_date": ["is", "not set"],
            "building": ["is", "set"],
        },
        pluck="building",
        distinct=True,
    )
    for building in buildings:
        frappe.enqueue(
            "apex_habitat.habitat.tasks.allocate_building_accommodation_cost",
            queue="long",
            timeout=3600,
            job_id=f"acc-cost-alloc::{building}::{posting_date}",
            deduplicate=True,
            enqueue_after_commit=True,
            building=building,
            posting_date=posting_date,
        )


def allocate_building_accommodation_cost(building, posting_date=None) -> None:
    """Allocate ONE building's daily accommodation costs to the Accommodation
    Ledger. Enqueued per building by ``daily_accommodation_cost_allocation`` (also
    directly callable). Idempotent — an existing ledger row for the
    (employee, posting_date, assignment, building, ledger_type) key is skipped, so
    retries and overlapping runs never duplicate.
    """
    from frappe.utils import today, flt

    posting_date = posting_date or today()
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

    # [#3r52d7]
    if not frappe.db.exists("Accommodation Building", building):
        logger.warning(
            f"allocate_building_accommodation_cost: Building {building} not found. Skipping."
        )
        return
    building_doc = frappe.get_doc("Accommodation Building", building)
    # [#el5lmg]
    from apex_habitat.habitat.doctype.accommodation_building.accommodation_building import apply_active_lease
    apply_active_lease(building_doc)
    capacity = flt(building_doc.total_capacity)
    if capacity <= 0:
        logger.warning(
            f"allocate_building_accommodation_cost: Building {building} has invalid capacity {capacity}. Skipping."
        )
        return

    start = 0
    batch_size = 500
    while True:
        active_assignments = frappe.get_all(
            "Accommodation Assignment",
            filters={
                "docstatus": 1,
                "check_out_date": ["is", "not set"],
                "building": building,
            },
            fields=["name", "employee", "project", "cost_center", "billed_to_supplier"],
            limit_start=start,
            limit_page_length=batch_size,
        )
        if not active_assignments:
            break

        for asgn in active_assignments:
            if not asgn.employee:
                logger.warning(
                    f"allocate_building_accommodation_cost: Assignment {asgn.name} has no employee specified. Skipping."
                )
                continue

            for ledger_type, building_field in cost_type_mapping.items():
                annual_cost = flt(building_doc.get(building_field))
                if annual_cost <= 0:
                    continue

                # [#pqghnl]
                daily_cost = flt(annual_cost / days_in_year, 5)
                daily_share = flt(daily_cost / capacity, 5)

                # [#4g0jys]
                exists = frappe.db.exists(
                    "Accommodation Ledger",
                    {
                        "employee": asgn.employee,
                        "posting_date": posting_date,
                        "assignment": asgn.name,
                        "building": building,
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
                        "building": building,
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
                    ledger_entry.insert(ignore_permissions=True)  # audit-ok — scheduler-run cost allocation, no user session
                except frappe.exceptions.DuplicateEntryError:
                    frappe.db.rollback()  # [#g4zbzv]
                except Exception as e:
                    frappe.db.rollback()  # [#9hso8i]
                    logger.error(
                        f"allocate_building_accommodation_cost: Failed to insert ledger row for assignment {asgn.name}, cost {ledger_type}: {e}"
                    )
                    frappe.log_error(
                        message=frappe.get_traceback(),
                        title=f"Cost allocation: ledger insert failed ({asgn.name}/{ledger_type})"[:140],
                    )

        start += batch_size


def backdate_assignment_cost(assignment_name, from_date, to_date=None) -> int:
    """Post the missed daily Operational-Memo accommodation-cost rows for ONE
    assignment over [from_date, to_date] (default to_date = today).

    Used when a Temporary Worker is linked to a real Employee (Batch 5): the days he
    was housed on a passport were skipped by the daily allocator (it skips an
    assignment with no employee), so they are back-dated to the now-linked Employee.
    Mirrors daily_accommodation_cost_allocation's per-assignment-per-date algorithm;
    idempotent (existence-guarded) and per-row error-isolated. Returns days processed.
    """
    from frappe.utils import today, getdate, add_days, flt

    to_date = to_date or today()
    asgn = frappe.db.get_value(
        "Accommodation Assignment",
        assignment_name,
        ["name", "employee", "building", "project", "cost_center", "billed_to_supplier"],
        as_dict=True,
    )
    if not asgn or not asgn.employee or not asgn.building:
        return 0
    try:
        building = frappe.get_doc("Accommodation Building", asgn.building)
    except frappe.DoesNotExistError:
        return 0
    from apex_habitat.habitat.doctype.accommodation_building.accommodation_building import apply_active_lease
    apply_active_lease(building)  # [#ijk615]
    capacity = flt(building.total_capacity)
    if capacity <= 0:
        return 0

    cost_type_mapping = {
        "Rent": "annual_rent_sar",
        "Electricity": "annual_electricity_sar",
        "Water": "annual_water_sar",
        "Cleaning Staff Salary": "annual_cleaning_staff_sar",
        "Supervisor Salary": "annual_supervision_sar",
        "Other": "annual_other_expenses_sar",
    }

    d = getdate(from_date)
    end = getdate(to_date)
    days = 0
    while d <= end:
        posting_date = str(d)
        days_in_year = 366 if calendar.isleap(d.year) else 365
        for ledger_type, building_field in cost_type_mapping.items():
            annual_cost = flt(building.get(building_field))
            if annual_cost <= 0:
                continue
            daily_share = flt(flt(annual_cost / days_in_year, 5) / capacity, 5)
            if frappe.db.exists(
                "Accommodation Ledger",
                {
                    "employee": asgn.employee,
                    "posting_date": posting_date,
                    "assignment": asgn.name,
                    "building": asgn.building,
                    "ledger_type": ledger_type,
                },
            ):
                continue
            try:
                frappe.get_doc({
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
                }).insert(ignore_permissions=True)  # audit-ok — back-dated cost memo
            except Exception:
                frappe.db.rollback()
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Backdate cost insert failed ({asgn.name}/{ledger_type})"[:140],
                )
        days += 1
        d = getdate(add_days(d, 1))
    return days


def daily_building_license_expiry_check() -> None:
    """Warn when Building License documents are approaching or past expiry.

    Updates status of Building License records:
    - Expired: if today is past or equal to expiry_date.
    - Expiring Soon: if today is within renewal_lead_days (default 60) of expiry_date.
    """
    from frappe.utils import today, date_diff

    today_str = today()
    logger = frappe.logger()

    # [#bz69zh]
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

        default_lead = frappe.db.get_single_value("Habitat Settings", "license_expiry_days_before") or 60
        for lic in licenses:
            expiry_date = lic.expiry_date
            if not expiry_date:
                continue

            try:
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
                frappe.db.rollback()  # [#7kjob3]
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"License expiry check failed for {lic.name}"[:140],
                )

        start += batch_size


def _raise_maintenance_alert(
    req_name: str,
    priority: str,
    elapsed_hours: float,
    threshold_hours: int,
    issue_type: str,
    status: str,
) -> None:
    """Insert an Operations Alert for an overdue Maintenance Request (idempotent).

    Mirrors the Salis ``_raise_alert`` pattern: existence-guarded so one Open
    alert per (Maintenance Request, day) is never duplicated across runs. Both
    the insert and the optional timeline comment are individually guarded so a
    failure rolls back and logs but never aborts the calling loop.
    """
    from frappe.utils import now_datetime, today

    alert_type = "Maintenance Overdue"  # [#ihzt5o]
    severity = "Critical" if priority == "Critical" else "Warning"
    message = (
        f"open_maintenance_escalation: Maintenance Request {req_name} "
        f"({issue_type}, status: {status}) is overdue. "
        f"Priority: {priority}, hours open: {elapsed_hours:.1f} "
        f"(threshold: {threshold_hours} hours)."
    )[:2000]

    # [#glisou]
    try:
        today_str = today()
        if frappe.db.exists(
            "Operations Alert",
            {
                "alert_type": alert_type,
                "status": "Open",
                "message": ["like", f"%{req_name}%"],
                "raised_on": ["between", [f"{today_str} 00:00:00", f"{today_str} 23:59:59"]],
            },
        ):
            return
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            message=frappe.get_traceback(),
            title=f"Maintenance alert dedupe check failed ({req_name})"[:140],
        )
        return

    # [#rx9vmh]
    try:
        frappe.get_doc(
            {
                "doctype": "Operations Alert",
                "alert_type": alert_type,
                "severity": severity,
                "status": "Open",
                "raised_on": now_datetime(),
                "message": message,
            }
        ).insert(ignore_permissions=True)  # audit-ok — scheduler-run escalation, no user session
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            message=frappe.get_traceback(),
            title=f"Maintenance alert insert failed ({req_name})"[:140],
        )
        return

    # [#q02x8v]
    try:
        frappe.get_doc("Maintenance Request", req_name).add_comment("Comment", message)
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            message=frappe.get_traceback(),
            title=f"Maintenance alert comment failed for {req_name}"[:140],
        )


def open_maintenance_escalation() -> None:
    """Escalate overdue open Maintenance Requests.

    Checks open requests (docstatus != 2, status in ('Open', 'Assigned', 'In Progress', 'Reopened'))
    and logs escalations based on priority and elapsed time.
    Also inserts an Operations Alert for each overdue ticket (idempotent — one
    Open alert per request per day; see _raise_maintenance_alert).
    """
    from frappe.utils import now_datetime, get_datetime

    now = now_datetime()
    logger = frappe.logger()

    # [#6x8ro4]
    thresholds = {
        "Critical": 24,
        "High": 72,
        "Medium": 168,
        "Low": 336
    }

    # [#bz0n3e]
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
            try:  # [#jrhqtd]
                priority = req.priority or "Medium"
                threshold_hours = thresholds.get(priority, 168)

                creation_dt = get_datetime(req.creation)
                elapsed_hours = (now - creation_dt).total_seconds() / 3600.0

                if elapsed_hours > threshold_hours:
                    logger.warning(
                        f"Maintenance Request {req.name} ({req.issue_type}, status: {req.status}) "
                        f"is overdue! Priority: {priority}, hours open: {elapsed_hours:.1f} (threshold: {threshold_hours} hours)."
                    )
                    _raise_maintenance_alert(
                        req_name=req.name,
                        priority=priority,
                        elapsed_hours=elapsed_hours,
                        threshold_hours=threshold_hours,
                        issue_type=req.issue_type or "",
                        status=req.status or "",
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
    """Alert on leases expiring within the configured lead days.

    Queries Accommodation Lease (submitted, status=Active) directly —
    the authoritative source for lease dates.
    Sets lease status = Expired when lease_end_date has passed.
    """
    from frappe.utils import date_diff, today

    today_str = today()
    logger = frappe.logger()
    lease_lead = frappe.db.get_single_value("Habitat Settings", "lease_expiry_days_before") or 90

    start = 0
    batch_size = 500
    while True:
        leases = frappe.get_all(
            "Accommodation Lease",
            filters={"docstatus": 1, "status": "Active", "lease_end_date": ["is", "set"]},
            fields=["name", "building", "lease_end_date"],
            limit_start=start,
            limit_page_length=batch_size,
        )
        if not leases:
            break

        for lease in leases:
            try:
                days = date_diff(lease.lease_end_date, today_str)
                if days < 0:
                    frappe.db.set_value("Accommodation Lease", lease.name, "status", "Expired")
                    msg = (
                        f"lease_expiry_watchlist: lease {lease.name} "
                        f"(building {lease.building}) expired {abs(days)} days ago."
                    )
                    logger.warning(msg)
                    _notify_operational("Accommodation Lease", lease.name, msg)
                elif 0 <= days <= lease_lead:
                    msg = (
                        f"lease_expiry_watchlist: lease {lease.name} "
                        f"(building {lease.building}) expires in {days} days ({lease.lease_end_date})."
                    )
                    logger.warning(msg)
                    _notify_operational("Accommodation Lease", lease.name, msg)
            except Exception:
                frappe.db.rollback()
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Lease expiry watchlist failed for {lease.name}"[:140],
                )

        start += batch_size


def temporary_stay_checkout_watchlist() -> None:
    """Flag temporary stays whose expected check-out date has arrived or passed
    while the worker is still checked in.

    Active stay = submitted Accommodation Assignment with no check_out_date. For
    each temporary one, compare today to expected_checkout_date; post a timeline
    comment (gated by Enable Operational Notifications) on overdue stays, and on
    those due within the Temporary Stay Lead Days. Mirrors lease_expiry_watchlist:
    paginated 500/batch, per-row error isolation. Sets no state field.
    """
    from frappe.utils import date_diff, today

    today_str = today()
    logger = frappe.logger()
    start = 0
    batch_size = 500
    while True:
        stays = frappe.get_all(
            "Accommodation Assignment",
            filters={
                "stay_type": "Temporary",
                "docstatus": 1,
                "check_out_date": ["is", "not set"],
                "expected_checkout_date": ["is", "set"],
            },
            fields=["name", "employee", "employee_name", "expected_checkout_date"],
            limit_start=start,
            limit_page_length=batch_size,
        )
        if not stays:
            break

        lead = frappe.db.get_single_value("Habitat Settings", "temporary_stay_days_before") or 2
        for s in stays:
            try:
                days = date_diff(s.expected_checkout_date, today_str)
                worker = s.employee_name or s.employee
                if days < 0:
                    msg = (f"temporary_stay_checkout_watchlist: {worker} is overdue — expected check-out was "
                           f"{s.expected_checkout_date} ({abs(days)} days ago) and the worker is still checked in.")
                    logger.warning(msg)
                    _notify_operational("Accommodation Assignment", s.name, msg)
                elif 0 <= days <= lead:
                    msg = (f"temporary_stay_checkout_watchlist: {worker}'s temporary stay ends on "
                           f"{s.expected_checkout_date} (in {days} days). Please arrange check-out.")
                    logger.warning(msg)
                    _notify_operational("Accommodation Assignment", s.name, msg)
            except Exception:
                frappe.db.rollback()
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Temporary stay watchlist failed for {s.name}"[:140],
                )

        start += batch_size


def idle_resident_aging() -> None:
    """Accrue days-idle and the estimated accommodation cost bleed for every open
    Idle Resident Report.

    days_idle = today - reported_on. Cost bleed = sum of the per-resident daily
    share already posted to the Accommodation Ledger (Operational Memo) for the
    linked assignment over the idle window — no GL, reuses existing memo data.
    Paginated 500/batch with per-row error isolation; posts a timeline note every
    7 idle days when operational notifications are enabled.
    """
    from frappe.utils import date_diff, flt, getdate, today

    today_str = today()
    start = 0
    batch_size = 500
    while True:
        reports = frappe.get_all(
            "Idle Resident Report",
            filters={"status": ["in", ["Open", "Acknowledged"]]},
            fields=["name", "reported_on", "assignment", "employee_name", "employee"],
            limit_start=start,
            limit_page_length=batch_size,
        )
        if not reports:
            break

        # Bulk-prefetch every ledger memo (assignment, posting_date <= today) for the
        # batch's assignments in one query, grouped by assignment, instead of one
        # get_all per report (N+1). The per-report reported_on..today window is then
        # applied in memory below, so each report's cost bleed is unchanged.
        asgn_ids = {r.assignment for r in reports if r.assignment and r.reported_on}
        ledger_by_assignment: dict = {}
        if asgn_ids:
            for x in frappe.get_all(
                "Accommodation Ledger",
                filters={"assignment": ["in", list(asgn_ids)], "posting_date": ["<=", today_str]},
                fields=["assignment", "posting_date", "employee_daily_share"],
            ):
                ledger_by_assignment.setdefault(x.assignment, []).append(x)

        for r in reports:
            try:
                days = date_diff(today_str, r.reported_on) if r.reported_on else 0
                cost = 0.0
                if r.assignment and r.reported_on:
                    reported_date = getdate(r.reported_on)
                    cost = flt(
                        sum(
                            flt(x.employee_daily_share)
                            for x in ledger_by_assignment.get(r.assignment, [])
                            if getdate(x.posting_date) >= reported_date
                        )
                    )
                frappe.db.set_value(
                    "Idle Resident Report", r.name,
                    {"days_idle": days, "estimated_accommodation_cost_bleed_sar": cost},
                    update_modified=False,
                )
                if days and days % 7 == 0:
                    worker = r.employee_name or r.employee
                    _notify_operational(
                        "Idle Resident Report", r.name,
                        f"idle_resident_aging: {worker} has now been a cost bleed for {days} days "
                        f"(estimated accommodation cost {cost} SAR).",
                    )
            except Exception:
                frappe.db.rollback()
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Idle resident aging failed for {r.name}"[:140],
                )

        start += batch_size


def weekly_occupancy_sync() -> None:
    """Recalculate occupancy counters on all Accommodation Rooms and Buildings.

    Runs a full reconciliation pass to correct any counter drift caused by
    out-of-band data changes.
    """
    batch_size = 500

    # [#d7yd9d]
    active_by_room = {
        r["room"]: int(r["n"] or 0)
        for r in frappe.db.sql(
            """
            SELECT room, COUNT(*) AS n
            FROM `tabAccommodation Assignment`
            WHERE docstatus = 1
              AND (check_out_date IS NULL OR check_out_date = '')
              AND room IS NOT NULL
            GROUP BY room
            """,
            as_dict=True,
        )
    }

    start = 0
    while True:
        rooms = frappe.get_all(
            "Accommodation Room",
            fields=["name", "bed_capacity"],
            limit_start=start,
            limit_page_length=batch_size,
        )
        if not rooms:
            break

        for room in rooms:
            try:
                active = active_by_room.get(room.name, 0)
                capacity = room.bed_capacity or 0
                if active <= 0:
                    new_status = "Available"
                elif capacity and active >= capacity:
                    new_status = "Full"
                else:
                    new_status = "Partially Occupied"

                frappe.db.set_value(
                    "Accommodation Room",
                    room.name,
                    {
                        "current_occupancy": active,
                        "status": new_status,
                    },
                    update_modified=False,
                )
            except Exception:
                frappe.db.rollback()  # [#7kjob3]
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Occupancy sync failed for room {room.name}"[:140],
                )

        start += batch_size

    frappe.logger().info("weekly_occupancy_sync: room occupancy counters refreshed.")

    # [#qm5tz5]
    rooms_per_building = {
        r["building"]: int(r["n"] or 0)
        for r in frappe.db.sql(
            """
            SELECT building, COUNT(*) AS n
            FROM `tabAccommodation Room`
            WHERE building IS NOT NULL
            GROUP BY building
            """,
            as_dict=True,
        )
    }
    active_by_building = {
        r["building"]: int(r["n"] or 0)
        for r in frappe.db.sql(
            """
            SELECT building, COUNT(*) AS n
            FROM `tabAccommodation Assignment`
            WHERE docstatus = 1
              AND (check_out_date IS NULL OR check_out_date = '')
              AND building IS NOT NULL
            GROUP BY building
            """,
            as_dict=True,
        )
    }

    start = 0
    while True:
        buildings = frappe.get_all(
            "Accommodation Building",
            fields=["name", "total_capacity"],
            limit_start=start,
            limit_page_length=batch_size,
        )
        if not buildings:
            break

        for building in buildings:
            try:
                total_rooms = rooms_per_building.get(building.name, 0)
                if not total_rooms:
                    # [#qtpe2y]
                    continue

                active = active_by_building.get(building.name, 0)
                total_capacity = building.total_capacity or 0
                occupancy_pct = (active / total_capacity * 100) if total_capacity else 0.0
                frappe.db.set_value(
                    "Accommodation Building",
                    building.name,
                    {
                        "current_occupants": active,
                        "occupancy_percent": round(occupancy_pct, 2),
                    },
                    update_modified=False,
                )
            except Exception:
                frappe.db.rollback()  # [#7kjob3]
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Occupancy sync failed for building {building.name}"[:140],
                )

        start += batch_size

    frappe.logger().info("weekly_occupancy_sync: building occupancy counters refreshed.")


def daily_occupancy_snapshot() -> None:
    """Write a daily point-in-time occupancy row per building to the read-only
    Accommodation Occupancy Snapshot engine, so occupancy history/trends survive
    (the live occupancy_percent field is overwritten and keeps no history).

    The per-building inputs (already-snapshotted set, room counts by status,
    active occupants, capacity, cost-per-capacity) are pre-aggregated once via a
    few grouped queries and looked up in memory, instead of issuing ~7
    ``count``/``exists``/``get_value`` calls per building (N+1). Behaviour and the
    one-row-per-building-per-day idempotency guard are preserved."""
    from frappe.utils import today

    snapshot_date = today()
    year = int(snapshot_date[:4])
    days_in_year = 366 if calendar.isleap(year) else 365

    # [#tt1y1j]
    already = {
        r["building"]
        for r in frappe.get_all(
            "Accommodation Occupancy Snapshot",
            filters={"snapshot_date": snapshot_date},
            fields=["building"],
        )
        if r["building"]
    }

    # [#90367k]
    rooms_by_building: dict = {}
    for r in frappe.db.sql(
        """
        SELECT building, status, COUNT(*) AS n
        FROM `tabAccommodation Room`
        WHERE building IS NOT NULL
        GROUP BY building, status
        """,
        as_dict=True,
    ):
        bucket = rooms_by_building.setdefault(r["building"], {"_total": 0})
        bucket[r["status"]] = int(r["n"] or 0)
        bucket["_total"] += int(r["n"] or 0)

    # [#6kydth]
    active_by_building = {
        r["building"]: int(r["n"] or 0)
        for r in frappe.db.sql(
            """
            SELECT building, COUNT(*) AS n
            FROM `tabAccommodation Assignment`
            WHERE docstatus = 1
              AND (check_out_date IS NULL OR check_out_date = '')
              AND building IS NOT NULL
            GROUP BY building
            """,
            as_dict=True,
        )
    }

    # [#im8xs8]
    building_meta = {
        b["name"]: b
        for b in frappe.get_all(
            "Accommodation Building",
            fields=["name", "total_capacity", "annual_cost_per_capacity_sar"],
        )
    }

    start = 0
    batch_size = 500
    while True:
        building_names = frappe.get_all(
            "Accommodation Building", pluck="name",
            limit_start=start, limit_page_length=batch_size,
        )
        if not building_names:
            break
        for building_name in building_names:
            try:
                if building_name in already:
                    continue
                room_bucket = rooms_by_building.get(building_name)
                total_rooms = room_bucket["_total"] if room_bucket else 0
                if not total_rooms:
                    continue
                active = active_by_building.get(building_name, 0)
                meta = building_meta.get(building_name) or {}
                total_capacity = meta.get("total_capacity") or 0
                occ_pct = round(active / total_capacity * 100, 2) if total_capacity else 0.0
                available_capacity = max(total_capacity - active, 0)

                annual_cost_per_capacity = meta.get("annual_cost_per_capacity_sar") or 0.0
                cost_bleeding = round(available_capacity * (annual_cost_per_capacity / days_in_year), 2)

                frappe.get_doc({
                    "doctype": "Accommodation Occupancy Snapshot",
                    "snapshot_date": snapshot_date,
                    "building": building_name,
                    "active_occupants": active,
                    "total_capacity": total_capacity,
                    "occupancy_percent": occ_pct,
                    "available_capacity": available_capacity,
                    "cost_bleeding": cost_bleeding,
                    "full_rooms": room_bucket.get("Full", 0),
                    "partial_rooms": room_bucket.get("Partially Occupied", 0),
                    "available_rooms": room_bucket.get("Available", 0),
                }).insert(ignore_permissions=True)  # audit-ok
            except Exception:
                frappe.db.rollback()
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Occupancy snapshot failed for building {building_name}"[:140],
                )
        start += batch_size
    frappe.logger().info("daily_occupancy_snapshot: snapshots written.")


def _instance_priority(template: str | None) -> str:
    """Resolve a Scheduled Task Instance's effective priority via its template's
    linked Safety Task Catalog task. Returns "" when no priority can be derived."""
    if not template:
        return ""
    catalog = frappe.db.get_value("Scheduled Task Template", template, "safety_task_catalog")
    if not catalog:
        return ""
    return frappe.db.get_value("Safety Task Catalog", catalog, "priority") or ""


def daily_safety_task_compliance_scan() -> None:
    """Daily — flag overdue Scheduled Task Instances Overdue, escalate the urgent ones,
    and flag active buildings with no safety round at all in the recent window.

    An instance counts as overdue once today is past its due_date plus the configured
    ``safety_overdue_grace_days`` (read as ``value or 0`` — a new Int on the Habitat
    Settings Single may store 0). On flipping an instance to Overdue, the effective
    priority is resolved through its template's Safety Task Catalog task: a High or
    Critical task additionally raises an idempotent Operations Alert AND posts a system
    Notification to the Safety Officer, so urgent safety lapses surface immediately.

    Second pass: every ACTIVE Accommodation Building (``status == "Active"``) with ZERO
    submitted Safety Rounds of ANY cadence dated within the trailing
    ``ZERO_ROUNDS_WINDOW_DAYS`` raises an idempotent Operations Alert, notifies the
    Safety Officer, posts the reminder to the building timeline, and alerts the
    building's own Responsible Facility Supervisor. This is broader than
    ``weekly_safety_coverage_gate`` (which only
    checks for a *Weekly*-cadence round in the current ISO week): it catches buildings
    with no safety activity whatsoever. The alert carries a ``zero-rounds::<building>``
    dedupe token so daily reruns stay idempotent.

    Per-row error isolation; paginated 500/batch.
    """
    from frappe.utils import today, getdate, add_days

    grace_days = frappe.db.get_single_value("Habitat Settings", "safety_overdue_grace_days") or 0
    cutoff = str(getdate(add_days(today(), -int(grace_days))))
    logger = frappe.logger()

    total_overdue = 0
    escalated = 0

    # [#4qriyf]
    start = 0
    batch_size = 500
    while True:
        overdue = frappe.get_all(
            "Scheduled Task Instance",
            filters={"docstatus": 0, "status": ["in", ["Open", "In Progress"]], "due_date": ["<", cutoff]},
            fields=["name", "due_date", "template", "building"],
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
                # [#wave3-prio] High/Critical -> Operations Alert + Safety Officer system alert.
                priority = _instance_priority(inst.template)
                if priority in ("High", "Critical"):
                    msg = (
                        f"daily_safety_task_compliance_scan: {priority}-priority scheduled task "
                        f"{inst.name} ({inst.template}) is overdue (was due {inst.due_date})."
                    )
                    _raise_safety_alert(
                        alert_type="Maintenance Overdue",
                        severity="Critical" if priority == "Critical" else "Warning",
                        message=msg,
                        dedupe_token=inst.name,
                    )
                    _notify_role_system(
                        "Safety Officer",
                        subject=f"Overdue {priority} safety task: {inst.name}",
                        message=msg,
                    )
                    escalated += 1
            except Exception:
                frappe.db.rollback()  # [#7kjob3]
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Safety compliance scan failed for {inst.name}"[:140],
                )

        total_overdue += len(overdue)
        start += batch_size

    if total_overdue:
        logger.warning(
            f"daily_safety_task_compliance_scan: Marked {total_overdue} Scheduled Task Instances "
            f"as Overdue ({escalated} High/Critical escalated)."
        )
    else:
        logger.info("daily_safety_task_compliance_scan: No overdue instances found.")

    # Zero-rounds pass: active buildings with NO safety round of any cadence recently.
    ZERO_ROUNDS_WINDOW_DAYS = 7
    window_start = str(getdate(add_days(today(), -ZERO_ROUNDS_WINDOW_DAYS)))
    no_rounds = 0

    start = 0
    while True:
        buildings = frappe.get_all(
            "Accommodation Building",
            filters={"status": "Active"},
            fields=["name", "building_name", "responsible_facility_supervisor"],
            limit_start=start,
            limit_page_length=batch_size,
        )
        if not buildings:
            break

        for b in buildings:
            try:
                has_round = frappe.db.exists(
                    "Safety Round",
                    {
                        "docstatus": 1,
                        "building": b.name,
                        "round_date": [">=", window_start],
                    },
                )
                if has_round:
                    continue
                label = b.building_name or b.name
                token = f"zero-rounds::{b.name}"
                # Token embedded so _raise_safety_alert's message-LIKE dedupe matches.
                msg = (
                    f"daily_safety_task_compliance_scan [{token}]: building {label} has no "
                    f"submitted Safety Round in the last {ZERO_ROUNDS_WINDOW_DAYS} days."
                )
                _raise_safety_alert(
                    alert_type="Supervisor Delay",
                    severity="Warning",
                    message=msg,
                    dedupe_token=token,
                )
                _notify_role_system(
                    "Safety Officer",
                    subject=f"No recent safety round: {label}",
                    message=msg,
                )
                # Reach the building's own responsible supervisor: timeline note +
                # a direct system alert (the role-wide ping above may not be them).
                _notify_operational("Accommodation Building", b.name, msg)
                _notify_user_system(
                    b.responsible_facility_supervisor,
                    subject=f"No recent safety round: {label}",
                    message=msg,
                )
                no_rounds += 1
            except Exception:
                frappe.db.rollback()  # [#7kjob3]
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Zero-rounds scan failed for {b.name}"[:140],
                )

        start += batch_size

    logger.info(
        f"daily_safety_task_compliance_scan: {no_rounds} active building(s) with no recent safety round."
    )


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

    # [#78c2rg]
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
            # [#hs4wc0]
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
                sti.insert(ignore_permissions=True)  # audit-ok — scheduler-run task generation, no user session
                logger.info(
                    "daily_scheduled_task_instance_generator: Created STI %s for template %s due %s.",
                    sti.name,
                    tmpl.name,
                    period_key,
                )
            except Exception as e:  # noqa: BLE001
                frappe.db.rollback()  # [#7kjob3]
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


def weekly_safety_coverage_gate() -> None:
    """Weekly — every ACTIVE building must be covered by a submitted Weekly Safety
    Round this week; flag the buildings that are not.

    Gated by Habitat Settings ``require_weekly_all_building_coverage`` (read as
    ``value if not None else 1`` — the gate defaults ON, but a falsy stored value on
    the Single turns it off, per the Single new-field caveat). When the gate is ON,
    each ACTIVE Accommodation Building (``status == "Active"``) with no submitted
    Weekly-cadence Safety Round dated within the current ISO week raises an idempotent
    Operations Alert and posts a system Notification to the Safety Officer. Per-row
    error isolation.
    """
    from frappe.utils import today, getdate, add_days

    require_coverage = frappe.db.get_single_value(
        "Habitat Settings", "require_weekly_all_building_coverage"
    )
    require_coverage = require_coverage if require_coverage is not None else 1
    if not require_coverage:
        frappe.logger().info("weekly_safety_coverage_gate: coverage gate disabled — skipping.")
        return

    today_date = getdate(today())
    week_start = add_days(today_date, -today_date.weekday())  # Monday
    week_end = add_days(week_start, 6)  # Sunday
    logger = frappe.logger()
    uncovered = 0

    start = 0
    batch_size = 500
    while True:
        buildings = frappe.get_all(
            "Accommodation Building",
            filters={"status": "Active"},
            fields=["name", "building_name"],
            limit_start=start,
            limit_page_length=batch_size,
        )
        if not buildings:
            break

        for b in buildings:
            try:
                covered = frappe.db.exists(
                    "Safety Round",
                    {
                        "docstatus": 1,
                        "cadence": "Weekly",
                        "building": b.name,
                        "round_date": ["between", [str(week_start), str(week_end)]],
                    },
                )
                if covered:
                    continue
                label = b.building_name or b.name
                msg = (
                    f"weekly_safety_coverage_gate: building {label} ({b.name}) has no submitted "
                    f"Weekly Safety Round for the week of {week_start} — {week_end}."
                )
                logger.warning(msg)
                _raise_safety_alert(
                    alert_type="Supervisor Delay",
                    severity="Warning",
                    message=msg,
                    dedupe_token=b.name,
                )
                _notify_role_system(
                    "Safety Officer",
                    subject=f"Building not covered by a weekly safety round: {label}",
                    message=msg,
                )
                uncovered += 1
            except Exception:
                frappe.db.rollback()
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Safety coverage gate failed for {b.name}"[:140],
                )

        start += batch_size

    logger.info(f"weekly_safety_coverage_gate: {uncovered} active building(s) uncovered this week.")


def audit_remediation_deadline_watch() -> None:
    """Daily — flag submitted Client Audit Remediation Plans whose deadline has passed.

    A submitted plan whose ``overall_status`` is not yet closed (anything other than
    "Closed by Client" / "Overdue") and whose ``remediation_deadline`` is before today
    is set to "Overdue", and a system Notification is posted to the plan's AFMCO owner
    and to the Operations Director. Mirrors daily_building_license_expiry_check:
    paginated 500/batch with per-row error isolation.
    """
    from frappe.utils import today, getdate

    today_date = getdate(today())
    logger = frappe.logger()
    flagged = 0

    start = 0
    batch_size = 500
    while True:
        plans = frappe.get_all(
            "Client Audit Remediation Plan",
            filters={
                "docstatus": 1,
                "overall_status": ["not in", ["Closed by Client", "Overdue"]],
                "remediation_deadline": ["<", str(today_date)],
            },
            fields=["name", "remediation_deadline", "afmco_owner", "client_project"],
            limit_start=start,
            limit_page_length=batch_size,
        )
        if not plans:
            break

        for plan in plans:
            try:
                frappe.db.set_value(
                    "Client Audit Remediation Plan", plan.name, "overall_status", "Overdue"
                )
                msg = (
                    f"audit_remediation_deadline_watch: remediation plan {plan.name} "
                    f"(project {plan.client_project}) passed its deadline {plan.remediation_deadline} "
                    f"and is now Overdue."
                )
                logger.warning(msg)
                _notify_operational("Client Audit Remediation Plan", plan.name, msg)
                # [#wave3-audit] notify the plan owner directly + the Operations Director role.
                if plan.afmco_owner:
                    frappe.get_doc({
                        "doctype": "Notification Log",
                        "for_user": plan.afmco_owner,
                        "type": "Alert",
                        "subject": f"Audit remediation overdue: {plan.name}"[:140],
                        "email_content": msg,
                    }).insert(ignore_permissions=True)  # audit-ok — scheduler-run owner alert
                _notify_role_system(
                    "Operations Director",
                    subject=f"Audit remediation overdue: {plan.name}",
                    message=msg,
                )
                flagged += 1
            except Exception:
                frappe.db.rollback()
                frappe.log_error(
                    message=frappe.get_traceback(),
                    title=f"Audit remediation watch failed for {plan.name}"[:140],
                )

        start += batch_size

    logger.info(f"audit_remediation_deadline_watch: {flagged} remediation plan(s) flagged Overdue.")


def weekly_custody_digest() -> None:
    """Email each building's responsible supervisor a weekly custody roll-up.

    Per building: open custody issues (Issued / Partially Returned), of those the
    count already past ``expected_return_date``, the SAR value still in worker
    hands (net signed ledger value, the same definition as the value-in-hands
    card), and damage assessed month-to-date. Buildings are grouped by their
    ``responsible_facility_supervisor`` so each supervisor receives only their own
    buildings. Buildings with no supervisor, or a disabled supervisor user, are
    skipped — oversight roles already see the dashboards.

    Gated by the master email kill-switch; per-recipient delivery is isolated
    (rollback before log) so one bad recipient never aborts the rest. Idempotent:
    a re-run re-sends the current snapshot and mutates no state.
    """
    from collections import defaultdict

    from frappe.utils import escape_html, flt, fmt_money, get_url_to_list, getdate, today

    from apex_habitat.apex_core.utils.email_gate import email_enabled

    logger = frappe.logger()

    if not email_enabled():
        logger.info("weekly_custody_digest: email disabled (Habitat Settings); skipped.")
        return

    buildings = frappe.get_all(
        "Accommodation Building",
        filters={"responsible_facility_supervisor": ["is", "set"]},
        fields=["name", "responsible_facility_supervisor"],
    )
    if not buildings:
        logger.info("weekly_custody_digest: no building has a responsible supervisor.")
        return

    today_str = str(getdate(today()))
    month_start = str(getdate(today()).replace(day=1))

    # Open custody issues per building, and how many are overdue.
    open_counts: dict[str, int] = defaultdict(int)
    overdue_counts: dict[str, int] = defaultdict(int)
    for issue in frappe.get_all(
        "Custody Issue",
        filters={"status": ["in", ["Issued", "Partially Returned"]]},
        fields=["building", "expected_return_date"],
    ):
        if not issue.building:
            continue
        open_counts[issue.building] += 1
        if issue.expected_return_date and str(issue.expected_return_date) < today_str:
            overdue_counts[issue.building] += 1

    # Net custody value still in worker hands, per building (ledger is the
    # canonical valuation, mirroring get_custody_value_in_employee_hands).
    value_by_building: dict[str, float] = defaultdict(float)
    for row in frappe.db.sql(
        """
        SELECT building, COALESCE(SUM(qty * COALESCE(unit_cost_sar, 0)), 0) AS value
        FROM `tabAccommodation Stock Ledger`
        WHERE is_cancelled = 0
          AND item_type = 'Custody Article'
          AND employee IS NOT NULL AND employee != ''
          AND building IS NOT NULL AND building != ''
        GROUP BY building
        """,
        as_dict=True,
    ):
        value_by_building[row.building] = flt(row.value)

    # Damage assessed month-to-date per building (submitted assessments only).
    damage_mtd: dict[str, float] = defaultdict(float)
    for row in frappe.db.sql(
        """
        SELECT building, COALESCE(SUM(total_estimated_replacement_cost_sar), 0) AS cost
        FROM `tabCustody Damage Assessment`
        WHERE docstatus = 1
          AND assessment_date >= %(month_start)s
          AND building IS NOT NULL AND building != ''
        GROUP BY building
        """,
        {"month_start": month_start},
        as_dict=True,
    ):
        damage_mtd[row.building] = flt(row.cost)

    by_supervisor: dict[str, list] = defaultdict(list)
    for b in buildings:
        by_supervisor[b.responsible_facility_supervisor].append(b.name)

    list_url = get_url_to_list("Custody Issue")
    sent = 0
    for supervisor, names in by_supervisor.items():
        try:
            if not frappe.db.get_value("User", supervisor, "enabled"):
                continue
            rows = "".join(
                "<tr><td>{b}</td><td>{open_}</td><td>{overdue}</td>"
                "<td>{value}</td><td>{damage}</td></tr>".format(
                    b=escape_html(name),
                    open_=open_counts.get(name, 0),
                    overdue=overdue_counts.get(name, 0),
                    value=fmt_money(value_by_building.get(name, 0.0), currency="SAR"),
                    damage=fmt_money(damage_mtd.get(name, 0.0), currency="SAR"),
                )
                for name in names
            )
            header = "<tr><th>{b}</th><th>{o}</th><th>{ov}</th><th>{v}</th><th>{d}</th></tr>".format(
                b=_("Building"),
                o=_("Open"),
                ov=_("Overdue"),
                v=_("Value in hands"),
                d=_("Damage (MTD)"),
            )
            message = "{intro}<br><table border='1' cellpadding='4'>{header}{rows}</table><br><a href='{url}'>{cta}</a>".format(
                intro=_("Weekly custody summary for your building(s):"),
                header=header,
                rows=rows,
                url=list_url,
                cta=_("Open the custody issue list"),
            )
            frappe.sendmail(
                recipients=[supervisor],
                subject=_("Weekly Custody Digest"),
                message=message,
            )
            sent += 1
        except Exception:
            frappe.db.rollback()
            frappe.log_error(
                message=frappe.get_traceback(),
                title=f"Custody digest failed for {supervisor}"[:140],
            )

    logger.info(f"weekly_custody_digest: sent {sent} supervisor digest(s).")
