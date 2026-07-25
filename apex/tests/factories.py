# Copyright (c) 2026, AFMCO and contributors
"""Shared test fixture helpers for Habitat doctypes.

Usage:
    from apex.tests.factories import make_building, make_room, make_bed, make_assignment
"""

from __future__ import annotations
import frappe
from frappe.utils import today

try:
    from frappe.tests.utils import FrappeTestCase
    _UnitTestCase = FrappeTestCase
except Exception:  # pragma: no cover — frappe absent (static analysis / non-bench)
    FrappeTestCase = object  # type: ignore
    _UnitTestCase = object  # type: ignore


# [#2gr8f9]
class ApexHabitatTestCase(FrappeTestCase):
    """Base test case for apex integration tests."""


class ApexHabitatUnitTestCase(_UnitTestCase):
    """Base test case for apex unit tests (no database)."""

# [#8evoal]
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
        "company": company or "Test AFMCO",
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
        "company": company or "Test AFMCO",
        "status": "Active",
        "gender": "Male",
        "date_of_birth": "1990-01-01",
        "date_of_joining": "2020-01-01",
        **kwargs,
    })
    doc.insert(ignore_permissions=True)
    return doc


# [#cglp6s]


def make_supplier(name, **kwargs):
    """Get-or-create a Supplier by name (named by supplier_name on a default
    ERPNext site); return its name. Idempotent — a re-run never duplicates."""
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


def default_company():
    """The site's default company name (global default, else the first Company)."""
    return (
        frappe.defaults.get_global_default("company")
        or frappe.get_all("Company", limit=1)[0].name
    )


def make_project(name):
    """Get-or-create a Project by ``project_name``; return its name."""
    p = frappe.db.get_value("Project", {"project_name": name}, "name")
    if not p:
        p = frappe.get_doc(
            {"doctype": "Project", "project_name": name}
        ).insert(ignore_permissions=True).name
    return p


