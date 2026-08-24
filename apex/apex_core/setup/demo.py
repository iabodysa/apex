# Copyright (c) 2026, afmcoltd
"""Setup-wizard demo data — one coherent accommodation scenario, and its removal.

The writes and the delete pass ``ignore_permissions`` because this is installer context: the
wizard runs as Administrator on a site that has no operator yet, and the demo user it creates
does not exist until this module creates it. A DocPerm that made these legal would stay live for
every real operator afterwards.

The scenario is built by a DEDICATED DEMO USER, so ``owner`` is the removal key:
every row the build creates is selected back by that one column and nothing else.
No name pattern, no date window, no "everything in this DocType".
"""

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
    """`setup_wizard_complete` hook — queue the demo build if the operator asked.

    Separate from erpnext's own demo (erpnext/setup/demo.py:37), which seeds erpnext
    transactions and cannot create a Building, a Housing Assignment or a Dispatch Trip.
    Both may run on one site; neither clears the other's rows.
    """
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

    Returns ``{"built": bool, "stopped_at": str | None}``. The verdict exists because a
    step failure rolls the whole scenario back and reports to the operator out of band, so
    without it a caller cannot tell a full scenario from an empty one — every outcome looked
    like ``None`` and a build that produced nothing read as one that succeeded.

    ``frappe.set_user`` (frappe/__init__.py:641) makes every record's ``owner`` the
    demo user, which is what the removal keys on — the one thing a background job
    cannot do is remember who asked for it, so ownership IS the marker. The bootinfo
    cache is dropped with ``frappe.cache.delete_keys`` (frappe/utils/redis_wrapper.py)
    so the "remove demo data" control appears without a re-login.
    """
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
    """Names the step that failed to the operator who ticked the demo box.

    The wizard reports success the moment its stages finish, while this job is still
    queued, so a raw exception here surfaces only in a worker log the operator never
    opens. Roll the half-built scenario back, keep the traceback in the Error Log, and
    say which step stopped.

    ``frappe.db.rollback`` (frappe/database/database.py:1186) unwinds the whole job
    rather than a savepoint: a half-built scenario is not a smaller demo, it is an
    inconsistent one. ``frappe.publish_realtime`` (frappe/realtime.py:23) is what
    reaches the operator — the one thing the Error Log cannot do is tell someone who
    has already left the wizard that their build stopped."""
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
    """Clears the demo Rental Settlement's ``payment_request`` link before the removal walks the table.

    ``_build_rental_settlement`` raises the demo Salis Payment Request through
    ``RentalSettlement.create_payment_request()``, which stamps a link BOTH ways: the
    settlement's ``payment_request`` points at the request, and the request's
    ``reference_doctype``/``reference_name`` (Dynamic Link) points back at the
    settlement. Frappe's own link-existence check then refuses either side first —
    each cites the other as the still-standing reference — so no processing order of
    ``DEMO_DOCTYPES`` can ever clear the pair. ``frappe.db.set_value`` breaks the
    settlement's half of the cycle directly (the field is read-only, so the ORM write
    path would refuse it), after which the reversed sweep below deletes the request,
    then the settlement, in the normal order.
    """
    for name in frappe.get_all(
        "Rental Settlement",
        filters={"owner": ["in", list(DEMO_USERS)], "payment_request": ["is", "set"]},
        pluck="name",
    ):
        frappe.db.set_value("Rental Settlement", name, "payment_request", None, update_modified=False)

def _remove_worker_tokens_for_demo_drivers(deleted, residue):
    """Deletes any Masar Worker Token issued for a demo driver, before Salis Driver is swept.

    ``issue_driver_link`` (``masar_worker_token.py``) is the whitelisted API a Fleet
    persona calls from the portal to hand a driver their access link; it stamps the
    token's ``owner`` as whoever called it, never the demo user, and the token is not a
    demo DocType (``DEMO_DOCTYPES`` never lists it). A demo driver left Active is a
    normal target for that call — this site carried one such token from outside the
    build, and it blocked the driver's removal exactly as the settlement/payment cycle
    above blocks each other. Found by the ``driver`` link rather than by ownership,
    since ownership is exactly the column that does not identify it.
    """
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
    """Remove every row the demo build created, and nothing else.

    Returns ``{"deleted": int, "residue": [...]}``. Residue is reported, never
    hidden: a row that refuses to go leaves the rest of the clear standing.

    Clears only what this app's demo built. erpnext's ``clear_demo_data``
    (erpnext/setup/demo.py:37) owns its own rows and is not called from here.
    """
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
    """Cancel-then-delete one record inside its own savepoint.

    Returns None on success, or the error text of a record that survived.

    ``frappe.db.savepoint`` (frappe/database/database.py:1203) isolates each record:
    the one thing ``frappe.delete_doc`` (frappe/model/delete_doc.py:23) cannot do is
    fail cleanly — a link that refuses leaves the cancel already written, and without
    the point the next record inherits it. ``frappe.clear_last_message`` drops the
    framework's own throw text so a survivable refusal is reported in the residue
    list rather than raised at whoever pressed the button.
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
        frappe.delete_doc(doctype, name, ignore_permissions=True, delete_permanently=True)
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
    the whole clear from inside the very handler meant to contain one bad record.

    ``frappe.db.release_savepoint`` and ``rollback``
    (frappe/database/database.py:1186) both accept the point; the one thing neither
    can do is tell a missing point from a failed release, so the absence is tolerated
    here rather than distinguished. ``frappe.clear_last_message`` drops the framework
    throw text that would otherwise reach the operator twice."""
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

    ``frappe.db.commit`` (frappe/database/database.py:1173) lands the removal before
    the users go: the demo user is the key every other row is found by, so the one
    thing that must not happen is losing the key while rows remain.
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
    they are never swept by the owner filter and are deleted explicitly instead.

    Runs before ``build_demo_data`` switches to ``DEMO_OWNER`` below, so the acting
    user is still whoever completed the setup wizard's demo checkbox — the only
    account that could have, since ``setup_demo`` fires from ``setup_wizard_complete``,
    gated behind ``frappe.is_setup_complete()``
    (frappe/desk/page/setup_wizard/setup_wizard.py:54-55) — Administrator, who already
    carries every permission (frappe/permissions.py:107,273,506).
    """
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
    """Insert one demo record, refusing any DocType the removal would not reach."""
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
    """Applies a sequence of workflow actions to a document while impersonating ``user``
    (the demo approver by default, so every existing call site is unaffected).

    ``frappe.set_user`` (frappe/__init__.py:641) does the switch and the restore is in
    a ``finally``: the one thing ``set_user`` cannot do is put the session back, and a
    background worker is reused, so a session left elevated carries into whatever runs
    next. ``apply_workflow`` (frappe/model/workflow.py) is the transition itself — the
    states are never written directly, so the demo exercises the same gate an operator
    would.
    """
    previous_user = frappe.session.user
    frappe.set_user(user)
    try:
        doc = frappe.get_doc(doctype, name)
        for action in actions:
            apply_workflow(doc, action)
    finally:
        frappe.set_user(previous_user)

