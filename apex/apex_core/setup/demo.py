# Copyright (c) 2026, afmcoltd

from __future__ import annotations

import random
import string
import time

import frappe
from frappe import _
from frappe.model.workflow import apply_workflow
from frappe.utils import add_days, today

from apex.apex_core.utils.company import resolve_company_or_any
from apex.habitat.tasks.cost import allocate_building_accommodation_cost
from apex.salis.utilisation_engine import weekly_vehicle_utilisation_snapshot

DEMO_ARG = "apex_setup_demo"

_GENDER_WAIT_SECONDS = 60

DEMO_OWNER = "demo.manager@apex.example"
DEMO_SUPERVISOR = "demo.supervisor@apex.example"
DEMO_APPROVER = "demo.approver@apex.example"
DEMO_FLEET_SUPERVISOR = "demo.fleet.supervisor@apex.example"
DEMO_FLEET_MANAGER = "demo.fleet.manager@apex.example"
DEMO_USERS = (
    DEMO_OWNER,
    DEMO_SUPERVISOR,
    DEMO_APPROVER,
    DEMO_FLEET_SUPERVISOR,
    DEMO_FLEET_MANAGER,
)

DEMO_DOCTYPES = (
    "Company",
    "Supplier",
    "Project",
    "Site",
    "Building",
    "Room",
    "Bed",
    "Employee",
    "Custody Asset Category",
    "Custody Article",
    "Utility Account",
    "Facility Asset",
    "Salis Driver",
    "Salis Vehicle",
    "Telecom Contract",
    "SIM Card",
    "Housing Assignment",
    "Maintenance Request",
    "Cleaning Log",
    "Lease",
    "Utility Bill Entry",
    "Custody Damage Assessment",
    "Audit Remediation Plan",
    "Facility Asset Movement",
    "Operational Depreciation Snapshot",
    "Housing Checkout",
    "Driver Attendance",
    "Driver Clearance",
    "Vehicle Utilisation Snapshot",
    "Accommodation Ledger",
    "QR Location",
    "Custody Handover",
    "Vehicle Handover Checklist Template",
    "Vehicle Assignment",
    "Vehicle Handover",
    "Vehicle Incident",
    "File",
    "Vehicle Damage Write-Off",
    "Subcontractor Service Contract",
    "Subcontractor Service Order",
    "Rental Office",
    "Goods Receipt",
    "Material Transfer",
    "Custody Issue",
    "Maintenance Work Order",
    "Safety Incident",
    "Safety Round",
    "Fuel Request",
    "Fuel Claim",
    "Passenger Manifest",
    "Rental Settlement",
    "Route Template",
    "Work Shift",
    "Route Assignment",
    "Dispatch Trip",
    "Transport Request",
    "Fuel Exception Case",
    "Movement Cost Recovery",
    "Movement Cost Transfer",
    "Salis Payment Request",
)

_DEMO_SCENARIO_COUNTS = {
    "Project": 2,
    "Building": 2,
    "Room": 2,
    "Bed": 4,
    "Employee": 3,
    "SIM Card": 3,
    "Housing Assignment": 3,
}

DEMO_INVENTORY = {
    doctype: {
        "target_scenarios": 3,
        "observed_scenarios": _DEMO_SCENARIO_COUNTS.get(doctype, 1),
        "cleanup": "owner",
        **(
            {}
            if _DEMO_SCENARIO_COUNTS.get(doctype, 1) >= 3
            else {
                "gap": (
                    "The current coherent linked demo has fewer than three records; "
                    "additional diverse scenarios remain to be built."
                )
            }
        ),
    }
    for doctype in DEMO_DOCTYPES
}
DEMO_INVENTORY.update(
    {
        "User Permission": {
            "target_scenarios": 3,
            "observed_scenarios": 1,
            "cleanup": "demo-user",
            "gap": "Two more distinct scoped permission scenarios remain to be built.",
        },
        "User": {
            "target_scenarios": 3,
            "observed_scenarios": 3,
            "cleanup": "explicit-name",
        },
        "Contact": {
            "target_scenarios": 3,
            "observed_scenarios": 3,
            "cleanup": "linked-demo-user",
        },
    }
)

_DEMO_SITE = "Al Waha Workers Village"
_DEMO_BUILDING = "Al Waha Building 1"
_DEMO_PARTNER_BUILDING = "Al Rawdah Building 1"
_DEMO_PROJECT = "Al Waha Housing Project"
_DEMO_COMPLETED_PROJECT = "Al Furat Housing Project"
_DEMO_PARTNER_COMPANY = "Al Rawdah Support Services"
_DEMO_SUPPLIER = "Dar Al Sakan Supplies"
_DEMO_CATEGORY = "Room Furnishings"
_DEMO_ARTICLE = "Bunk Bed Mattress"
_DEMO_RENTAL_OFFICE = "Al Yamamah Rental Office"
_DEMO_ROOMS = ("101", "102")

def setup_demo(args=None):
    args = frappe._dict(args or {})
    if not args.get(DEMO_ARG):
        return
    frappe.enqueue(build_demo_data, enqueue_after_commit=True, at_front=True)

def boot_demo(bootinfo):
    bootinfo.apex_demo_data = bool(frappe.db.exists("User", DEMO_OWNER))