def make_vehicle(plate, odometer=None, project=None):
    """Get-or-create an Active Salis Vehicle by ``plate_number``; return its name.

    ``odometer`` / ``project`` are applied on the EXISTING row too, not only on a
    freshly created one: the dispatch-trip workflow tests pass ``odometer=0`` to
    assert a reading a previous module may already have moved.
    """
    name = frappe.db.get_value("Salis Vehicle", {"plate_number": plate}, "name")
    values = {
        k: v for k, v in (("odometer", odometer), ("project", project)) if v is not None
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


def make_site(name):
    """Get-or-create an Accommodation Site by ``site_name``; return its name."""
    s = frappe.db.get_value("Site", {"site_name": name}, "name")
    if not s:
        s = frappe.get_doc(
            {"doctype": "Site", "site_name": name, "company": default_company()}
        ).insert(ignore_permissions=True).name
    return s


def make_masar_building(name):
    """Get-or-create an Accommodation Building on the shared Masar test site,
    carrying a ``google_maps_url``; return its name."""
    b = frappe.db.get_value("Building", {"building_name": name}, "name")
    if not b:
        b = frappe.get_doc(
            {
                "doctype": "Building",
                "building_name": name,
                "site": make_site("Masar Test Site"),
                "total_capacity": 50,
                "google_maps_url": "https://maps.example/masar-building",
            }
        ).insert(ignore_permissions=True).name
    return b


def make_building_with_coords(name, lat, lng):
    """Get-or-create a building carrying pickup coordinates (idempotent on re-run)."""
    existing = frappe.db.get_value("Building", {"building_name": name}, "name")
    if existing:
        frappe.db.set_value(
            "Building", existing, {"pickup_lat": lat, "pickup_lng": lng}
        )
        return existing
    return (
        frappe.get_doc(
            {
                "doctype": "Building",
                "building_name": name,
                "site": make_site("Masar GPS Test Site"),
                "total_capacity": 20,
                "pickup_lat": lat,
                "pickup_lng": lng,
            }
        )
        .insert(ignore_permissions=True)
        .name
    )


def make_worker_employee(first_name):
    """Get-or-create an Employee by ``first_name`` (matched on employee_name);
    return its name."""
    emp = frappe.db.get_value("Employee", {"employee_name": first_name}, "name")
    if not emp:
        emp = frappe.get_doc(
            {
                "doctype": "Employee",
                "first_name": first_name,
                "date_of_birth": "1990-01-01",
                "date_of_joining": today(),
                "gender": "Male",
                "company": default_company(),
            }
        ).insert(ignore_permissions=True).name
    return emp


def driver_user(driver):
    """The login user behind a Salis Driver (via its Employee.user_id)."""
    emp = frappe.db.get_value("Salis Driver", driver, "employee")
    return frappe.db.get_value("Employee", emp, "user_id")


def make_driver_chain(email, first_name):
    """Idempotently get-or-create a User+Employee+Salis Driver chain and return
    ``(driver_name, email)``. Re-runs on a non-fresh DB never duplicate."""
    if not frappe.db.exists("User", email):
        frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": first_name,
                "send_welcome_email": 0,
            }
        ).insert(ignore_permissions=True)
    user = frappe.get_doc("User", email)
    if "Driver" not in frappe.get_roles(email):
        user.add_roles("Driver")
    emp = frappe.db.get_value("Employee", {"user_id": email}, "name")
    if not emp:
        emp = frappe.get_doc(
            {
                "doctype": "Employee",
                "first_name": first_name,
                "user_id": email,
                "date_of_birth": "1990-01-01",
                "date_of_joining": today(),
                "gender": "Male",
                "company": default_company(),
            }
        ).insert(ignore_permissions=True).name
    drv = frappe.db.get_value("Salis Driver", {"employee": emp}, "name")
    if not drv:
        drv = frappe.get_doc(
            {
                "doctype": "Salis Driver",
                "employee": emp,
                "full_name": first_name,
                "status": "Active",
            }
        ).insert(ignore_permissions=True).name
    return drv, email


def make_test_driver():
    """Get-or-create the canonical portal-test driver (User+Employee+Salis Driver
    +Vehicle) keyed on a fixed user; return the driver name. Idempotent."""
    user = "drv_dp@example.com"
    if not frappe.db.exists("User", user):
        try:
            u = frappe.get_doc(
                {"doctype": "User", "email": user, "first_name": "Test Driver", "send_welcome_email": 0}
            )
            u.add_roles("Driver")
            u.insert(ignore_permissions=True)
        except frappe.DuplicateEntryError:
            # [#hxpd3j]
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


def make_driver_without_vehicle(email):
    """Get-or-create a User+Employee+Salis Driver chain with NO current_vehicle,
    keyed on ``email``; return ``(driver_name, email)``. Idempotent — the fuel /
    scope tests use it to prove a vehicle-less driver is rejected."""
    if not frappe.db.exists("User", email):
        try:
            u = frappe.get_doc(
                {"doctype": "User", "email": email, "first_name": "NoVeh", "send_welcome_email": 0}
            )
            u.add_roles("Driver")
            u.insert(ignore_permissions=True)
        except frappe.DuplicateEntryError:
            # [#hxpd3j]
            pass
    emp = frappe.db.get_value("Employee", {"user_id": email}, "name")
    if not emp:
        emp = frappe.get_doc(
            {
                "doctype": "Employee",
                "first_name": "NoVeh",
                "user_id": email,
                "date_of_birth": "1990-01-01",
                "date_of_joining": today(),
                "gender": "Male",
                "company": default_company(),
            }
        ).insert(ignore_permissions=True).name
    drv = frappe.db.get_value("Salis Driver", {"employee": emp}, "name")
    if not drv:
        drv = frappe.get_doc(
            {"doctype": "Salis Driver", "employee": emp, "full_name": "NoVeh", "status": "Active"}
        ).insert(ignore_permissions=True).name
    return drv, email


