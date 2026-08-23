# Copyright (c) 2026, afmcoltd
"""Salis Driver Portal — profile endpoints (split from the driver_portal god module). Kernel helpers are imported from the package so the canonical dotted path apex.salis.api.driver_portal.<fn> is unchanged."""

import frappe

from apex.apex_core.utils.rate_limit_identity import rate_limit
from apex.salis.api.driver_portal import (
    _resolve_driver,
    _require_enabled,
)
from apex.salis.api.masar_worker import _fmt_date
from apex.salis.utils import days_until as _days_until


def _employee_documents(employee):
    """The linked Employee's Iqama/passport identity expiries, read defensively.

	Mirrors ``masar.get_worker_context``: Employee field names vary across HR setups,
	so every field is read via ``.get()`` on the cached doc and a missing field
	surfaces as None rather than erroring. Returns a list of ``{type, number, expiry,
	days_left}`` entries (only for documents on file), the same shape the Masar
	profile consumes — so the SPA reuses one renderer. Read-only.
    """
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
    """Resolve a Project link id (e.g. ``PROJ-0038``) to its display name.

	The portal shows the project's human ``project_name`` (the Project DocType's
	title field), not the autonamed series code. Returns the resolved name, or the
	code itself as a fallback when the link is blank or cannot be resolved — so a
	missing/renamed project never blanks the field. Read-only."""
    if not code:
        return code
    return frappe.db.get_value("Project", code, "project_name") or code


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=120, seconds=60)
def get_driver_profile():
    """The current driver's OWN profile (read).

	Identity-scoped: the driver is resolved credential-first, never client-supplied,
	so this can only ever return the caller's own record — it cannot leak another
	driver's data. Read-only, no commit. Returns the durable fields the portal
	profile view shows (name, employee, status, license, contact, current vehicle).
	Date fields are stringified so the JSON response always serializes."""
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