def build_demo_data():
    if frappe.db.exists("User", DEMO_OWNER):
        return {"built": False, "stopped_at": "already built"}

    operator = frappe.session.user
    if not resolve_company_or_any():
        _report_build_failure(operator, "Company", None)
        return {"built": False, "stopped_at": "Company"}

    gender = _demo_gender()

    _create_demo_users()
    previous_user = frappe.session.user
    failure = None
    try:
        frappe.set_user(DEMO_OWNER)
        context = {"gender": gender}
        for doctype, step in _BUILD_STEPS:
            try:
                step(context)
            except Exception:
                failure = (doctype, frappe.get_traceback(with_context=True))
                break
    finally:
        frappe.set_user(previous_user)

    if failure:
        _report_build_failure(operator, *failure)
        return {"built": False, "stopped_at": failure[0]}

    frappe.cache.delete_keys("bootinfo")
    return {"built": True, "stopped_at": None}

def _report_build_failure(operator, doctype, traceback):
    frappe.db.rollback()
    frappe.log_error(title="Apex demo build", message=traceback or doctype)
    frappe.publish_realtime(
        "msgprint",
        _("The Apex demo data could not be built. It stopped at {0}; the Error Log has why.").format(
            _(doctype)
        ),
        user=operator,
    )

def _break_settlement_payment_cycle():
    for name in frappe.get_all(
        "Rental Settlement",
        filters={"owner": ["in", list(DEMO_USERS)], "payment_request": ["is", "set"]},
        pluck="name",
    ):
        frappe.db.set_value("Rental Settlement", name, "payment_request", None, update_modified=False)

def _remove_worker_tokens_for_demo_drivers(deleted, residue):
    drivers = frappe.get_all(
        "Salis Driver", filters={"owner": ["in", list(DEMO_USERS)]}, pluck="name"
    )
    if not drivers:
        return deleted, residue
    for name in frappe.get_all(
        "Masar Worker Token", filters={"driver": ["in", drivers]}, pluck="name"
    ):
        error = _remove_one("Masar Worker Token", name)
        if error:
            residue.append({"doctype": "Masar Worker Token", "name": name, "error": error})
        else:
            deleted += 1
    return deleted, residue

@frappe.whitelist()
def clear_demo_data():
    frappe.only_for("System Manager")
    if not frappe.db.exists("User", DEMO_OWNER):
        frappe.throw(_("This site has no Apex demo data to remove."))

    _break_settlement_payment_cycle()

    deleted = 0
    residue = []
    deleted, residue = _remove_user_permissions(deleted, residue)
    deleted, residue = _remove_worker_tokens_for_demo_drivers(deleted, residue)
    for doctype in reversed(DEMO_DOCTYPES):
        for name in frappe.get_all(
            doctype, filters={"owner": ["in", list(DEMO_USERS)]}, pluck="name"
        ):
            error = _remove_one(doctype, name)
            if error:
                residue.append({"doctype": doctype, "name": name, "error": error})
            else:
                deleted += 1

    frappe.db.commit()
    deleted, residue = _remove_demo_users(deleted, residue)

    frappe.cache.delete_keys("bootinfo")
    _report(deleted, residue)
    return {"deleted": deleted, "residue": residue}

def _remove_one(doctype, name):
    save_point = "".join(random.sample(string.ascii_lowercase, 10))
    frappe.db.savepoint(save_point)
    try:
        doc = frappe.get_doc(doctype, name)
        if doc.docstatus == 1:
            if doc.meta.has_field("cancellation_reason") and not doc.get(
                "cancellation_reason"
            ):
                doc.cancellation_reason = "Apex demo data removal"
            doc.cancel()
        frappe.delete_doc(doctype, name, ignore_permissions=True, delete_permanently=True)
    except Exception as exc:
        _release(save_point, undo=True)
        frappe.clear_last_message()
        return str(exc) or exc.__class__.__name__
    _release(save_point)
    return None

def _release(save_point, undo=False):
    try:
        if undo:
            frappe.db.rollback(save_point=save_point)
        else:
            frappe.db.release_savepoint(save_point)
    except Exception:
        frappe.clear_last_message()

def _remove_user_permissions(deleted, residue):
    for permission in frappe.get_all(
        "User Permission", filters={"user": ["in", list(DEMO_USERS)]}, pluck="name"
    ):
        error = _remove_one("User Permission", permission)
        if error:
            residue.append(
                {"doctype": "User Permission", "name": permission, "error": error}
            )
        else:
            deleted += 1
    return deleted, residue

def _remove_demo_users(deleted, residue):
    if residue:
        return deleted, residue

    contacts = [
        name
        for user in DEMO_USERS
        for name in frappe.get_all("Contact", filters={"user": user}, pluck="name")
    ]

    for user in DEMO_USERS:
        if not frappe.db.exists("User", {"name": user}):
            continue
        error = _remove_one("User", user)
        if error:
            residue.append({"doctype": "User", "name": user, "error": error})
        else:
            deleted += 1
    frappe.db.commit()

    for contact in contacts:
        if not frappe.db.exists("Contact", {"name": contact}):
            continue
        error = _remove_one("Contact", contact)
        if error:
            residue.append({"doctype": "Contact", "name": contact, "error": error})
        else:
            deleted += 1
    return deleted, residue

def _report(deleted, residue):
    if not residue:
        frappe.msgprint(
            _("Removed {0} demo records.").format(deleted),
            title=_("Demo Data Removed"),
            indicator="green",
        )
        return
    frappe.msgprint(
        _(
            "Removed {0} demo records. {1} could not be removed and are listed below. "
            "The demo users are kept so you can run this again once they are cleared."
        ).format(deleted, len(residue))
        + "<br>"
        + "<br>".join(
            "{0} {1}: {2}".format(row["doctype"], row["name"], row["error"])
            for row in residue
        ),
        title=_("Demo Data Partly Removed"),
        indicator="orange",
    )

