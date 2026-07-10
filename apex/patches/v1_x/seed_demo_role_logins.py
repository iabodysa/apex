# Copyright (c) 2026, AFMCO and contributors
"""Seed two ready-to-use demo logins so the owner can test the app as each role.

A fresh dev/demo site has no per-role users, so trying out the role-scoped
surfaces means hand-building a User, the roles, a User Permission, and enough
data for each surface to render. This seeds that end-to-end for two personas:

  supervisor.demo@example.com  (Resident Supervisor + Fleet Supervisor)
    - scoped to ONE demo building via the building's
      ``responsible_supervisor`` (the canonical source of the
      Accommodation Building User Permission) and to ONE demo Project, so the
      owner sees the *scoped* supervisor experience, not the global one.
    - lands the supervisor surfaces non-empty: the safety portal (a Safety
      Round on the building), the building dashboard (rooms + an occupancy
      snapshot), and Fleet operations-control (the demo Dispatch Trip seeded by
      seed_masar_demo_movement on the same Project).

  employee.demo@example.com  (a plain Employee with a Masar worker link)
    - linked to a demo Employee and issued a Masar Worker Token, so Masar
      resolves them. Masar is token-only (Guest, no login), so the recipe is the
      personal link ``/masar?w=<token>`` — the minted token is returned below.

Both personas reuse the demo estate keys from seed_masar_demo_movement (same
building / site / project / company), so the two seeders compose and a re-run of
either adds nothing.

Idempotent and install-safe: every record is get-or-created by a stable key, the
whole thing is a no-op unless ``developer_mode`` is on, and it is wrapped so it
can never fail an install/migrate. All names are generic demo placeholders — no
real personnel, contacts, or locations. The dev password is a fixed,
non-secret demo value (a dev/demo site only) returned for the owner's recipe.
"""

import frappe

from apex.apex_core.utils.company import resolve_company_or_any

# Fixed, non-secret demo credential — only ever set on a developer_mode site
# (the whole seeder is gated on that). Returned in the login recipe, never a real
# secret.
_DEMO_PASSWORD = "ApexDemo#2024"

# Supervisor persona.
_SUP_USER = "supervisor.demo@example.com"
_SUP_NAME = "Demo Supervisor"
_SUP_ROLES = ("Resident Supervisor", "Fleet Supervisor")

# Employee persona.
_EMP_USER = "employee.demo@example.com"
_EMP_NAME = "Demo Employee"

# Shared demo estate — same stable keys as seed_masar_demo_movement so the two
# seeders land on ONE estate and the supervisor's scope matches the demo trip.
_PROJECT = "Demo Transport Project"
_SITE = "Demo Housing Site"
_BUILDING = "Demo Residence A"

# DocTypes this seeder writes to; if any is missing the personas cannot be built.
_REQUIRED = (
    "Building",
    "Room",
    "Occupancy Snapshot",
    "Safety Round",
    "Employee",
    "Masar Worker Token",
)


def _get_or_create(doctype, key_filters, make):
    name = frappe.db.get_value(doctype, key_filters, "name")
    if name:
        return name
    return make().name


def _site(company):
    return _get_or_create(
        "Site",
        {"site_name": _SITE},
        lambda: frappe.get_doc(
            {"doctype": "Site", "site_name": _SITE, "company": company}
        ).insert(ignore_permissions=True),  # audit-ok
    )


def _building(company):
    return _get_or_create(
        "Building",
        {"building_name": _BUILDING},
        lambda: frappe.get_doc(
            {
                "doctype": "Building",
                "building_name": _BUILDING,
                "site": _site(company),
                "total_capacity": 40,
                "google_maps_url": "https://maps.example/demo-residence-a",
            }
        ).insert(ignore_permissions=True),  # audit-ok
    )


def _project():
    return _get_or_create(
        "Project",
        {"project_name": _PROJECT},
        lambda: frappe.get_doc(
            {"doctype": "Project", "project_name": _PROJECT}
        ).insert(ignore_permissions=True),  # audit-ok
    )


def _user(email, full_name, roles):
    """Get-or-create a demo User with a fixed demo password and the given roles."""
    if not frappe.db.exists("User", email):
        frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": full_name,
                "send_welcome_email": 0,
                "new_password": _DEMO_PASSWORD,
            }
        ).insert(ignore_permissions=True)  # audit-ok
    user = frappe.get_doc("User", email)
    missing = [r for r in roles if r not in frappe.get_roles(email)]
    if missing:
        # Only add roles that actually exist, so a not-yet-seeded role never
        # crashes the persona (the others still apply).
        existing = [r for r in missing if frappe.db.exists("Role", r)]
        if existing:
            user.add_roles(*existing)
    return email


def _user_permission(user, allow, for_value):
    """Mirror Accommodation Building's own on_update permission shape; idempotent."""
    if frappe.db.exists(
        "User Permission", {"user": user, "allow": allow, "for_value": for_value}
    ):
        return
    frappe.get_doc(
        {
            "doctype": "User Permission",
            "user": user,
            "allow": allow,
            "for_value": for_value,
        }
    ).insert(ignore_permissions=True)  # audit-ok — demo scope, dev site only


