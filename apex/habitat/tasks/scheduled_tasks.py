# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import frappe
from frappe.utils import get_first_day, get_first_day_of_week, getdate, today

_ROW_SAVEPOINT = "scheduled_task_row"

def daily_scheduled_task_instance_generator() -> None:
    today_str = today()
    today_date = getdate(today_str)
    logger = frappe.logger()

    def _period_key(freq: str) -> str:
        if freq == "Daily":
            return today_str
        if freq == "Weekly":
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

        templates = list({assignment.template for assignment in assignments})
        items_by_template = {}
        for item in frappe.get_all(
            "Scheduled Task Template Item",
            filters={"parent": ["in", templates], "is_active": 1},
            fields=["parent", "task_catalog", "frequency_override", "title"],
        ):
            items_by_template.setdefault(item.parent, []).append(item)
        frequency_by_template = dict(
            frappe.get_all(
                "Scheduled Task Template",
                filters={"name": ["in", templates]},
                fields=["name", "frequency"],
                as_list=True,
            )
        )

        for assignment in assignments:
            items = items_by_template.get(assignment.template, [])
            template_frequency = frequency_by_template.get(assignment.template) or "Monthly"
            for item in items:
                frequency = item.frequency_override or template_frequency

                due_date = _period_key(frequency)

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
                    instance.insert()
                    created += 1
                    logger.info(
                        "daily_scheduled_task_instance_generator: created %s "
                        "(assignment=%s, task_catalog=%s, due=%s).",
                        instance.name,
                        assignment.name,
                        item.task_catalog,
                        due_date,
                    )
                except Exception as e:
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