def _create_demo_users():
    for email, full_name, roles in (
        (DEMO_OWNER, "Fahad Al-Dosari", ("System Manager",)),
        (DEMO_SUPERVISOR, "Turki Al-Zahrani", ("Resident Supervisor",)),
        (DEMO_APPROVER, "Nasser Al-Qahtani", ("Accommodation Manager", "Finance Manager")),
        (DEMO_FLEET_SUPERVISOR, "Khalid Al-Harbi", ("Fleet Supervisor",)),
        (DEMO_FLEET_MANAGER, "Sultan Al-Ghamdi", ("Fleet Manager",)),
    ):
        if frappe.db.exists("User", {"name": email}):
            continue
        user = frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": full_name,
                "send_welcome_email": 0,
            }
        ).insert()
        installed = [
            role for role in roles if frappe.db.exists("Role", {"name": role})
        ]
        if installed:
            user.add_roles(*installed)

def _create(doctype, payload):
    if doctype not in set(DEMO_DOCTYPES):
        frappe.throw(
            _("{0} is not a demo DocType; the demo removal would never clear it.").format(
                doctype
            )
        )
    doc = frappe.get_doc(dict(payload, doctype=doctype))
    doc.insert(ignore_permissions=True)
    return doc

def _walk_workflow(doctype, name, actions, user=DEMO_APPROVER):
    previous_user = frappe.session.user
    frappe.set_user(user)
    try:
        doc = frappe.get_doc(doctype, name)
        for action in actions:
            apply_workflow(doc, action)
    finally:
        frappe.set_user(previous_user)

def _build_partner_company(context):
    context["company"] = resolve_company_or_any()
    currency = (
        frappe.db.get_value("Company", context["company"], "default_currency")
        if context["company"]
        else None
    ) or frappe.defaults.get_global_default("currency")
    country = (
        frappe.db.get_value("Company", context["company"], "country")
        if context["company"]
        else None
    )
    partner = _create(
        "Company",
        {
            "company_name": _DEMO_PARTNER_COMPANY,
            "abbr": "DPCO",
            "default_currency": currency,
            "country": country or "Saudi Arabia",
        },
    )
    context["partner_company"] = partner.name
    context["currency"] = currency

def _build_supplier(context):
    group = frappe.db.get_value(
        "Supplier Group", {"name": "All Supplier Groups"}
    ) or frappe.db.get_value("Supplier Group", {})
    payload = {"supplier_name": _DEMO_SUPPLIER}
    if group:
        payload["supplier_group"] = group
    context["supplier"] = _create("Supplier", payload).name

def _build_project(context):
    context["project"] = _create(
        "Project", {"project_name": _DEMO_PROJECT, "company": context["company"]}
    ).name
    context["completed_project"] = _create(
        "Project",
        {
            "project_name": _DEMO_COMPLETED_PROJECT,
            "company": context["company"],
            "status": "Completed",
        },
    ).name

def _build_site(context):
    context["site"] = _create(
        "Site", {"site_name": _DEMO_SITE, "status": "Active"}
    ).name

def _build_building(context):
    company = context["company"]
    payload = {
        "building_name": _DEMO_BUILDING,
        "site": context["site"],
        "status": "Active",
        "accommodation_type": "Building",
        "total_capacity": 4,
        "company": company,
        "responsible_supervisor": DEMO_SUPERVISOR,
        "annual_rent": 60000,
        "annual_electricity": 12000,
        "is_procurement_store": 1,
    }
    cost_center = frappe.get_cached_value("Company", company, "cost_center") if company else None
    if cost_center:
        payload["default_cost_center"] = cost_center
        context["cost_center"] = cost_center
    context["building"] = _create("Building", payload).name

    partner = context["partner_company"]
    partner_payload = {
        "building_name": _DEMO_PARTNER_BUILDING,
        "site": context["site"],
        "status": "Active",
        "accommodation_type": "Building",
        "total_capacity": 2,
        "company": partner,
        "responsible_supervisor": DEMO_SUPERVISOR,
    }
    partner_cost_center = frappe.db.get_value("Company", partner, "cost_center")
    if partner_cost_center:
        partner_payload["default_cost_center"] = partner_cost_center
    context["partner_building"] = _create("Building", partner_payload).name

def _build_rooms(context):
    context["rooms"] = [
        _create(
            "Room",
            {
                "building": context["building"],
                "room_number": number,
                "floor": 1,
                "room_type": "Worker",
                "bed_capacity": 2,
                "status": "Available",
                "readiness_status": "Ready",
            },
        ).name
        for number in _DEMO_ROOMS
    ]

def _build_beds(context):
    context["beds"] = [
        _create(
            "Bed",
            {
                "room": room,
                "bed_code": "{0}-{1}".format(room, suffix),
                "status": "Available",
                "condition": "Good",
            },
        ).name
        for room in context["rooms"]
        for suffix in ("A", "B")
    ]

def _demo_gender():
    deadline = time.monotonic() + _GENDER_WAIT_SECONDS
    while True:
        existing = frappe.db.get_value("Gender", {"name": "Male"}) or frappe.db.get_value(
            "Gender", {}
        )
        if existing:
            return existing
        if time.monotonic() >= deadline:
            break
        time.sleep(1)
        frappe.db.rollback()
    doc = frappe.get_doc({"doctype": "Gender", "gender": "Male"})
    doc.insert(ignore_if_duplicate=True)
    return doc.name

