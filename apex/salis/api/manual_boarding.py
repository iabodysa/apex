"""Driver fallback when a worker cannot present a scannable boarding pass.

The Boarding Scan Log write keeps ``ignore_permissions`` for the reason in ``boarding.py``: it is
an ``in_create`` audit record no role may write by hand, and this is the fallback path, so every
attempt is logged whether it succeeds or fails — a DocPerm that made the write legal would also
let the log be edited afterwards, which is the one thing it must not. The Trip Start Log write
runs inside ``as_capacity(DRIVER, driver)`` instead: it is the driver's own execution record, and
``apex.salis.permissions._trip_start_log_capacity_verdict`` refuses it when the log's own driver
is not the resolved identity.
"""

import frappe
from frappe import _

from apex.apex_core.utils.portal_identity import DRIVER, as_capacity
from apex.apex_core.utils.rate_limit_identity import rate_limit


def _log_attempt(dispatch_trip, trip, employee, result, trip_start_log=None, created=0):
    """Write one immutable Boarding Scan Log row for this manual scan attempt.

    ``board_worker`` is ``allow_guest=True``: the caller is a credential-scoped driver trip, not a
    signed-in account, so there is no role to grant a DocPerm to in the first place. See
    ``log_credential_event`` (apex/apex_core/utils/portal_identity.py:1) for the same shape.
    """
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
    doc.insert(ignore_permissions=True)
    return doc.name


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=30, seconds=60)
def board_worker(dispatch_trip, employee):
    """Board one manifest worker manually on the credential-scoped driver trip."""
    from apex.salis.api import boarding
    from apex.salis.api.boarding_flow import mark_boarded
    from apex.salis.api.driver_portal import _require_enabled

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
    log = boarding._get_or_create_log(dispatch_trip, driver)
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