def _build_partner_company(context):
    """Creates the demo partner Company, reusing the real company's currency and country.

    The fallback is the SITE's own default, never a pinned code: a demo built on a site
    whose company trades in another currency would otherwise show every seeded figure in
    one this operator does not use. The chain is ``resolve_company_or_any``, which ends
    at ``frappe.defaults.get_global_default`` (frappe/defaults.py) — the one thing a
    literal currency cannot do is follow the site it lands on.
    """
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
                "bed_code": "{0}-{1}".format(room, suffix),
                "status": "Available",
                "condition": "Good",
            },
        ).name
        for room in context["rooms"]
        for suffix in ("A", "B")
    ]

def _demo_gender():
    """Returns a Gender that exists on THIS site, creating one only if none ever arrives.

    Employee.gender is mandatory and is a Link, so a hardcoded "Male" fails outright on a
    site whose Gender records are not there yet — the LinkValidationError measured on a bare
    site. They are not there yet because Frappe installs its Gender fixtures only after every
    setup stage has run, while this build is queued from a stage; writing our own row in that
    window deadlocks against the fixture's insert on tabgender. So wait for the framework's
    rows first and write one only if the wait runs out. Rolling back between reads is what
    lets this connection see the other transaction's commit — and is why this is resolved
    before the build starts rather than at the Employee step, where the same rollback threw
    away every row already built and left the next link pointing at nothing.

    ``frappe.db.rollback`` (frappe/database/database.py:1186) between reads is not
    cleanup here — it is the only way this connection sees the fixture transaction's
    commit, which is the one thing a long-running read cannot do on its own."""
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
    """Creates the demo resident, supplier-worker, and leaver Employee records."""
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
            "account_number": "SEC-2205841",
            "status": "Active",
        },
    ).name