def _build_employee(context):
    gender = context["gender"]
    context["employees"] = [
        _create(
            "Employee",
            {
                "first_name": first_name,
                "company": context["company"],
                "gender": gender,
                "date_of_birth": "1990-01-01",
                "date_of_joining": add_days(today(), -365),
                "status": "Active",
            },
        ).name
        for first_name in ("Majed Al-Shehri", "Yousef Al-Anazi", "Bandar Al-Subaie")
    ]
    context["employee"] = context["employees"][0]

def _build_custody_category(context):
    context["custody_category"] = _create(
        "Custody Asset Category", {"category_name": _DEMO_CATEGORY}
    ).name

def _build_custody_article(context):
    context["article"] = _create(
        "Custody Article",
        {"article_name": _DEMO_ARTICLE, "category": context["custody_category"]},
    ).name

def _build_utility_account(context):
    context["utility_account"] = _create(
        "Utility Account",
        {
            "building": context["building"],
            "utility_type": "Electricity",
            "account_number": "SEC-2205841",
            "status": "Active",
        },
    ).name

def _build_facility_asset(context):
    context["facility_asset"] = _create(
        "Facility Asset",
        {
            "asset_name": "Main Gate CCTV Camera",
            "asset_category": "CCTV Camera",
            "building": context["building"],
            "responsible_supervisor": DEMO_SUPERVISOR,
            "status": "Operational",
        },
    ).name

def _grant_demo_scope(context):
    grants = (
        (DEMO_FLEET_SUPERVISOR, "Project", context["project"]),
        (DEMO_SUPERVISOR, "Project", context["project"]),
        (DEMO_SUPERVISOR, "Building", context["building"]),
    )
    for user, allow, value in grants:
        if not value or not frappe.db.exists("User", user):
            continue
        if frappe.db.exists(
            "User Permission", {"user": user, "allow": allow, "for_value": value}
        ):
            continue
        frappe.get_doc(
            {
                "doctype": "User Permission",
                "user": user,
                "allow": allow,
                "for_value": value,
                "apply_to_all_doctypes": 1,
            }
        ).insert()


def _build_driver(context):
    context["driver"] = _create(
        "Salis Driver",
        {
            "full_name": "Hassan Al-Amri",
            "status": "Active",
            "project": context["project"],
        },
    ).name

def _build_vehicle(context):
    context["vehicle"] = _create(
        "Salis Vehicle",
        {
            "plate_number": "RUH 4521",
            "status": "Active",
            "planned_fuel_grade": "Petrol 91",
            "project": context["project"],
        },
    ).name

def _build_telecom_contract(context):
    contract = _create(
        "Telecom Contract",
        {
            "company": context["company"],
            "supplier": context["supplier"],
            "contract_start_date": add_days(today(), -180),
            "contract_end_date": add_days(today(), 185),
            "billing_frequency": "Monthly",
            "recurring_amount": 500,
            "currency": context["currency"],
        },
    )
    contract.submit()
    context["telecom_contract"] = contract.name

def _build_sim_cards(context):
    holder = context["employee"]
    context["sim_cards"] = [
        _create(
            "SIM Card",
            {
                "telecom_contract": context["telecom_contract"],
                "mobile_number": mobile,
                "iccid": iccid,
                "status": status,
                "current_custodian_type": custodian_type,
                "current_custodian_employee": employee,
                "current_cost_center": cost_center,
            },
        ).name
        for mobile, iccid, status, custodian_type, employee, cost_center in (
            ("0550000001", "8996605112345678901", "Assigned", "Employee", holder, context.get("cost_center")),
            ("0550000002", "8996605112345678902", "Assigned", "Employee", holder, context.get("cost_center")),
            ("0550000003", None, "Suspended", "Unassigned", None, None),
        )
    ]

def _build_assignment(context):
    assignment = _create(
        "Housing Assignment",
        {
            "party_type": "Employee",
            "party": context["employee"],
            "project": context["project"],
            "bed": context["beds"][0],
            "check_in_date": add_days(today(), -30),
            "assignment_type": "New Assignment",
            "stay_type": "Permanent",
        },
    )
    assignment.submit()
    context["assignment"] = assignment.name

    supplier_assignment = _create(
        "Housing Assignment",
        {
            "party_type": "Employee",
            "party": context["employees"][1],
            "project": context["completed_project"],
            "bed": context["beds"][1],
            "check_in_date": add_days(today(), -45),
            "assignment_type": "New Assignment",
            "stay_type": "Permanent",
            "is_external_supplier": 1,
            "billed_to_supplier": context["supplier"],
        },
    )
    supplier_assignment.submit()
    context["supplier_assignment"] = supplier_assignment.name

    leaver_assignment = _create(
        "Housing Assignment",
        {
            "party_type": "Employee",
            "party": context["employees"][2],
            "project": context["project"],
            "bed": context["beds"][2],
            "check_in_date": add_days(today(), -60),
            "assignment_type": "New Assignment",
            "stay_type": "Permanent",
        },
    )
    leaver_assignment.submit()
    context["leaver_assignment"] = leaver_assignment.name

