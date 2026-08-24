# Copyright (c) 2026, AFMCO and contributors

from __future__ import annotations
import frappe
from frappe.utils import today

try:
    from frappe.tests.utils import FrappeTestCase
    _UnitTestCase = FrappeTestCase
except Exception:
    FrappeTestCase = object
    _UnitTestCase = object

class ApexHabitatTestCase(FrappeTestCase):
    pass

class ApexHabitatUnitTestCase(_UnitTestCase):
    pass

class ExistsShortCircuitDB:

    def __init__(self, present=None):
        self.present = {} if present is None else present
        self.queried = []

    def names(self, doctype):
        return self.present.get(doctype, set())

    def exists(self, doctype, key=None, **_kwargs):
        if isinstance(key, str) and key == doctype and doctype != "DocType":
            return key
        self.queried.append((doctype, key))
        rows = self.names(doctype)
        if isinstance(key, dict):
            return next((value for value in key.values() if value in rows), None)
        return key if key in rows else None

test_ignore = [
    "Additional Salary",
    "Asset",
    "Asset Movement",
    "Company",
    "Cost Center",
    "Currency",
    "Employee",
    "Item",
    "Payment Entry",
    "Project",
    "Purchase Invoice",
    "Role",
    "Salary Component",
    "Supplier",
    "User",
]

def make_company(name="Test AFMCO", **kwargs):
    if frappe.db.exists("Company", name):
        return frappe.get_doc("Company", name)
    doc = frappe.get_doc({
        "doctype": "Company",
        "company_name": name,
        "abbr": "TAFM",
        "default_currency": "SAR",
        "country": frappe.defaults.get_global_default("country") or "Saudi Arabia",
        **kwargs,
    })
    doc.insert(ignore_permissions=True)
    return doc

def make_building(name=None, company=None, **kwargs):
    name = name or "Test Building"
    if frappe.db.exists("Building", name):
        return frappe.get_doc("Building", name)
    doc = frappe.get_doc({
        "doctype": "Building",
        "building_name": name,
        "status": "Active",
        "total_capacity": kwargs.pop("total_capacity", 10),
        "company": company or make_company().name,
        **kwargs,
    })
    doc.insert(ignore_permissions=True)
    return doc

def make_room(building, room_number=None, **kwargs):
    room_number = room_number or f"{building}-R01"
    if frappe.db.exists("Room", room_number):
        return frappe.get_doc("Room", room_number)
    doc = frappe.get_doc({
        "doctype": "Room",
        "room_number": room_number,
        "building": building,
        "bed_capacity": kwargs.pop("bed_capacity", 2),
        "status": "Available",
        **kwargs,
    })
    doc.insert(ignore_permissions=True)
    return doc

def make_bed(room, bed_code=None, **kwargs):
    bed_code = bed_code or f"{room}-B01"
    if frappe.db.exists("Bed", bed_code):
        return frappe.get_doc("Bed", bed_code)
    doc = frappe.get_doc({
        "doctype": "Bed",
        "bed_code": bed_code,
        "room": room,
        "status": "Available",
        **kwargs,
    })
    doc.insert(ignore_permissions=True)
    return doc

def make_employee(name=None, company=None, **kwargs):
    name = name or "Test Employee"
    if frappe.db.exists("Employee", {"employee_name": name}):
        return frappe.get_all("Employee", filters={"employee_name": name}, limit=1)[0]
    doc = frappe.get_doc({
        "doctype": "Employee",
        "employee_name": name,
        "first_name": name,
        "company": company or make_company().name,
        "status": "Active",
        "gender": "Male",
        "date_of_birth": "1990-01-01",
        "date_of_joining": "2020-01-01",
        **kwargs,
    })
    doc.insert(ignore_permissions=True)
    return doc

def make_supplier(name, **kwargs):
    if frappe.db.exists("Supplier", name):
        return name
    frappe.get_doc(
        {
            "doctype": "Supplier",
            "supplier_name": name,
            "supplier_group": "All Supplier Groups",
            **kwargs,
        }
    ).insert(ignore_permissions=True)
    return name