def _build_facility_asset(context):
    """Creates the demo CCTV Facility Asset for the demo building."""
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
    """Give the scoped demo personas the User Permission their role needs.

    Fleet Supervisor and Resident Supervisor are SCOPED roles — they are absent from
    ``salis.permissions.UNSCOPED_ROLES``, so ``permission_query_conditions`` confines
    them to the projects and buildings a User Permission grants, and a persona with no
    grant can read nothing at all. The demo walks a Driver Clearance workflow as the
    fleet supervisor, which is refused outright without this.

    This is what a real deployment does for a scoped supervisor, so granting it here
    exercises the scoping rather than stepping around it: the persona sees the demo
    project and nothing else, which is the behaviour worth demonstrating.

    Runs under ``frappe.set_user(DEMO_OWNER)`` (``build_demo_data``), and ``DEMO_OWNER``
    holds System Manager, which already carries create on User Permission — granting
    a permission scope to someone ELSE is an ordinary create, not a right the grantor
    needs to hold themselves (``user_permission.py`` validates only for duplicates and
    the record's own shape).
    """
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
    """Creates the demo Salis Driver, on the demo project.

    The project is not decoration. Every Salis document is scoped through the driver's
    or vehicle's project (``salis.permissions``), so a driver with no project is
    invisible to every SCOPED role — a Fleet Supervisor is then refused read on the
    driver's own clearance, and the workflow this demo walks cannot start.
    """
    context["driver"] = _create(
        "Salis Driver",
        {
            "full_name": "Hassan Al-Amri",
            "status": "Active",
            "project": context["project"],
        },
    ).name

def _build_vehicle(context):
    """Creates the demo Salis Vehicle.

    ``planned_fuel_grade`` is set here, not on the Fuel Request that follows: it is
    the vehicle's own fact, and Fuel Request.fuel_grade fetches it from
    ``vehicle.planned_fuel_grade`` (``fetch_if_empty``).
    """
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
    """Creates and submits the demo Telecom Contract for the demo supplier.

    Submitted, because SIM Card refuses a contract that is not in force and the demo
    SIMs that follow read as Assigned and Suspended — states only a live contract has.
    """
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
    """Creates two assigned SIM Cards and one suspended SIM Card for the demo employee."""
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
    """The one SUBMITTED row. on_submit marks the bed Occupied and recalculates
    the building's occupancy; on_cancel puts both back — which is why the removal
    cancels before it deletes."""
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
                    "skip_reason": "Awaiting next cleaning round",
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
                    "damage_description": "Torn mattress cover, foam exposed",
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
    """Creates the demo Driver Clearance record and starts its investigation.

    Stops at In Progress rather than walking to Cleared: on_submit's
    ``_release_driver`` would move the shared demo driver to Released and clear
    its current vehicle, breaking every later Salis step that still needs it
    Active.
    """
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
    """Runs the weekly vehicle utilisation snapshot job to populate demo data."""
    weekly_vehicle_utilisation_snapshot()

def _build_accommodation_ledger(context):
    """Allocates today's accommodation cost for the demo building."""
    allocate_building_accommodation_cost(context["building"], today())

def _build_qr_location(context):
    """Creates the demo QR poster for the building entrance."""
    context["qr_location"] = _create(
        "QR Location",
        {
            "poster_title": "{0} — Main Entrance".format(context["building"]),
            "is_active": 1,
            "room": context["rooms"][0],
        },
    ).name

def _build_custody_handover(context):
    """Creates the demo custody handover between the two demo buildings."""
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
    """Creates the active checklist a receipt must be raised against.

    vehicle_handover.py:89-118 requires a template for a receipt, requires it active, and
    requires the handover's rows to equal the template's rows EXACTLY — so the two lists
    are built from one tuple rather than written twice.
    """
    context["handover_template"] = _create(
        "Vehicle Handover Checklist Template",
        {
            "template_name": "Vehicle Handover Checklist",
            "is_active": 1,
            "items": [{"check_item": item} for item in _HANDOVER_CHECKS],
        },
    ).name