def _build_maintenance_request(context):
    context["maintenance_request"] = _create(
        "Maintenance Request",
        {
            "building": context["building"],
            "room": context["rooms"][0],
            "reported_by": DEMO_OWNER,
            "issue_type": "Air Conditioning",
            "priority": "Medium",
            "status": "Open",
            "issue_description": "Air conditioning in the demo room is not cooling.",
            "company": context["company"],
        },
    ).name

def _build_cleaning_log(context):
    context["cleaning_log"] = _create(
        "Cleaning Log",
        {
            "building": context["building"],
            "cleaning_date": today(),
            "cleaner_type": "Internal Employee",
            "room_details": [
                {"room": context["rooms"][0], "room_status": "Cleaned", "cleaned": 1},
                {
                    "room": context["rooms"][1],
                    "room_status": "Skipped",
                    "cleaned": 0,
                    "skip_reason": "Awaiting next cleaning round",
                },
            ],
        },
    ).name

def _build_lease(context):
    lease = _create(
        "Lease",
        {
            "company": context["company"],
            "building": context["building"],
            "lease_start_date": add_days(today(), -60),
            "lease_end_date": add_days(today(), 25),
            "rent_amount": 5000,
            "billing_cycle": "Monthly",
            "first_payment_date": add_days(today(), -60),
        },
    )
    _walk_workflow("Lease", lease.name, ("Submit for Approval", "Approve"))
    context["lease"] = lease.name

def _build_utility_bill(context):
    bill = _create(
        "Utility Bill Entry",
        {
            "utility_account": context["utility_account"],
            "company": context["company"],
            "billing_period_from": add_days(today(), -30),
            "billing_period_to": add_days(today(), -1),
            "bill_amount": 1500,
            "consumption_units": 900,
        },
    )
    _walk_workflow(
        "Utility Bill Entry", bill.name, ("Submit for Approval", "Approve")
    )
    context["utility_bill"] = bill.name

def _build_damage_assessment(context):
    context["damage_assessment"] = _create(
        "Custody Damage Assessment",
        {
            "assessment_date": today(),
            "building": context["building"],
            "party_type": "Employee",
            "party": context["employees"][2],
            "employee": context["employees"][2],
            "items": [
                {
                    "article": context["article"],
                    "damage_description": "Torn mattress cover, foam exposed",
                    "estimated_replacement_cost": 150,
                }
            ],
        },
    ).name

def _build_audit_plan(context):
    context["audit_plan"] = _create(
        "Audit Remediation Plan",
        {
            "client_project": context["project"],
            "audit_received_date": add_days(today(), -10),
            "remediation_deadline": add_days(today(), 20),
            "buildings_in_scope": [{"building": context["building"]}],
            "remediation_items": [
                {
                    "finding_description": "Fire extinguisher inspection tag expired",
                    "remediation_action": "Replace the expired extinguisher",
                    "due_date": add_days(today(), -5),
                    "status": "Open",
                },
                {
                    "finding_description": "Room number signage missing",
                    "remediation_action": "Install room signage",
                    "due_date": add_days(today(), 15),
                    "status": "In Progress",
                },
            ],
        },
    ).name

def _build_asset_movement(context):
    context["asset_movement"] = _create(
        "Facility Asset Movement",
        {
            "movement_date": today(),
            "facility_asset": context["facility_asset"],
            "movement_category": "Intercompany Temporary",
            "movement_reason": "Reallocation",
            "to_building": context["partner_building"],
            "release_approved_by": DEMO_OWNER,
            "receiving_confirmed_by": DEMO_SUPERVISOR,
        },
    ).name

def _build_depreciation_snapshot(context):
    snapshot = _create(
        "Operational Depreciation Snapshot",
        {
            "snapshot_date": today(),
            "building": context["building"],
            "items": [
                {
                    "article": context["article"],
                    "original_cost": 1200,
                    "age_years": 2,
                }
            ],
        },
    )
    snapshot.submit()
    context["depreciation_snapshot"] = snapshot.name

def _build_checkout(context):
    checkout = _create(
        "Housing Checkout",
        {
            "assignment": context["leaver_assignment"],
            "checkout_date": today(),
            "checkout_reason": "End of Contract",
            "custody_return_items": [
                {
                    "article": context["article"],
                    "return_status": "Damaged",
                    "quantity_returned": 0,
                }
            ],
        },
    )
    checkout.submit()
    context["checkout"] = checkout.name

def _build_driver_attendance(context):
    context["driver_attendance"] = _create(
        "Driver Attendance",
        {
            "driver": context["driver"],
            "attendance_date": today(),
            "status": "Present",
            "check_in": f"{today()} 07:00:00",
            "check_out": f"{today()} 15:00:00",
        },
    ).name

def _build_driver_clearance(context):
    clearance = _create(
        "Driver Clearance",
        {
            "driver": context["driver"],
            "clearance_reason": "End of Assignment",
            "status": "Open",
        },
    )
    _walk_workflow(
        "Driver Clearance",
        clearance.name,
        ("Start Processing",),
        user=DEMO_FLEET_SUPERVISOR,
    )
    context["driver_clearance"] = clearance.name

def _build_vehicle_snapshots(context):
    weekly_vehicle_utilisation_snapshot()

def _build_accommodation_ledger(context):
    allocate_building_accommodation_cost(context["building"], today())

def _build_qr_location(context):
    context["qr_location"] = _create(
        "QR Location",
        {
            "poster_title": "{0} — Main Entrance".format(context["building"]),
            "is_active": 1,
            "room": context["rooms"][0],
        },
    ).name