def service_item(name):
    if frappe.db.exists("Item", name):
        return name
    group = frappe.db.get_value("Item Group", {"is_group": 0}, "name")
    frappe.get_doc(
        {
            "doctype": "Item",
            "item_code": name,
            "item_name": name,
            "item_group": group,
            "stock_uom": "Nos",
            "is_stock_item": 0,
        }
    ).insert(ignore_permissions=True)
    return name

def default_company():
    return (
        frappe.defaults.get_global_default("company")
        or frappe.get_all("Company", limit=1)[0].name
    )

def make_project(name):
    p = frappe.db.get_value("Project", {"project_name": name}, "name")
    if not p:
        p = frappe.get_doc(
            {"doctype": "Project", "project_name": name}
        ).insert(ignore_permissions=True).name
    return p

def purge_doc(doctype, name):
    frappe.set_user("Administrator")
    if not frappe.db.exists(doctype, name):
        return
    doc = frappe.get_doc(doctype, name)
    if doc.docstatus == 1:
        try:
            doc.cancel()
        except Exception:
            frappe.db.set_value(doctype, name, "docstatus", 2, update_modified=False)
    frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)

def purge_trip_request(tr_name, rp_name):
    frappe.set_user("Administrator")
    for ledger in frappe.get_all(
        "Trip Fulfilment Ledger", filters={"transport_request": tr_name}, pluck="name"
    ):
        frappe.delete_doc(
            "Trip Fulfilment Ledger", ledger, ignore_permissions=True, force=True
        )
    purge_doc("Route Plan", rp_name)
    purge_doc("Transport Request", tr_name)

def make_rental_office(name):
    office = frappe.db.get_value("Rental Office", {"office_name": name}, "name")
    if not office:
        office = frappe.get_doc(
            {"doctype": "Rental Office", "office_name": name, "status": "Active"}
        ).insert(ignore_permissions=True).name
    return office

def make_vehicle(plate, odometer=None, project=None, ownership=None):
    name = frappe.db.get_value("Salis Vehicle", {"plate_number": plate}, "name")
    values = {
        k: v
        for k, v in (
            ("odometer", odometer),
            ("project", project),
            ("ownership", ownership),
        )
        if v is not None
    }
    if not name:
        return frappe.get_doc(
            {
                "doctype": "Salis Vehicle",
                "plate_number": plate,
                "status": "Active",
                **values,
            }
        ).insert(ignore_permissions=True).name
    if values:
        frappe.db.set_value("Salis Vehicle", name, values)
    return name

def driver_user(driver):
    emp = frappe.db.get_value("Salis Driver", driver, "employee")
    return frappe.db.get_value("Employee", emp, "user_id")

def make_test_driver():
    user = "drv_dp@example.com"
    if not frappe.db.exists("User", user):
        try:
            u = frappe.get_doc(
                {"doctype": "User", "email": user, "first_name": "Test Driver", "send_welcome_email": 0}
            )
            u.add_roles("Driver")
            u.insert(ignore_permissions=True)
        except frappe.DuplicateEntryError:
            pass
    emp = frappe.db.get_value("Employee", {"user_id": user}, "name")
    if not emp:
        emp = frappe.get_doc(
            {
                "doctype": "Employee",
                "first_name": "Test Driver",
                "user_id": user,
                "date_of_birth": "1990-01-01",
                "date_of_joining": today(),
                "gender": "Male",
                "company": default_company(),
            }
        ).insert(ignore_permissions=True).name
    drv = frappe.db.get_value("Salis Driver", {"employee": emp}, "name")
    if not drv:
        drv = frappe.get_doc(
            {"doctype": "Salis Driver", "employee": emp, "full_name": "Test Driver", "status": "Active"}
        ).insert(ignore_permissions=True).name
    if not frappe.db.get_value("Salis Driver", drv, "current_vehicle"):
        veh = frappe.get_doc(
            {"doctype": "Salis Vehicle", "plate_number": "DP TEST 1", "status": "Active"}
        ).insert(ignore_permissions=True).name
        frappe.db.set_value("Salis Driver", drv, "current_vehicle", veh)
    return drv

