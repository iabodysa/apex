# Copyright (c) 2026, afmcoltd
"""Setup-wizard demo data — one coherent accommodation scenario, and its removal.

The scenario is built by a DEDICATED DEMO USER, so ``owner`` is the removal key:
every row the build creates is selected back by that one column and nothing else.
No name pattern, no date window, no "everything in this DocType".
"""

from __future__ import annotations

import random
import string

import frappe
from frappe import _
from frappe.utils import add_days, today

from apex.apex_core.utils.system_write import system_insert

DEMO_ARG = "apex_setup_demo"

DEMO_OWNER = "demo.manager@apex.example"
DEMO_SUPERVISOR = "demo.supervisor@apex.example"
DEMO_APPROVER = "demo.approver@apex.example"
DEMO_USERS = (DEMO_OWNER, DEMO_SUPERVISOR, DEMO_APPROVER)

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
)

_DEMO_SITE = "Demo Housing Site"
_DEMO_BUILDING = "Demo Building A"
_DEMO_PARTNER_BUILDING = "Demo Building B"
_DEMO_PROJECT = "Demo Residential Project"
_DEMO_COMPLETED_PROJECT = "Demo Completed Project"
_DEMO_PARTNER_COMPANY = "Demo Partner Company"
_DEMO_SUPPLIER = "Demo Accommodation Supplier"
_DEMO_CATEGORY = "Demo Custody Category"
_DEMO_ARTICLE = "Demo Custody Article"
_DEMO_ROOMS = ("DEMO-101", "DEMO-102")


def setup_demo(args=None):
    """`setup_wizard_complete` hook — queue the demo build if the operator asked."""
    args = frappe._dict(args or {})
    if not args.get(DEMO_ARG):
        return
    frappe.enqueue(build_demo_data, enqueue_after_commit=True, at_front=True)


def boot_demo(bootinfo):
    """`extend_bootinfo` hook — flag whether this site carries removable demo data.

    Derived from the demo user rather than stored anywhere: the user IS the
    removal key, so the flag cannot drift from what the removal can act on. The
    build creates that user and the removal deletes it, which sets and clears the
    flag with no third place to keep in step."""
    bootinfo.apex_demo_data = bool(frappe.db.exists("User", DEMO_OWNER))


def build_demo_data():
    """Build the demo scenario as the demo user. Background job — never inline."""
    if frappe.db.exists("User", DEMO_OWNER):
        return

    _create_demo_users()
    previous_user = frappe.session.user
    try:
        frappe.set_user(DEMO_OWNER)
        context = {}
        for _doctype, step in _BUILD_STEPS:
            step(context)
    finally:
        frappe.set_user(previous_user)

    _scope_supervisor(context.get("building"))
    frappe.cache.delete_keys("bootinfo")


@frappe.whitelist()
def clear_demo_data():
    """Remove every row the demo build created, and nothing else.

    Returns ``{"deleted": int, "residue": [...]}``. Residue is reported, never
    hidden: a row that refuses to go leaves the rest of the clear standing."""
    frappe.only_for("System Manager")
    if not frappe.db.exists("User", DEMO_OWNER):
        frappe.throw(_("This site has no Apex demo data to remove."))

    deleted = 0
    residue = []
    deleted, residue = _remove_user_permissions(deleted, residue)
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
    """Cancel-then-delete one record inside its own savepoint.

    Returns None on success, or the error text of a record that survived.
    """
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
        frappe.delete_doc(
            doctype,
            name,
            ignore_permissions=True,
            delete_permanently=True,
        )
    except Exception as exc:
        _release(save_point, undo=True)
        frappe.clear_last_message()
        return str(exc) or exc.__class__.__name__
    _release(save_point)
    return None


def _release(save_point, undo=False):
    """Discard a savepoint, tolerating one that is already gone.

    MariaDB drops every savepoint when anything in the transaction commits, and a
    delete path may commit for its own reasons. Letting that surface would abort
    the whole clear from inside the very handler meant to contain one bad record."""
    try:
        if undo:
            frappe.db.rollback(save_point=save_point)
        else:
            frappe.db.release_savepoint(save_point)
    except Exception:
        frappe.clear_last_message()