def _build_custody_handover(context):
    context["custody_handover"] = _create(
        "Custody Handover",
        {
            "handover_date": today(),
            "from_building": context["building"],
            "to_building": context["partner_building"],
            "procurement_supervisor": DEMO_SUPERVISOR,
            "receiving_supervisor": DEMO_APPROVER,
            "items": [
                {
                    "item_type": "Custody Article",
                    "item": context["article"],
                    "qty": 2,
                    "condition_on_transfer": "Good",
                }
            ],
        },
    ).name

_HANDOVER_CHECKS = ("Spare tyre", "Jack and wrench", "First aid kit", "Fire extinguisher")

def _build_handover_checklist_template(context):
    context["handover_template"] = _create(
        "Vehicle Handover Checklist Template",
        {
            "template_name": "Vehicle Handover Checklist",
            "is_active": 1,
            "items": [{"check_item": item} for item in _HANDOVER_CHECKS],
        },
    ).name

def _build_vehicle_assignment(context):
    assignment = _create(
        "Vehicle Assignment",
        {
            "vehicle": context["vehicle"],
            "driver": context["driver"],
            "start_date": today(),
            "status": "Active",
        },
    )
    assignment.submit()
    context["vehicle_assignment"] = assignment.name

def _build_vehicle_handover(context):
    context["vehicle_handover"] = _create(
        "Vehicle Handover",
        {
            "vehicle": context["vehicle"],
            "direction": "Receipt",
            "vehicle_assignment": context["vehicle_assignment"],
            "checklist_template": context["handover_template"],
            "to_driver": context["driver"],
            "handover_date": today(),
            "fuel_level": "Half",
            "discrepancy_status": "Clean",
            "handover_check_items": [
                {"check_item": item, "ok": 1} for item in _HANDOVER_CHECKS
            ],
        },
    ).name

def _build_vehicle_incident(context):
    context["vehicle_incident"] = _create(
        "Vehicle Incident",
        {
            "incident_type": "Accident",
            "vehicle": context["vehicle"],
            "incident_date": today(),
            "injuries": "No Injuries",
            "status": "Open",
            "description": "Minor rear bumper contact while reversing at the site gate. "
            "No third party involved and the vehicle remained drivable.",
        },
    ).name

def _build_vehicle_write_off(context):
    evidence = frappe.new_doc("File")
    evidence.update(
        {
            "file_name": "demo-write-off-evidence.txt",
            "content": "Vehicle damage evidence photo (placeholder).",
            "is_private": 0,
        }
    )
    evidence.insert()
    name = _create(
        "Vehicle Damage Write-Off",
        {
            "vehicle": context["vehicle"],
            "evidence": evidence.file_url,
            "recommended_action": "Repair",
            "status": "Open",
        },
    ).name
    evidence.db_set(
        {"attached_to_doctype": "Vehicle Damage Write-Off", "attached_to_name": name},
        update_modified=False,
    )
    _walk_workflow(
        "Vehicle Damage Write-Off",
        name,
        ("Submit for Review", "Authorize (Regional)"),
        user=DEMO_FLEET_SUPERVISOR,
    )
    _walk_workflow("Vehicle Damage Write-Off", name, ("Close",), user=DEMO_FLEET_MANAGER)
    context["vehicle_write_off"] = name

def _build_subcontractor_contract(context):
    name = _create(
        "Subcontractor Service Contract",
        {
            "supplier": context["supplier"],
            "service_type": "Pest Control",
            "contract_start_date": today(),
            "contract_end_date": add_days(today(), 365),
            "visit_frequency": "Monthly",
            "status": "Draft",
            "covered_buildings": [{"building": context["building"]}],
        },
    ).name
    _walk_workflow("Subcontractor Service Contract", name, ("Submit for Approval", "Approve"))
    context["subcontractor_contract"] = name

def _build_subcontractor_order(context):
    context["subcontractor_order"] = _create(
        "Subcontractor Service Order",
        {
            "building": context["building"],
            "scheduled_date": today(),
            "contract": context["subcontractor_contract"],
            "status": "Scheduled",
            "service_items": [
                {"description": "Monthly pest-control visit", "qty": 1, "rate": 350},
            ],
        },
    ).name

def _build_rental_office(context):
    context["rental_office"] = _create(
        "Rental Office",
        {"office_name": _DEMO_RENTAL_OFFICE, "status": "Active"},
    ).name

def _build_goods_receipt(context):
    receipt = _create(
        "Goods Receipt",
        {
            "receipt_date": today(),
            "intake_building": context["building"],
            "procurement_supervisor": DEMO_SUPERVISOR,
            "status": "Draft",
            "items": [
                {
                    "item_type": "Custody Article",
                    "item": context["article"],
                    "qty": 10,
                    "condition_on_transfer": "New",
                }
            ],
        },
    )
    context["goods_receipt"] = receipt.name

def _build_material_transfer(context):
    context["material_transfer"] = _create(
        "Material Transfer",
        {
            "transfer_date": today(),
            "from_building": context["building"],
            "to_building": context["partner_building"],
            "status": "Draft",
            "items": [
                {
                    "item_type": "Custody Article",
                    "item": context["article"],
                    "qty": 3,
                    "condition_on_transfer": "Good",
                }
            ],
        },
    ).name