def make_worker_token(employee):
    """Create a Masar Worker Token for an Employee; return the RAW token string. The
    token is stored hashed at rest (P-104), so the raw value is read from the freshly
    minted doc's transient ``_plaintext_token`` (never re-readable from the row)."""
    return (
        frappe.get_doc(
            {
                "doctype": "Masar Worker Token",
                "party_type": "Employee",
                "party": employee,
                "employee": employee,
                "enabled": 1,
            }
        )
        .insert(ignore_permissions=True)
        ._plaintext_token
    )


def make_assignment(employee, building, project, room_number=None, bed_code=None, stay_type="Permanent"):
    """A submitted Accommodation Assignment placing ``employee`` in ``building``
    (creating the room + bed if needed). Returns the assignment name."""
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
    depart_time="06:30:00",
    status="Planned",
    link_route_plan_on_request=False,
):
    """Build a complete Workers-line trip (Transport Request + Route Plan +
    Dispatch Trip) and return the three docs ``(tr, rp, dt)``.

    Defaults reproduce the Masar worker-trip fixture; the GPS/ETA tests override
    ``from_location``/``pickup_datetime``/``status``/``link_route_plan_on_request``
    to build a *dispatched* trip whose Route Plan is linked back on the request.
    A new Dispatch Trip must start ``Planned`` (controller guard); a non-Planned
    target ``status`` is applied afterward via a direct write."""
    from_location = building if from_location is None else from_location
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
    # [#aj1ze2]
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
    """Builds a complete Workers-line trip for a given driver and returns the
    handle records, registering cleanup. Record creation is delegated to
    ``make_worker_trip``; everything is created as Administrator.

    Promoted from tests/test_masar_worker_movement.py (P-135) so the Masar test
    modules share one mixin without a cross-test-module import."""

    def _worker_trip(self, driver, project, building, workers, route_name):
        tr, rp, dt = make_worker_trip(driver, project, building, workers, route_name)
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


# [#446tat]

_BUILDING_BASELINE: set[str] = set()


def snapshot_building_baseline():
    """Record the Accommodation Building names that exist before the suite runs.
    Called from ``tests/before_tests.py`` (the ``before_tests`` hook)."""
    _BUILDING_BASELINE.clear()
    _BUILDING_BASELINE.update(
        frappe.get_all("Building", pluck="name")
    )


def purge_test_buildings():
    """Force-delete every Accommodation Building created after the pre-suite
    baseline snapshot; return the number removed. Idempotent, best-effort per row
    (as Administrator). Invoked from a ``tearDownModule`` in building-creating test
    modules so the post-suite building count returns to the pre-suite baseline.

    ``force=True`` bypasses the link-validation check, so a building with dependent
    rooms/beds/assignments is removed regardless (test site only; those children
    are themselves suite pollution)."""
    frappe.set_user("Administrator")
    removed = 0
    for name in frappe.get_all("Building", pluck="name"):
        if name in _BUILDING_BASELINE:
            continue
        try:
            frappe.delete_doc(
                "Building", name, ignore_permissions=True, force=True
            )
            removed += 1
        except Exception:
            # [#kgd2nu]
            pass
    if removed:
        frappe.db.commit()
    return removed


# [#a140fx] Accounting / payroll chain fixtures. Site-wide masters (Company, Account)
# are get-or-create, since a second copy would change what "the site's company" means
# for every other test; class-private records (Employee, Salary Component, Salary
# Structure) are always NEW, because borrowing what an earlier test left behind is
# exactly the order-dependence these builders exist to remove.


def fixture_tag():
    """A collision-free fixture suffix (>=12 random characters — the floor
    ``apex/tests/test_fixture_identifier_entropy.py`` enforces)."""
    return frappe.generate_hash(length=12)


