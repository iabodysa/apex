# Copyright (c) 2026, AFMCO and contributors
"""Scheduled tasks for the Habitat module (split by domain)."""

from __future__ import annotations

import frappe

# Constant name, re-issued per template item: MariaDB replaces a same-named
# savepoint rather than stacking one per row.
_ROW_SAVEPOINT = "scheduled_task_row"


def daily_scheduled_task_instance_generator() -> None:
    """Generate Scheduled Task Instance records using the Assignment × Item pattern.

    Assignment-based design: iterates active Scheduled Task Assignments, then for
    each active template item row creates one Scheduled Task Instance per
    (assignment, task_catalog, due_date). The due_date is resolved from the item's
    frequency_override if set, or the template-level frequency otherwise. Idempotent:
    an existing non-cancelled instance for the same (assignment, task_catalog, due_date)
    is skipped. Per-item error isolation; paginated 500/batch on assignments.
    """
    from frappe.utils import today, get_first_day, get_first_day_of_week, getdate

    today_str = today()
    today_date = getdate(today_str)
    logger = frappe.logger()

    def _period_key(freq: str) -> str:
        """Return the canonical due_date string for the given frequency."""
        if freq == "Daily":
            return today_str
        if freq == "Weekly":
            # Python's weekday() is Monday-based; the site's week may not be. frappe reads
            # System Settings first_day_of_the_week (data.py:69-70) and defaults to Sunday, so
            # a hardcoded Monday puts the whole app one day out on any site keeping that
            # default — invisible mid-week, wrong on the boundary day.
            return str(get_first_day_of_week(today_date))
        if freq == "Monthly":
            return str(get_first_day(today_date))
        if freq == "Quarterly":
            month = today_date.month
            quarter_start_month = ((month - 1) // 3) * 3 + 1
            return str(today_date.replace(month=quarter_start_month, day=1))
        if freq == "Annually":
            return str(today_date.replace(month=1, day=1))
        return today_str

    created = 0
    start = 0
    batch_size = 500
    while True:
        assignments = frappe.get_all(
            "Scheduled Task Assignment",
            filters={"is_active": 1},
            fields=["name", "template", "building"],
            limit_start=start,
            limit_page_length=batch_size,
        )
        if not assignments:
            break

        for assignment in assignments:
            items = frappe.get_all(
                "Scheduled Task Template Item",
                filters={"parent": assignment.template, "is_active": 1},
                fields=["task_catalog", "frequency_override", "title"],
            )
            # [#b49szm]
            template_frequency = (
                frappe.db.get_value("Scheduled Task Template", assignment.template, "frequency")
                or "Monthly"
            )
            for item in items:
                # [#cxb0x6]
                frequency = item.frequency_override or template_frequency

                due_date = _period_key(frequency)

                # [#decyo7]
                if frappe.db.exists(
                    "Scheduled Task Instance",
                    {
                        "assignment": assignment.name,
                        "task_catalog": item.task_catalog,
                        "due_date": due_date,
                        "docstatus": ["!=", 2],
                    },
                ):
                    continue

                frappe.db.savepoint(_ROW_SAVEPOINT)
                try:
                    instance = frappe.get_doc({
                        "doctype": "Scheduled Task Instance",
                        "assignment": assignment.name,
                        "task_catalog": item.task_catalog,
                        "building": assignment.building,
                        "template": assignment.template,
                        "due_date": due_date,
                        "status": "Open",
                    })
                    instance.insert(ignore_permissions=True)  # audit-ok — scheduler-run task generation
                    created += 1
                    logger.info(
                        "daily_scheduled_task_instance_generator: created %s "
                        "(assignment=%s, task_catalog=%s, due=%s).",
                        instance.name,
                        assignment.name,
                        item.task_catalog,
                        due_date,
                    )
                except Exception as e:  # noqa: BLE001
                    frappe.db.rollback(save_point=_ROW_SAVEPOINT)
                    logger.error(
                        "daily_scheduled_task_instance_generator: failed for "
                        "assignment=%s, task_catalog=%s: %s",
                        assignment.name,
                        item.task_catalog,
                        e,
                    )
                    frappe.log_error(
                        message=frappe.get_traceback(),
                        title=(
                            f"STI generator failed (assignment={assignment.name}, "
                            f"task={item.task_catalog})"
                        )[:140],
                    )

        start += batch_size

    logger.info(f"daily_scheduled_task_instance_generator: created {created} instance(s).")