def _build_custody_issue(context):
    context["custody_issue"] = _create(
        "Custody Issue",
        {
            "issue_date": today(),
            "building": context["building"],
            "party_type": "Employee",
            "party": context["employee"],
            "status": "Draft",
            "items": [
                {"article": context["article"], "qty": 2, "condition_on_issue": "Good"},
            ],
        },
    ).name

def _build_work_order(context):
    context["work_order"] = _create(
        "Maintenance Work Order",
        {
            "maintenance_request": context["maintenance_request"],
            "planned_start_date": today(),
            "status": "Planned",
            "work_description": "<p>Replace the failed corridor light fitting and test the "
            "circuit before handing the room back.</p>",
        },
    ).name

def _build_safety_incident(context):
    context["safety_incident"] = _create(
        "Safety Incident",
        {
            "incident_datetime": frappe.utils.now_datetime(),
            "building": context["building"],
            "incident_type": "Electrical",
            "severity": "Medium",
            "status": "Open",
            "description": "Exposed wiring found in the corridor junction box during the "
            "weekly round. Power isolated and the area cordoned off.",
        },
    ).name

def _build_safety_round(context):
    context["safety_round"] = _create(
        "Safety Round",
        {
            "building": context["building"],
            "round_date": today(),
            "cadence": "Weekly",
            "overall_result": "Needs Attention",
        },
    ).name

def _build_fuel_request(context):
    request = _create(
        "Fuel Request",
        {
            "request_type": "Standard",
            "vehicle": context["vehicle"],
            "requested_litres": 40,
            "status": "Pending",
        },
    )
    _walk_workflow(
        "Fuel Request", request.name, ("Approve", "Complete"), user=DEMO_FLEET_MANAGER
    )
    context["fuel_request"] = request.name

def _build_fuel_claim(context):
    claim = _create(
        "Fuel Claim",
        {
            "project": context["project"],
            "vehicle": context["vehicle"],
            "period_month": today()[:7],
            "claimed_litres": 320,
            "status": "Draft",
        },
    )
    _walk_workflow(
        "Fuel Claim",
        claim.name,
        ("Submit to Movement", "Reconcile", "Approve", "Close"),
        user=DEMO_FLEET_MANAGER,
    )
    context["fuel_claim"] = claim.name

def _build_passenger_manifest(context):
    context["passenger_manifest"] = _create(
        "Passenger Manifest",
        {
            "passengers": [{"employee": context["employee"]}],
        },
    ).name

def _build_rental_settlement(context):
    settlement = _create(
        "Rental Settlement",
        {
            "rental_office": context["rental_office"],
            "period_month": today()[:7],
            "status": "Draft",
            "vehicles": [
                {
                    "vehicle": context["vehicle"],
                    "rental_start_date": add_days(today(), -30),
                    "rental_end_date": today(),
                    "days": 30,
                    "daily_rate": 120,
                    "amount": 3600,
                }
            ],
        },
    )
    _walk_workflow(
        "Rental Settlement",
        settlement.name,
        ("Reconcile", "Approve"),
        user=DEMO_FLEET_MANAGER,
    )
    context["salis_payment_request"] = frappe.get_doc(
        "Rental Settlement", settlement.name
    ).create_payment_request()
    _walk_workflow(
        "Rental Settlement", settlement.name, ("Mark Paid",), user=DEMO_APPROVER
    )
    context["rental_settlement"] = settlement.name

def _build_route_template(context):
    context["route_template"] = _create(
        "Route Template",
        {
            "template_name": "Main Gate Shuttle Route",
            "route_type": "Pickup",
            "stops": [{"stop_name": "{0} — Main Entrance".format(context["building"])}],
        },
    ).name

def _build_work_shift(context):
    context["work_shift"] = _create(
        "Work Shift",
        {
            "shift_name": "Morning Shift",
            "start_time": "06:00:00",
            "end_time": "14:00:00",
            "applicable_days": [{"day_of_week": "Sunday"}],
        },
    ).name

def _build_route_assignment(context):
    assignment = _create(
        "Route Assignment",
        {
            "route_template": context["route_template"],
            "work_shift": context["work_shift"],
            "project": context["project"],
            "driver": context["driver"],
            "vehicle": context["vehicle"],
            "route_supervisor": DEMO_FLEET_SUPERVISOR,
            "starts_on": today(),
        },
    )
    _walk_workflow("Route Assignment", assignment.name, ("Approve",), user=DEMO_FLEET_MANAGER)
    context["route_assignment"] = assignment.name

def _build_dispatch_trip(context):
    trip = _create(
        "Dispatch Trip",
        {
            "vehicle": context["vehicle"],
            "driver": context["driver"],
            "project": context["project"],
            "trip_date": today(),
        },
    )
    _walk_workflow("Dispatch Trip", trip.name, ("Dispatch",), user=DEMO_FLEET_SUPERVISOR)
    context["dispatch_trip"] = trip.name

def _build_transport_request(context):
    request = _create(
        "Transport Request",
        {
            "service_line": "Site Transport",
            "project": context["project"],
            "accommodation_building": context["building"],
            "passenger_count": 4,
        },
    )
    _walk_workflow(
        "Transport Request",
        request.name,
        ("Validate", "Authorize (Regional)", "Schedule", "Confirm Fulfilment"),
        user=DEMO_FLEET_SUPERVISOR,
    )
    context["transport_request"] = request.name

