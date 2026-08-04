# Copyright (c) 2026, AFMCO and contributors
"""Setup-wizard demo data — one coherent accommodation scenario, and its removal.

The last Apex wizard slide carries a demo checkbox. Ticking it does not build
anything inline: ``setup_demo`` only ENQUEUES the build with
``enqueue_after_commit=True`` (frappe/utils/background_jobs.py:168 defers the
enqueue onto ``frappe.db.after_commit``), so nothing is queued unless setup
commits and a failing demo can never fail setup. The Company the scenario needs
already exists by then because ERPNext creates it in a ``setup_wizard_stages``
hook and Frappe concatenates stages BEFORE completion hooks
(frappe/desk/page/setup_wizard/setup_wizard.py:36).

The scenario is built by a DEDICATED DEMO USER, so ``owner`` is the removal key:
every row the build creates is selected back by that one column and nothing else.
No name pattern, no date window, no "everything in this DocType".

``DEMO_DOCTYPES`` is the single ordered list both halves read — the build walks it
forward, the removal walks it reversed (ERPNext clears its own demo masters the
same way, erpnext/setup/demo.py:190). ``_create`` refuses a DocType absent from
that list, so the build cannot leave behind a row the removal would never reach.

The removal is the risky half and is written as such: System-Manager-only, it
refuses outright when the demo user is absent rather than sweeping broadly, it
CANCELS a submitted row before deleting it (frappe/model/delete_doc.py:252 refuses
a submitted record outright, and cancelling is what fires the ``on_cancel``
reversal — deleting a Housing Assignment without it strands its Bed on
"Occupied"), and it takes a savepoint per record so one stubborn row leaves the
rest of the clear standing and is REPORTED as residue instead of silently
rolling everything back.

``DEMO_ARG`` is the wizard's own field, deliberately NOT ERPNext's ``setup_demo``: that
fieldname is read by erpnext/setup/setup_wizard/setup_wizard.py:68, so sharing it would
build an entire ERPNext demo company off one tick of the Apex box.
"""

from __future__ import annotations

import random
import string

import frappe
from frappe import _
from frappe.utils import add_days, today

DEMO_ARG = "apex_setup_demo"

DEMO_OWNER = "demo.manager@apex.example"
DEMO_SUPERVISOR = "demo.supervisor@apex.example"
DEMO_USERS = (DEMO_OWNER, DEMO_SUPERVISOR)

DEMO_DOCTYPES = (
    "Project",
    "Site",
    "Building",
    "Room",
    "Bed",
    "Employee",
    "Housing Assignment",
    "Maintenance Request",
)

_DEMO_SITE = "Demo Housing Site"
_DEMO_BUILDING = "Demo Building A"
_DEMO_PROJECT = "Demo Residential Project"
_DEMO_ROOMS = ("DEMO-101", "DEMO-102")


def setup_demo(args=None):
    """`setup_wizard_complete` hook — queue the demo build if the operator asked.

    Mirrors erpnext/setup/setup_wizard/setup_wizard.py:67-69."""
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
    """Build the demo scenario as the demo user. Background job — never inline.

    From ``set_user(DEMO_OWNER)`` on, every insert stamps ``owner = DEMO_OWNER``
    (frappe/model/document.py:601-605), which is the whole removal key.

    Nothing commits here: ``execute_job`` commits a job that returns and rolls back one
    that raises (frappe/utils/background_jobs.py:248-257), so a half-built demo can
    never survive.
    """
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
        for name in frappe.get_all(doctype, filters={"owner": DEMO_OWNER}, pluck="name"):
            error = _remove_one(doctype, name)
            if error:
                residue.append({"doctype": doctype, "name": name, "error": error})
            else:
                deleted += 1

    frappe.db.commit()  # audit-ok — bounds the blast radius of the user deletion
    deleted, residue = _remove_demo_users(deleted, residue)

    frappe.cache.delete_keys("bootinfo")
    _report(deleted, residue)
    return {"deleted": deleted, "residue": residue}


def _remove_one(doctype, name):
    """Cancel-then-delete one record inside its own savepoint.

    Returns None on success, or the error text of a record that survived.

    The savepoint is driven directly rather than through frappe.db.savepoint's
    context manager (frappe/database/database.py:1537): that wrapper swallows the
    exception, and the exception text IS the residue report."""
    save_point = "".join(random.sample(string.ascii_lowercase, 10))
    frappe.db.savepoint(save_point)
    try:
        doc = frappe.get_doc(doctype, name)
        if doc.docstatus == 1:
            doc.cancel()
        frappe.delete_doc(
            doctype,
            name,
            ignore_permissions=True,  # audit-ok — System-Manager-gated demo clear
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

    Frappe attaches a Contact to every User it creates, from a background job
    (frappe/core/doctype/user/user.py:235-241). The Contact names are read BEFORE the
    users are deleted, because ``User.on_trash`` nulls the very link that query reads
    (user.py:539-540) — which is also why the user goes first: that unlink means the
    Contact can never block the deletion, and deleting the Contact in the same
    transaction is what makes the unlink raise ER_CHECKREAD."""
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
    frappe.db.commit()  # audit-ok — a fresh snapshot for the contacts just unlinked

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
    """The owner key and the scoped persona. Created as the installing user, so
    they are never swept by the owner filter and are deleted explicitly instead."""
    for email, full_name, roles in (
        (DEMO_OWNER, "Demo Manager", ("System Manager",)),
        (DEMO_SUPERVISOR, "Demo Supervisor", ("Resident Supervisor",)),
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
        ).insert(ignore_permissions=True)  # audit-ok — first-run demo provisioning
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
    ).insert(ignore_permissions=True)  # audit-ok — first-run demo provisioning


def _create(doctype, payload):
    """Insert one demo record, refusing any DocType the removal would not reach."""
    if doctype not in set(DEMO_DOCTYPES):
        frappe.throw(
            _("{0} is not a demo DocType; the demo removal would never clear it.").format(
                doctype
            )
        )
    doc = frappe.get_doc(dict(payload, doctype=doctype))
    doc.insert(ignore_permissions=True)  # audit-ok — first-run demo provisioning
    return doc


def _company():
    return frappe.defaults.get_global_default("company") or frappe.db.get_value("Company", {})


def _build_project(context):
    context["company"] = _company()
    context["project"] = _create(
        "Project", {"project_name": _DEMO_PROJECT, "company": context["company"]}
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
        "responsible_facility_supervisor": DEMO_SUPERVISOR,
    }
    cost_center = frappe.get_cached_value("Company", company, "cost_center") if company else None
    if cost_center:
        payload["default_cost_center"] = cost_center
    context["building"] = _create("Building", payload).name


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
    context["employee"] = _create(
        "Employee",
        {
            "first_name": "Demo Resident",
            "company": context["company"],
            "gender": "Male",
            "date_of_birth": "1990-01-01",
            "date_of_joining": add_days(today(), -365),
            "status": "Active",
        },
    ).name


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


_BUILD_STEPS = (
    ("Project", _build_project),
    ("Site", _build_site),
    ("Building", _build_building),
    ("Room", _build_rooms),
    ("Bed", _build_beds),
    ("Employee", _build_employee),
    ("Housing Assignment", _build_assignment),
    ("Maintenance Request", _build_maintenance_request),
)