def _build_vehicle_assignment(context):
    """Creates the demo vehicle assignment the handover receipt is raised against.

    Submitted, not left a draft: vehicle_handover.py:150 refuses a receipt whose assignment
    is not both submitted and Active, so a draft here fails the step that follows.
    """
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
    """Creates the demo vehicle handover receipt with its inspection checklist.

    ``Receipt``, not the ``Transfer`` the controller defaults to: this is the vehicle's
    first handover, so there is no previous driver, and vehicle_handover.py:44-49 requires
    both drivers for a transfer. A receipt in turn requires the assignment it is raised
    against (vehicle_handover.py:141), which the step above creates.
    """
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
    """Creates the demo open vehicle incident."""
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
    """Creates the demo damage write-off and drives it to Closed.

    The DocType makes `evidence` mandatory, so a placeholder File is attached, because a
    write-off with no photo is a record no approver could act on.

    ``frappe.new_doc`` (frappe/__init__.py:1152) builds the File; an Attach field stores
    a URL, so the placeholder must be a real File row rather than a string — the one
    thing a bare path cannot do is survive the field's own validation.
    """
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
    """Creates the demo pest-control contract and walks it to Active through its workflow."""
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
    """Creates the demo service order against the demo contract."""
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
    """Creates the demo rental office that the settlement is raised against."""
    context["rental_office"] = _create(
        "Rental Office",
        {"office_name": _DEMO_RENTAL_OFFICE, "status": "Active"},
    ).name

def _build_goods_receipt(context):
    """Creates the demo goods receipt into the building store, left in Draft.

    Nothing in the demo is submitted: submitting writes Accommodation Stock Ledger rows, and
    those rows link the building, the article and the employee, so `clear_demo_data` can no
    longer take the demo back. A printable draft is worth more than a demo that will not clear.
    """
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
    """Creates the demo transfer between the two demo buildings."""
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
    """Issues two demo articles to the demo employee, left in Draft.

    A Custody Return cannot be raised against a draft issue, so Custody Return Receipt is the
    one print format with no demo document. The alternative — submitting the issue — writes
    stock ledger rows the demo removal cannot take back, which costs more than it buys.
    """
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
    """Creates the demo work order against the demo maintenance request."""
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
    """Creates the demo open safety incident."""
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
    """Creates the demo weekly safety round for the building."""
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
    """Creates the demo fuel request and drives it to Done.

    ``fuel_grade`` is not set here: it fetches from ``vehicle.planned_fuel_grade``
    (``fetch_if_empty``), which ``_build_vehicle`` now sets.
    """
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
    """Creates the demo monthly fuel claim and drives it to Closed."""
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
    """Creates the demo passenger manifest with the demo employee on board."""
    context["passenger_manifest"] = _create(
        "Passenger Manifest",
        {
            "passengers": [{"employee": context["employee"]}],
        },
    ).name

def _build_rental_settlement(context):
    """Creates the demo monthly rental settlement and drives it to Paid.

    Raises the demo Salis Payment Request along the way through
    ``RentalSettlement.create_payment_request()`` — the same whitelisted method
    Finance uses — rather than re-building the same record by hand;
    ``_build_salis_payment_request`` then walks it through its own workflow.
    """
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
    """Creates the minimal demo Route Template that Route Assignment requires.

    Neither this DocType nor Work Shift ships any fixture or default row, and
    Route Assignment's ``route_template``/``work_shift`` links are both
    mandatory, so a demo Route Assignment cannot exist without building both
    masters first.
    """
    context["route_template"] = _create(
        "Route Template",
        {
            "template_name": "Main Gate Shuttle Route",
            "route_type": "Pickup",
            "stops": [{"stop_name": "{0} — Main Entrance".format(context["building"])}],
        },
    ).name

def _build_work_shift(context):
    """Creates the minimal demo Work Shift that Route Assignment requires."""
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
    """Creates the demo route assignment and approves it.

    Uses the unconditional Fleet Manager approval path: the Fleet Supervisor
    path is gated on ``doc.route_supervisor == frappe.session.user``, which the
    demo does not arrange.
    """
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
    """Creates the demo dispatch trip and dispatches it.

    Stops at Dispatched rather than Completed: reaching Completed submits the
    trip, and ``before_submit`` then requires at least one route stop plus
    either an assigned Transport Request or a boarding-state row, none of
    which this demo wires up.
    """
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
    """Creates the demo site-transport request and drives it to Fulfilled."""
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
    """Creates the demo fuel exception case and drives it to Closed."""
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
    """Creates the demo cost recovery case and drives it to Recovered.

    ``basis_evidence`` is a mandatory Attach field, so a placeholder File is
    attached — the same pattern ``_build_vehicle_write_off`` uses for its own
    mandatory evidence field.

    ``frappe.new_doc`` (frappe/__init__.py:1152) builds the File; an Attach field stores
    a URL, so the placeholder must be a real File row rather than a string — the one
    thing a bare path cannot do is survive the field's own validation.
    """
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
    """Creates the demo inter-project cost transfer and drives it to Posted (memo)."""
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
    """Walks the Salis Payment Request that ``_build_rental_settlement`` raised
    (via ``RentalSettlement.create_payment_request()``) through its own Finance
    approval workflow."""
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
