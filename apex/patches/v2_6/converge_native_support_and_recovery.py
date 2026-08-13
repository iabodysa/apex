from __future__ import annotations

import frappe

from apex.apex_core.setup.employee_advance_recovery import (
    configure_recovery,
    seed_recovery_component,
)
from apex.apex_core.setup.salis_support import (
    SLA_NAME,
    SLA_PRIORITIES,
    grant_issue_role_permissions,
)


_LEGACY_HOLIDAY_LIST = "Apex Support 24x7"
_LEGACY_DAYS = {"Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"}


def execute():
    """Converge upgraded sites on native fixtures, Issue SLA, and Employee Advance recovery."""
    grant_issue_role_permissions()
    _retire_untouched_legacy_sla()
    seed_recovery_component()
    _migrate_deduction_policy()
    _repair_demo_import_residue()
    _assert_select_consistency()


def _retire_untouched_legacy_sla():
    name = frappe.db.get_value(
        "Service Level Agreement", {"service_level": SLA_NAME}, "name"
    )
    if not name:
        return
    doc = frappe.get_doc("Service Level Agreement", name)
    priorities = {
        (
            row.priority,
            int(row.response_time or 0),
            int(row.resolution_time or 0),
            int(row.default_priority or 0),
        )
        for row in doc.priorities
    }
    schedule = {
        (row.workday, str(row.start_time), str(row.end_time))
        for row in doc.support_and_resolution
    }
    generated = (
        doc.holiday_list == _LEGACY_HOLIDAY_LIST
        and priorities == set(SLA_PRIORITIES)
        and {row.status for row in doc.sla_fulfilled_on} == {"Resolved", "Closed"}
        and {row[0] for row in schedule} == _LEGACY_DAYS
        and all(row[1] in {"0:00:00", "00:00:00"} for row in schedule)
        and all(row[2] == "23:59:59" for row in schedule)
    )
    if not generated:
        return
    frappe.delete_doc(
        "Service Level Agreement", name, ignore_permissions=True, force=True
    )
    _delete_unused_legacy_holiday_list()


def _delete_unused_legacy_holiday_list():
    if not frappe.db.exists("Holiday List", _LEGACY_HOLIDAY_LIST):
        return
    if frappe.db.exists(
        "Service Level Agreement", {"holiday_list": _LEGACY_HOLIDAY_LIST}
    ):
        return
    holiday_list = frappe.get_doc("Holiday List", _LEGACY_HOLIDAY_LIST)
    if holiday_list.holidays:
        return
    if str(holiday_list.from_date) != "2000-01-01" or str(holiday_list.to_date) != "2099-12-31":
        return
    frappe.delete_doc(
        "Holiday List", _LEGACY_HOLIDAY_LIST, ignore_permissions=True, force=True
    )


def _migrate_deduction_policy():
    if not frappe.db.table_exists("Salary Deduction Policy"):
        return
    enabled = frappe.db.get_single_value(
        "Salary Deduction Policy", "enable_salary_deductions"
    )
    max_percent = frappe.db.get_single_value(
        "Salary Deduction Policy", "global_max_percent_of_salary"
    )
    damage = frappe.db.get_value(
        "Salary Deduction Type Rule",
        {
            "parent": "Salary Deduction Policy",
            "parenttype": "Salary Deduction Policy",
            "deduction_type": "Damage",
        },
        ["enabled", "salary_component"],
        as_dict=True,
    )
    if enabled and damage and damage.enabled:
        company = frappe.db.get_single_value("Salary Deduction Policy", "company")
        try:
            configure_recovery(
                enabled=True,
                company=company,
                salary_component=damage.salary_component,
                max_percent=max_percent,
            )
        except Exception:
            frappe.clear_last_message()
            frappe.log_error(
                title="Employee Advance recovery migration left disabled",
                message=frappe.get_traceback(),
            )

    for doctype in ("Salary Deduction Type Rule", "Salary Deduction Policy"):
        if frappe.db.exists("DocType", doctype):
            frappe.delete_doc("DocType", doctype, ignore_permissions=True, force=True)


def _repair_demo_import_residue():
    if frappe.db.table_exists("Dispatch Trip"):
        frappe.db.set_value(
            "Dispatch Trip",
            {"naming_series": "TRIP-DEMO-.##"},
            "naming_series",
            "DT-.######",
            update_modified=False,
        )
    if not frappe.db.table_exists("Bed"):
        return
    invalid_beds = frappe.get_all(
        "Bed",
        filters={"status": ["not in", ["Available", "Occupied", "Out of Service"]]},
        pluck="name",
    )
    invalid_beds += frappe.get_all("Bed", filters={"status": ["is", "not set"]}, pluck="name")
    for bed in set(invalid_beds):
        occupied = frappe.db.exists(
            "Housing Assignment",
            {"bed": bed, "docstatus": 1, "check_out_date": ["is", "not set"]},
        )
        frappe.db.set_value(
            "Bed", bed, "status", "Occupied" if occupied else "Available", update_modified=False
        )


def _assert_select_consistency():
    problems = []
    doctypes = frappe.get_all(
        "DocType",
        filters={"module": ["in", ["Apex Core", "Habitat", "Salis", "Logistay"]]},
        pluck="name",
    )
    for doctype in doctypes:
        meta = frappe.get_meta(doctype)
        if meta.issingle or meta.istable:
            continue
        for field in meta.get("fields", {"fieldtype": "Select"}):
            options = {line.strip() for line in (field.options or "").splitlines() if line.strip()}
            if not options:
                continue
            values = frappe.get_all(doctype, fields=[field.fieldname], distinct=True)
            for row in values:
                value = row.get(field.fieldname)
                if value not in (None, "") and value not in options:
                    problems.append(f"{doctype}.{field.fieldname}={value!r}")
    if problems:
        frappe.throw("Invalid Apex Select values remain: " + ", ".join(problems[:20]))