def _scope_supervisor_to_building(user, building):
    """Point the building's supervisor field at the demo user so the building
    controller's on_update mints the Accommodation Building User Permission (the
    canonical source of the building scope). Belt-and-braces ensure the row even
    if the field was already set on a prior run."""
    if frappe.db.get_value("Building", building, "responsible_supervisor") != user:
        b = frappe.get_doc("Building", building)
        b.responsible_supervisor = user
        b.save(ignore_permissions=True)  # audit-ok — triggers permission sync
    _user_permission(user, "Building", building)


def _demo_rooms(building):
    """A small ground-floor layout so the building dashboard renders a real grid
    (it reads Accommodation Room). Mixed statuses to exercise the colour map."""
    rooms = [
        ("G01", "Available", "Ready"),
        ("G02", "Partially Occupied", "Ready"),
        ("G03", "Full", "Ready"),
        ("G04", "Under Maintenance", "Needs Repair"),
    ]
    for suffix, status, readiness in rooms:
        room_number = f"{_BUILDING[:4].upper()}-{suffix}"
        if frappe.db.exists("Room", room_number):
            continue
        frappe.get_doc(
            {
                "doctype": "Room",
                "building": building,
                "room_number": room_number,
                "floor": 0,
                "room_type": "Worker",
                "bed_capacity": 4,
                "status": status,
                "readiness_status": readiness,
            }
        ).insert(ignore_permissions=True)  # audit-ok


def _occupancy_snapshot(building):
    """One snapshot so the dashboard's occupancy chart has a data point."""
    if frappe.db.exists("Occupancy Snapshot", {"building": building}):
        return
    frappe.get_doc(
        {
            "doctype": "Occupancy Snapshot",
            "building": building,
            "snapshot_date": frappe.utils.today(),
            "active_occupants": 18,
            "total_capacity": 40,
            "available_capacity": 22,
            "occupancy_percent": 45,
        }
    ).insert(ignore_permissions=True)  # audit-ok


def _safety_round(building, supervisor):
    """One Safety Round on the building so the supervisor's safety portal lists a
    real round, not an empty table. Left in draft (not submitted) — submit derives
    a result from linked task executions, which the demo has none of."""
    if frappe.db.exists("Safety Round", {"building": building}):
        return
    frappe.get_doc(
        {
            "doctype": "Safety Round",
            "building": building,
            "round_date": frappe.utils.today(),
            "cadence": "Monthly",
            "supervisor": supervisor,
        }
    ).insert(ignore_permissions=True)  # audit-ok


def _employee(full_name, company, user_id=None):
    name = frappe.db.get_value("Employee", {"employee_name": full_name}, "name")
    if name:
        if user_id and not frappe.db.get_value("Employee", name, "user_id"):
            frappe.db.set_value("Employee", name, "user_id", user_id)
        return name
    doc = {
        "doctype": "Employee",
        "first_name": full_name,
        "date_of_birth": "1990-01-01",
        "date_of_joining": frappe.utils.today(),
        "gender": "Male",
        "company": company,
        "status": "Active",
    }
    if user_id:
        doc["user_id"] = user_id
    return frappe.get_doc(doc).insert(ignore_permissions=True).name  # audit-ok


def _worker_token(employee):
    """Issue (or fetch) the employee's Masar token and return its value for the
    login recipe. Masar resolves a worker by this token, not by login."""
    from apex.apex_core.doctype.masar_worker_token.masar_worker_token import (
        get_or_create_for_employee,
    )

    return get_or_create_for_employee(employee).token


def _seed_supervisor(company):
    building = _building(company)
    project = _project()
    user = _user(_SUP_USER, _SUP_NAME, _SUP_ROLES)
    _scope_supervisor_to_building(user, building)
    # Fleet operations-control is project-scoped; scope the supervisor to the demo
    # Project so the demo Dispatch Trip (seed_masar_demo_movement) is in view.
    _user_permission(user, "Project", project)
    _demo_rooms(building)
    _occupancy_snapshot(building)
    _safety_round(building, user)


def _seed_employee(company):
    user = _user(_EMP_USER, _EMP_NAME, ())
    emp = _employee(_EMP_NAME, company, user_id=user)
    return _worker_token(emp)


def execute():
    """Seed both demo logins. Returns a dict of login recipes (and the minted
    Masar token) on a dev site; None / a no-op otherwise."""
    try:
        # Demo logins only on a developer/demo site — never seed a production site.
        if not frappe.conf.get("developer_mode"):
            return
        if any(not frappe.db.exists("DocType", dt) for dt in _REQUIRED):
            return
        company = resolve_company_or_any()
        if not company:
            return

        _seed_supervisor(company)
        frappe.db.commit()

        # The Masar token is the employee half; isolate it so a token failure does
        # not discard the supervisor persona already committed above.
        token = None
        try:
            token = _seed_employee(company)
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            frappe.log_error(
                title="seed_demo_role_logins: employee/token",
                message=frappe.get_traceback(),
            )

        base = frappe.utils.get_url()
        return {
            "supervisor": {
                "email": _SUP_USER,
                "password": _DEMO_PASSWORD,
                "roles": list(_SUP_ROLES),
                "scoped_building": _BUILDING,
                "login": f"{base}/login  (then open /app or /safety)",
            },
            "employee": {
                "email": _EMP_USER,
                "password": _DEMO_PASSWORD,
                "masar_link": f"{base}/masar?w={token}" if token else None,
            },
        }
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            title="seed_demo_role_logins failed",
            message=frappe.get_traceback(),
        )
