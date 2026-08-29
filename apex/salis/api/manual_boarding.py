# Copyright (c) 2026, afmcoltd


import frappe
from frappe import _

from apex.apex_core.utils.portal_identity import DRIVER, as_capacity
from apex.apex_core.utils.rate_limit_identity import rate_limit
from apex.salis.api import boarding
from apex.salis.api.boarding_flow import mark_boarded
from apex.salis.api.driver_portal import _require_enabled


def _log_attempt(dispatch_trip, trip, employee, result, trip_start_log=None, created=0):
    doc = frappe.get_doc(
        {
            "doctype": "Boarding Scan Log",
            "dispatch_trip": dispatch_trip,
            "trip_start_log": trip_start_log,
            "transport_request": trip.get("transport_request"),
            "driver": trip.get("driver"),
            "employee": employee,
            "result": result,
            "method": "Manual",
            "scanned_at": frappe.utils.now_datetime(),
            "boarding_event_created": frappe.utils.cint(created),
        }
    )
    with as_capacity(DRIVER, trip.get("driver")):
        doc.insert()
    return doc.name


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=30, seconds=60)
def board_worker(dispatch_trip, employee):
    _require_enabled()
    trip = boarding._resolve_trip(dispatch_trip, "write")
    employee = (employee or "").strip()
    if not employee:
        frappe.throw(_("Select a worker to board."))

    frappe.db.get_value("Dispatch Trip", dispatch_trip, "name", for_update=True)
    if employee not in boarding._trip_manifest_workers(
        trip.get("transport_request"), dispatch_trip
    ):
        scan_log = _log_attempt(dispatch_trip, trip, employee, "Wrong Trip")
        return {"result": "Wrong Trip", "scan_log": scan_log}

    driver = trip.get("driver")
    log = boarding.get_or_create_log(dispatch_trip, driver)
    if boarding.already_boarded(log, employee):
        scan_log = _log_attempt(dispatch_trip, trip, employee, "Duplicate", log.name)
        return {"result": "Duplicate", "scan_log": scan_log, "trip_start_log": log.name}

    log.append(
        "boarding_events",
        {
            "worker": employee,
            "boarded_at": frappe.utils.now_datetime(),
            "method": "Manual",
        },
    )
    with as_capacity(DRIVER, driver):
        log.save()
    mark_boarded(dispatch_trip, employee, source="Manual")
    scan_log = _log_attempt(dispatch_trip, trip, employee, "Valid", log.name, created=1)
    return {
        "result": "Valid",
        "scan_log": scan_log,
        "trip_start_log": log.name,
        "boarded_count": log.boarded_count,
    }