def ensure_company(name_prefix="Apex Test"):
    """The site's Company, created when the site has none. Returns its name.

    ``before_tests`` normally provisions one, so this usually returns what is
    already there; the create path is what keeps a test off ``skipTest`` on a site
    that was never wizard-bootstrapped.
    """
    existing = frappe.db.get_value("Company", {}, "name")
    if existing:
        return existing
    tag = fixture_tag()
    return frappe.get_doc(
        {
            "doctype": "Company",
            "company_name": f"{name_prefix} {tag}",
            # Full hash, never a slice — a narrowed random identifier is exactly
            # what the fixture-entropy guard forbids.
            "abbr": f"AT{tag}",
            "default_currency": "SAR",
            "country": "Saudi Arabia",
        }
    ).insert(ignore_permissions=True).name


def ensure_account(company, account_type, root_type, account_currency=None):
    """A non-group Account of ``account_type`` on ``company``; created under the
    chart's ``root_type`` group when the chart has none. Returns its name.

    HRMS refuses to submit an Employee Advance whose advance account is not
    Receivable, and a Journal Entry party proof needs a real Payable/Cash pair, so
    this account type is what those chains actually depend on. ``account_currency``
    narrows both the lookup and the created row when a caller needs the company's
    base currency specifically.
    """
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


def make_payroll_employee(company, name_prefix="Apex Recovery"):
    """A brand-new Active Employee on ``company``. Returns its name.

    Deliberately never reuses the site's existing Employee: a test that recovers
    from whatever worker an earlier test left behind passes for a reason that has
    nothing to do with the code under test.
    """
    return frappe.get_doc(
        {
            "doctype": "Employee",
            "first_name": f"{name_prefix} {fixture_tag()}",
            "company": company,
            "status": "Active",
            "gender": "Male",
            "date_of_birth": "1990-01-01",
            "date_of_joining": "2020-01-01",
        }
    ).insert(ignore_permissions=True).name


def make_salary_component(component_type, prefix="Apex"):
    """A brand-new Salary Component of ``component_type`` (Earning / Deduction).

    Type matters: an Earning component would silently PAY the worker the amount a
    Deduction component recovers, so the recovery tests need both to prove the
    engine tells them apart.
    """
    tag = fixture_tag()
    return frappe.get_doc(
        {
            "doctype": "Salary Component",
            "salary_component": f"{prefix} {component_type} {tag}",
            "salary_component_abbr": f"{prefix[0]}{component_type[0]}{tag}",
            "type": component_type,
        }
    ).insert(ignore_permissions=True).name


def assign_monthly_wage(employee, company, wage, currency=None):
    """Give ``employee`` a known monthly wage natively: a submitted Salary
    Structure plus a submitted Salary Structure Assignment. Returns the structure.

    ``employee_recovery._monthly_wage`` reads the assignment's ``base``, and every
    statutory cap is a percentage of it. Without this a recovery test can only
    ever observe "no wage known, recover nothing" — a zero that proves nothing.
    """
    currency = currency or frappe.db.get_value("Company", company, "default_currency") or "SAR"
    tag = fixture_tag()
    structure = frappe.get_doc(
        {
            "doctype": "Salary Structure",
            "name": f"Apex Structure {tag}",
            "company": company,
            "is_active": "Yes",
            "currency": currency,
            "payroll_frequency": "Monthly",
            "earnings": [
                {
                    "doctype": "Salary Detail",
                    "salary_component": make_salary_component("Earning"),
                    "amount": wage,
                    "parentfield": "earnings",
                }
            ],
        }
    ).insert(ignore_permissions=True)
    structure.submit()

    assignment = frappe.get_doc(
        {
            "doctype": "Salary Structure Assignment",
            "employee": employee,
            "salary_structure": structure.name,
            "company": company,
            "currency": currency,
            "from_date": "2020-01-01",
            "base": wage,
        }
    ).insert(ignore_permissions=True)
    assignment.submit()
    return structure.name