def _remove_user_permissions(deleted, residue):
    """Drop the demo users' User Permissions before the records they point at."""
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
    """Delete the demo users, last of all.

    Skipped entirely while any record survives: the demo user IS the removal key,
    so dropping it on top of residue would leave the site holding demo data that
    nothing can select any more. Keeping the user keeps the boot flag set and the
    action re-runnable once the blocker is cleared.
    """
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
    """Shows a success message when nothing is left, or lists residue rows on partial removal."""
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
    """The owner key and the scoped persona. Created as the installing user, so
    they are never swept by the owner filter and are deleted explicitly instead."""
    for email, full_name, roles in (
        (DEMO_OWNER, "Demo Manager", ("System Manager",)),
        (DEMO_SUPERVISOR, "Demo Supervisor", ("Resident Supervisor",)),
        (DEMO_APPROVER, "Demo Approver", ("Accommodation Manager", "Finance Manager")),
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
        ).insert(ignore_permissions=True)
        installed = [
            role for role in roles if frappe.db.exists("Role", {"name": role})
        ]
        if installed:
            user.add_roles(*installed)


def _scope_supervisor(building):
    """The demo supervisor sees the demo estate only — the scope axis every
    building-scoped role reads (apex/habitat/permissions.py)."""
    if not building:
        return
    frappe.get_doc(
        {
            "doctype": "User Permission",
            "user": DEMO_SUPERVISOR,
            "allow": "Building",
            "for_value": building,
        }
    ).insert(ignore_permissions=True)


def _create(doctype, payload):
    """Insert one demo record, refusing any DocType the removal would not reach."""
    if doctype not in set(DEMO_DOCTYPES):
        frappe.throw(
            _("{0} is not a demo DocType; the demo removal would never clear it.").format(
                doctype
            )
        )
    doc = frappe.get_doc(dict(payload, doctype=doctype))
    system_insert(doc)
    return doc


def _company():
    """Returns the global default company, or any existing company as a fallback."""
    return frappe.defaults.get_global_default("company") or frappe.db.get_value("Company", {})


def _walk_workflow(doctype, name, actions):
    """Applies a sequence of workflow actions to a document while impersonating the demo approver."""
    from frappe.model.workflow import apply_workflow

    previous_user = frappe.session.user
    frappe.set_user(DEMO_APPROVER)
    try:
        doc = frappe.get_doc(doctype, name)
        for action in actions:
            apply_workflow(doc, action)
    finally:
        frappe.set_user(previous_user)


def _build_partner_company(context):
    """Creates the demo partner Company, reusing the real company's currency and country."""
    context["company"] = _company()
    currency = (
        frappe.db.get_value("Company", context["company"], "default_currency")
        if context["company"]
        else None
    )
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
            "default_currency": currency or "SAR",
            "country": country or "Saudi Arabia",
        },
    )
    context["partner_company"] = partner.name
    context["currency"] = currency or "SAR"


def _build_supplier(context):
    """Creates the demo accommodation Supplier record."""
    group = frappe.db.get_value(
        "Supplier Group", {"name": "All Supplier Groups"}
    ) or frappe.db.get_value("Supplier Group", {})
    payload = {"supplier_name": _DEMO_SUPPLIER}
    if group:
        payload["supplier_group"] = group
    context["supplier"] = _create("Supplier", payload).name


def _build_project(context):
    """Creates the demo active Project and a demo completed Project."""
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
    """Creates the demo housing Site."""
    context["site"] = _create(
        "Site", {"site_name": _DEMO_SITE, "status": "Active"}
    ).name