def make_goods_receipt(intake_building, article, procurement_supervisor, qty=5):
    gr = frappe.get_doc(
        {
            "doctype": "Goods Receipt",
            "naming_series": "ACC-GRN-.YYYY.-.#####",
            "receipt_date": "2026-05-01",
            "intake_building": intake_building,
            "procurement_supervisor": procurement_supervisor,
        }
    )
    gr.append("items", {"item_type": "Custody Article", "item": article, "qty": qty})
    gr.insert(ignore_permissions=True)
    gr.submit()
    return gr

def make_maintenance_request(building, room):
    mr = frappe.get_doc(
        {
            "doctype": "Maintenance Request",
            "naming_series": "MAINT-.YYYY.-.#####",
            "building": building,
            "room": room,
            "reported_by": "Administrator",
            "issue_type": "Plumbing",
            "issue_description": "Leak under sink",
        }
    )
    mr.insert(ignore_permissions=True, ignore_links=True)
    mr.submit()
    return mr

def make_safety_round(building, **overrides):
    data = {
        "doctype": "Safety Round",
        "building": building,
        "round_date": today(),
        "cadence": "Weekly",
    }
    data.update(overrides)
    return frappe.get_doc(data).insert(ignore_permissions=True)

def make_scoped_supervisor(make_user, building, add_cleanup):
    email = make_user("Resident Supervisor")
    up = frappe.get_doc(
        {
            "doctype": "User Permission",
            "user": email,
            "allow": "Building",
            "for_value": building,
        }
    ).insert(ignore_permissions=True)
    add_cleanup(
        frappe.delete_doc, "User Permission", up.name, force=True, ignore_permissions=True
    )
    return email

def make_assignment(employee, building, project, room_number=None, bed_code=None, stay_type="Permanent"):
    room_number = room_number or f"{building}-GPS-R"
    bed_code = bed_code or f"{building}-GPS-B"
    if not frappe.db.exists("Room", room_number):
        frappe.get_doc(
            {
                "doctype": "Room",
                "room_number": room_number,
                "building": building,
                "bed_capacity": 4,
                "status": "Available",
            }
        ).insert(ignore_permissions=True)
    if not frappe.db.exists("Bed", bed_code):
        frappe.get_doc(
            {
                "doctype": "Bed",
                "bed_code": bed_code,
                "room": room_number,
                "status": "Available",
            }
        ).insert(ignore_permissions=True)
    company = frappe.db.get_value("Building", building, "company") or default_company()
    cost_center = frappe.db.get_value("Cost Center", {"company": company, "is_group": 0}, "name")
    doc = frappe.get_doc(
        {
            "doctype": "Housing Assignment",
            "employee": employee,
            "building": building,
            "room": room_number,
            "bed": bed_code,
            "project": project,
            "cost_center": cost_center,
            "check_in_date": today(),
            "stay_type": stay_type,
        }
    )
    doc.insert(ignore_permissions=True)
    doc.submit()
    return doc.name