def _build_fuel_exception_case(context):
    case = _create(
        "Fuel Exception Case",
        {
            "vehicle": context["vehicle"],
            "driver": context["driver"],
            "exception_type": "Over-Consumption",
            "description": (
                "Fuel consumption exceeds the vehicle's planned average "
                "for the period."
            ),
            "evidence_notes": "Investigation notes: pump receipt matches the trip log.",
        },
    )
    _walk_workflow(
        "Fuel Exception Case",
        case.name,
        ("Start Investigation", "Resolve", "Close"),
        user=DEMO_FLEET_MANAGER,
    )
    context["fuel_exception_case"] = case.name

def _build_movement_cost_recovery(context):
    evidence = frappe.new_doc("File")
    evidence.update(
        {
            "file_name": "demo-cost-recovery-evidence.txt",
            "content": "Cost recovery evidence photo (placeholder).",
            "is_private": 0,
        }
    )
    evidence.insert()
    recovery = _create(
        "Movement Cost Recovery",
        {
            "recovery_type": "Vehicle Damage",
            "vehicle": context["vehicle"],
            "driver": context["driver"],
            "amount": 500,
            "acknowledgement_received": 1,
            "basis_evidence": evidence.file_url,
        },
    )
    evidence.db_set(
        {"attached_to_doctype": "Movement Cost Recovery", "attached_to_name": recovery.name},
        update_modified=False,
    )
    _walk_workflow(
        "Movement Cost Recovery",
        recovery.name,
        ("Approve", "Recover"),
        user=DEMO_FLEET_MANAGER,
    )
    context["movement_cost_recovery"] = recovery.name

def _build_movement_cost_transfer(context):
    transfer = _create(
        "Movement Cost Transfer",
        {
            "transfer_type": "Fuel",
            "amount": 300,
            "from_project": context["project"],
            "to_project": context["completed_project"],
        },
    )
    _walk_workflow(
        "Movement Cost Transfer",
        transfer.name,
        ("Submit for Approval", "Approve", "Post (memo)"),
        user=DEMO_FLEET_MANAGER,
    )
    context["movement_cost_transfer"] = transfer.name

def _build_salis_payment_request(context):
    name = context["salis_payment_request"]
    _walk_workflow(
        "Salis Payment Request", name, ("Submit to Finance",), user=DEMO_FLEET_MANAGER
    )
    _walk_workflow(
        "Salis Payment Request", name, ("Approve (Finance)", "Mark Paid"), user=DEMO_APPROVER
    )

_BUILD_STEPS = (
    ("Company", _build_partner_company),
    ("Supplier", _build_supplier),
    ("Project", _build_project),
    ("Site", _build_site),
    ("Building", _build_building),
    ("Room", _build_rooms),
    ("Bed", _build_beds),
    ("Employee", _build_employee),
    ("Custody Asset Category", _build_custody_category),
    ("Custody Article", _build_custody_article),
    ("Utility Account", _build_utility_account),
    ("Facility Asset", _build_facility_asset),
    ("User Permission", _grant_demo_scope),
    ("Salis Driver", _build_driver),
    ("Salis Vehicle", _build_vehicle),
    ("Telecom Contract", _build_telecom_contract),
    ("SIM Card", _build_sim_cards),
    ("Housing Assignment", _build_assignment),
    ("Maintenance Request", _build_maintenance_request),
    ("Cleaning Log", _build_cleaning_log),
    ("Lease", _build_lease),
    ("Utility Bill Entry", _build_utility_bill),
    ("Custody Damage Assessment", _build_damage_assessment),
    ("Audit Remediation Plan", _build_audit_plan),
    ("Facility Asset Movement", _build_asset_movement),
    ("Operational Depreciation Snapshot", _build_depreciation_snapshot),
    ("Housing Checkout", _build_checkout),
    ("Driver Attendance", _build_driver_attendance),
    ("Driver Clearance", _build_driver_clearance),
    ("Vehicle Utilisation Snapshot", _build_vehicle_snapshots),
    ("Accommodation Ledger", _build_accommodation_ledger),
    ("QR Location", _build_qr_location),
    ("Custody Handover", _build_custody_handover),
    ("Vehicle Handover Checklist Template", _build_handover_checklist_template),
    ("Vehicle Assignment", _build_vehicle_assignment),
    ("Vehicle Handover", _build_vehicle_handover),
    ("Vehicle Incident", _build_vehicle_incident),
    ("Vehicle Damage Write-Off", _build_vehicle_write_off),
    ("Subcontractor Service Contract", _build_subcontractor_contract),
    ("Subcontractor Service Order", _build_subcontractor_order),
    ("Rental Office", _build_rental_office),
    ("Goods Receipt", _build_goods_receipt),
    ("Material Transfer", _build_material_transfer),
    ("Custody Issue", _build_custody_issue),
    ("Maintenance Work Order", _build_work_order),
    ("Safety Incident", _build_safety_incident),
    ("Safety Round", _build_safety_round),
    ("Fuel Request", _build_fuel_request),
    ("Fuel Claim", _build_fuel_claim),
    ("Passenger Manifest", _build_passenger_manifest),
    ("Rental Settlement", _build_rental_settlement),
    ("Route Template", _build_route_template),
    ("Work Shift", _build_work_shift),
    ("Route Assignment", _build_route_assignment),
    ("Dispatch Trip", _build_dispatch_trip),
    ("Transport Request", _build_transport_request),
    ("Fuel Exception Case", _build_fuel_exception_case),
    ("Movement Cost Recovery", _build_movement_cost_recovery),
    ("Movement Cost Transfer", _build_movement_cost_transfer),
    ("Salis Payment Request", _build_salis_payment_request),
)