def _build_building(context):
    """Creates the demo building and its partner-company counterpart building."""
    company = context["company"]
    payload = {
        "building_name": _DEMO_BUILDING,
        "site": context["site"],
        "status": "Active",
        "accommodation_type": "Building",
        "total_capacity": 4,
        "company": company,
        "responsible_facility_supervisor": DEMO_SUPERVISOR,
        "annual_rent": 60000,
        "annual_electricity": 12000,
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
        "responsible_facility_supervisor": DEMO_SUPERVISOR,
    }
    partner_cost_center = frappe.db.get_value("Company", partner, "cost_center")
    if partner_cost_center:
        partner_payload["default_cost_center"] = partner_cost_center
    context["partner_building"] = _create("Building", partner_payload).name


def _build_rooms(context):
    """Creates the two demo rooms inside the demo building."""
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
    """Creates two demo beds for each demo room."""
    context["beds"] = [
        _create(
            "Bed",
            {
                "room": room,
                "building": context["building"],
                "bed_code": "{0}-{1}".format(room, suffix),
                "status": "Available",
                "condition": "Good",
            },
        ).name
        for room in context["rooms"]
        for suffix in ("A", "B")
    ]


def _build_employee(context):
    """Creates the demo resident, supplier-worker, and leaver Employee records."""
    context["employees"] = [
        _create(
            "Employee",
            {
                "first_name": first_name,
                "company": context["company"],
                "gender": "Male",
                "date_of_birth": "1990-01-01",
                "date_of_joining": add_days(today(), -365),
                "status": "Active",
            },
        ).name
        for first_name in ("Demo Resident", "Demo Supplier Worker", "Demo Leaver")
    ]
    context["employee"] = context["employees"][0]


def _build_custody_category(context):
    """Creates the demo Custody Asset Category."""
    context["custody_category"] = _create(
        "Custody Asset Category", {"category_name": _DEMO_CATEGORY}
    ).name


def _build_custody_article(context):
    """Creates the demo Custody Article under the demo category."""
    context["article"] = _create(
        "Custody Article",
        {"article_name": _DEMO_ARTICLE, "category": context["custody_category"]},
    ).name


def _build_utility_account(context):
    """Creates the demo electricity Utility Account for the demo building."""
    context["utility_account"] = _create(
        "Utility Account",
        {
            "building": context["building"],
            "utility_type": "Electricity",
            "account_number": "DEMO-UTIL-0001",
            "status": "Active",
        },
    ).name


def _build_facility_asset(context):
    """Creates the demo CCTV Facility Asset for the demo building."""
    context["facility_asset"] = _create(
        "Facility Asset",
        {
            "asset_name": "Demo CCTV Camera",
            "asset_category": "CCTV Camera",
            "building": context["building"],
            "responsible_supervisor": DEMO_SUPERVISOR,
            "status": "Operational",
        },
    ).name


def _build_driver(context):
    """Creates the demo Salis Driver."""
    context["driver"] = _create(
        "Salis Driver", {"full_name": "Demo Driver", "status": "Active"}
    ).name


def _build_vehicle(context):
    """Creates the demo Salis Vehicle."""
    context["vehicle"] = _create(
        "Salis Vehicle", {"plate_number": "DEMO-1234", "status": "Active"}
    ).name


def _build_telecom_contract(context):
    """Creates the demo Telecom Contract for the demo supplier."""
    context["telecom_contract"] = _create(
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
    ).name


def _build_sim_cards(context):
    """Creates two assigned SIM Cards and one suspended SIM Card for the demo employee."""
    holder = context["employee"]
    context["sim_cards"] = [
        _create(
            "SIM Card",
            {
                "company": context["company"],
                "telecom_contract": context["telecom_contract"],
                "supplier": context["supplier"],
                "mobile_number": mobile,
                "iccid": iccid,
                "status": status,
                "current_custodian_type": custodian_type,
                "current_custodian_employee": employee,
                "current_cost_center": cost_center,
            },
        ).name
        for mobile, iccid, status, custodian_type, employee, cost_center in (
            ("0550000001", "DEMO-ICCID-0001", "Assigned", "Employee", holder, context.get("cost_center")),
            ("0550000002", "DEMO-ICCID-0002", "Assigned", "Employee", holder, context.get("cost_center")),
            ("0550000003", None, "Suspended", "Unassigned", None, None),
        )
    ]