def make_worker_trip(
    driver,
    project,
    building,
    workers,
    route_name,
    from_location=None,
    to_location="Project Site",
    pickup_point="Building Gate",
    pickup_datetime=None,
    passengers=None,
    depart_time=None,
    status="Planned",
    link_route_plan_on_request=False,
):
    from_location = building if from_location is None else from_location
    depart_time = frappe.utils.nowtime() if depart_time is None else depart_time
    passengers = len(workers) if passengers is None else passengers
    tr_fields = {
        "doctype": "Transport Request",
        "service_line": "Site Transport",
        "request_type": "Accommodation to Project Shuttle",
        "project": project,
        "accommodation_building": building,
        "from_location": from_location,
        "to_location": to_location,
        "source_channel": "Desk",
        "status": "New",
        "workers": [{"employee": e, "pickup_point": pickup_point} for e in workers],
    }
    if pickup_datetime is not None:
        tr_fields["pickup_datetime"] = pickup_datetime
    tr = frappe.get_doc(tr_fields).insert(ignore_permissions=True)
    tr.reload()

    rp = frappe.get_doc(
        {
            "doctype": "Route Plan",
            "route_name": route_name,
            "transport_request": tr.name,
            "project": project,
            "driver": driver,
            "stops": [
                {
                    "sequence": 1,
                    "stop_name": "Housing Pickup",
                    "accommodation_building": building,
                    "location": "Building Gate",
                    "passengers": passengers,
                },
                {
                    "sequence": 2,
                    "stop_name": "Project Drop-off",
                    "location": "Project Site",
                    "passengers": 0,
                },
            ],
        }
    ).insert(ignore_permissions=True)
    if link_route_plan_on_request:
        frappe.db.set_value("Transport Request", tr.name, "route_plan", rp.name)

    dt = frappe.get_doc(
        {
            "doctype": "Dispatch Trip",
            "route_plan": rp.name,
            "transport_request": tr.name,
            "driver": driver,
            "trip_date": today(),
            "depart_time": depart_time,
            "status": "Planned",
        }
    ).insert(ignore_permissions=True)
    if status and status != "Planned":
        frappe.db.set_value("Dispatch Trip", dt.name, "status", status)
        dt.reload()
    return tr, rp, dt

class WorkerTripMixin:

    def _worker_trip(self, driver, project, building, workers, route_name, **kwargs):
        tr, rp, dt = make_worker_trip(
            driver, project, building, workers, route_name, **kwargs
        )
        self.addCleanup(lambda: self._purge(dt.name, rp.name, tr.name))
        return tr, rp, dt

    @staticmethod
    def _purge(dt_name, rp_name, tr_name):
        frappe.set_user("Administrator")
        for dtp in (
            ("Dispatch Trip", dt_name),
            ("Route Plan", rp_name),
            ("Transport Request", tr_name),
        ):
            if frappe.db.exists(*dtp):
                doc = frappe.get_doc(*dtp)
                if doc.docstatus == 1:
                    try:
                        doc.cancel()
                    except Exception:
                        pass
                frappe.delete_doc(*dtp, ignore_permissions=True, force=True)

def fixture_tag():
    return frappe.generate_hash(length=12)

def ensure_company(name_prefix="Apex Test"):
    existing = frappe.db.get_value("Company", {}, "name")
    if existing:
        return existing
    tag = fixture_tag()
    return frappe.get_doc(
        {
            "doctype": "Company",
            "company_name": f"{name_prefix} {tag}",
            "abbr": f"AT{tag}",
            "default_currency": "SAR",
            "country": "Saudi Arabia",
        }
    ).insert(ignore_permissions=True).name

def ensure_account(company, account_type, root_type, account_currency=None):
    filters = {"company": company, "account_type": account_type, "is_group": 0}
    if account_currency:
        filters["account_currency"] = account_currency
    existing = frappe.db.get_value("Account", filters, "name")
    if existing:
        return existing
    parent = frappe.db.get_value(
        "Account", {"company": company, "is_group": 1, "root_type": root_type}, "name"
    )
    assert parent, (
        f"company {company} has no {root_type} group account to hang a "
        f"{account_type} account under"
    )
    values = {
        "doctype": "Account",
        "account_name": f"Apex {account_type} {fixture_tag()}",
        "company": company,
        "parent_account": parent,
        "root_type": root_type,
        "account_type": account_type,
        "is_group": 0,
    }
    if account_currency:
        values["account_currency"] = account_currency
    return frappe.get_doc(values).insert(ignore_permissions=True).name

def make_submitted_custody_issue():
    issue = frappe.get_doc(
        {
            "doctype": "Custody Issue",
            "naming_series": "CUST-ISS-.YYYY.-.####",
            "issue_date": "2026-06-01",
            "building": "QA-BLDG",
            "items": [{"doctype": "Custody Issue Item", "article": "QA-ART", "qty": 1}],
        }
    )
    issue.insert(ignore_permissions=True, ignore_links=True)
    issue.submit()
    return issue

