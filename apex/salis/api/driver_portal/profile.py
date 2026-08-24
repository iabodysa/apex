# Copyright (c) 2026, afmcoltd

import frappe

from apex.apex_core.utils.rate_limit_identity import rate_limit
from apex.salis.api.driver_portal import (
    _resolve_driver,
    _require_enabled,
)
from apex.salis.api.masar_worker import _fmt_date
from apex.salis.utils import days_until as _days_until


def _employee_documents(employee):
    if not employee or not frappe.db.exists("Employee", {"name": employee}):
        return []
    emp = frappe.get_cached_doc("Employee", employee)
    documents = []
    iqama_no = emp.get("iqama") or emp.get("iqama_no")
    iqama_expiry = emp.get("iqama_expiry") or emp.get("valid_upto")
    if iqama_no or iqama_expiry:
        documents.append(
            {
                "type": "iqama",
                "number": iqama_no,
                "expiry": _fmt_date(iqama_expiry),
                "days_left": _days_until(iqama_expiry),
            }
        )
    passport_no = emp.get("passport_number")
    if passport_no:
        documents.append(
            {
                "type": "passport",
                "number": passport_no,
                "expiry": _fmt_date(emp.get("passport_expiry")),
                "days_left": _days_until(emp.get("passport_expiry")),
            }
        )
    return documents


def _project_label(code):
    if not code:
        return code
    return frappe.db.get_value("Project", code, "project_name") or code


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=120, seconds=60)
def get_driver_profile():
    _require_enabled()
    driver = _resolve_driver()
    d = frappe.db.get_value(
        "Salis Driver", driver,
        ["name", "full_name", "employee", "status", "phone", "project",
         "license_number", "license_expiry", "current_vehicle"],
        as_dict=True,
    ) or {}
    if d.get("license_expiry"):
        d["license_expiry"] = frappe.utils.cstr(d["license_expiry"])
    if d.get("project"):
        d["project"] = _project_label(d["project"])
    d["documents"] = _employee_documents(d.get("employee"))
    return d