def _build_assignment(context):
    """The one SUBMITTED row. on_submit marks the bed Occupied and recalculates
    the building's occupancy; on_cancel puts both back — which is why the removal
    cancels before it deletes."""
    assignment = _create(
        "Housing Assignment",
        {
            "party_type": "Employee",
            "party": context["employee"],
            "project": context["project"],
            "building": context["building"],
            "room": context["rooms"][0],
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
            "building": context["building"],
            "room": context["rooms"][0],
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
            "building": context["building"],
            "room": context["rooms"][1],
            "bed": context["beds"][2],
            "check_in_date": add_days(today(), -60),
            "assignment_type": "New Assignment",
            "stay_type": "Permanent",
        },
    )
    leaver_assignment.submit()
    context["leaver_assignment"] = leaver_assignment.name


def _build_maintenance_request(context):
    """Creates the demo open Maintenance Request for an air conditioning issue."""
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
    """Creates the demo Cleaning Log with one room cleaned and one skipped."""
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
                    "skip_reason": "Demo pending round",
                },
            ],
        },
    ).name


def _build_lease(context):
    """Creates the demo Lease and drives it through Submit for Approval and Approve."""
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
    """Creates the demo Utility Bill Entry and drives it through Submit for Approval and Approve."""
    bill = _create(
        "Utility Bill Entry",
        {
            "utility_account": context["utility_account"],
            "company": context["company"],
            "building": context["building"],
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
    """Creates the demo Custody Damage Assessment for a damaged mattress."""
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
                    "damage_description": "Demo damaged mattress",
                    "estimated_replacement_cost": 150,
                }
            ],
        },
    ).name


def _build_audit_plan(context):
    """Creates the demo Audit Remediation Plan with two open findings."""
    context["audit_plan"] = _create(
        "Audit Remediation Plan",
        {
            "client_project": context["project"],
            "audit_received_date": add_days(today(), -10),
            "remediation_deadline": add_days(today(), 20),
            "buildings_in_scope": [{"building": context["building"]}],
            "remediation_items": [
                {
                    "finding_description": "Demo audit finding: fire extinguisher expired",
                    "remediation_action": "Replace the expired extinguisher",
                    "due_date": add_days(today(), -5),
                    "status": "Open",
                },
                {
                    "finding_description": "Demo audit finding: room signage missing",
                    "remediation_action": "Install room signage",
                    "due_date": add_days(today(), 15),
                    "status": "In Progress",
                },
            ],
        },
    ).name


def _build_asset_movement(context):
    """Creates the demo intercompany Facility Asset Movement between the demo buildings."""
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
    """Creates and submits the demo Operational Depreciation Snapshot."""
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
    """Creates and submits the demo Housing Checkout with one damaged custody item."""
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
    """Creates the demo present Driver Attendance record."""
    context["driver_attendance"] = _create(
        "Driver Attendance",
        {
            "driver": context["driver"],
            "attendance_date": today(),
            "status": "Present",
            "worked_hours": 8,
        },
    ).name


def _build_driver_clearance(context):
    """Creates the demo open Driver Clearance record."""
    context["driver_clearance"] = _create(
        "Driver Clearance",
        {
            "driver": context["driver"],
            "clearance_reason": "End of Assignment",
            "status": "Open",
        },
    ).name


def _build_vehicle_snapshots(context):
    """Runs the weekly vehicle utilisation snapshot job to populate demo data."""
    from apex.salis.utilisation_engine import weekly_vehicle_utilisation_snapshot

    weekly_vehicle_utilisation_snapshot()


def _build_accommodation_ledger(context):
    """Allocates today's accommodation cost for the demo building."""
    from apex.habitat.tasks.cost import allocate_building_accommodation_cost

    allocate_building_accommodation_cost(context["building"], today())


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
)
