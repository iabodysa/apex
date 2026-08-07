# Copyright (c) 2026, afmcoltd
"""Seed the native ERPNext Issue masters that back the Salis (movement/fleet)
support-ticket experience after Support Ticket was retired in favour of Issue +
SLA.

Every step is idempotent (created only if absent, so admins can freely edit
afterwards) and existence-guarded on the DocType it touches, so running it twice
— or before ERPNext is fully migrated — never raises and never aborts
``bench migrate``.

Seeds three things:

1. **Issue Type** masters — the categories a driver picks in the portal
   (Vehicle, Fuel, Attendance, Salary, Other). These replace the old
   ``Support Ticket.category`` Select.
2. **Issue Priority** masters — Low / Medium / High / Urgent (created only if
   absent; ERPNext ships only "Low/Medium/High" on some versions and nothing on
   others, so we guard each individually). These replace the old
   ``Support Ticket.priority`` Select.
3. **One Service Level Agreement** on Issue ("Salis Support SLA") with a
   response/resolution target per priority, a 24x7 service window and the
   Issue resolved/closed states as the SLA-fulfilled statuses. It is created as
   the *default* SLA for Issue so every new portal Issue is auto-tracked. Its
   required ``holiday_list`` is the site's own where one exists, otherwise an
   empty fallback list created here — no app provisions a Holiday List on a
   fresh site, and without one this SLA was never created at all.

It also grants the Salis role DocPerms on the core **Issue** DocType (via
``frappe.permissions.add_permission`` / ``update_permission_property``, which
write *Custom DocPerm* rows and never touch the core Issue JSON, so they are
upgrade-safe): Driver gets create+read of its own Issues (if_owner), the fleet
roles get read+write, and the oversight roles get read. This lets drivers see
their own Issues and fleet staff manage them on the desk (the portal already
works via ignore_permissions).

Driver-facing strings are English-first; the category/priority names are stable
English identifiers (the Arabic surfaces through ``translations/ar.csv`` and the
portal's own i18n bundle).
"""

import frappe

_ISSUE_TYPES = ["Vehicle", "Fuel", "Attendance", "Salary", "Other"]

_ISSUE_PRIORITIES = ["Low", "Medium", "High", "Urgent"]

_SLA_NAME = "Salis Support SLA"
_SLA_PRIORITIES = [
    ("Urgent", 1 * 3600, 4 * 3600, 0),
    ("High", 2 * 3600, 8 * 3600, 0),
    ("Medium", 4 * 3600, 24 * 3600, 1),
    ("Low", 8 * 3600, 72 * 3600, 0),
]

_WORKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

_SLA_HOLIDAY_LIST = "Apex Support 24x7"
_SLA_HOLIDAY_WINDOW = ("2000-01-01", "2099-12-31")

_ISSUE_ROLE_PERMS = [
    ("Driver", {"read": 1, "create": 1, "if_owner": 1}),
    ("Fleet Manager", {"read": 1, "write": 1}),
    ("Fleet Supervisor", {"read": 1, "write": 1}),
    ("Fleet Project Manager", {"read": 1, "write": 1}),
    ("Finance Manager", {"read": 1}),
    ("Internal Auditor", {"read": 1}),
]


def _seed_issue_types():
    """Creates each missing Issue Type master used by the Salis driver portal."""
    if not frappe.db.exists("DocType", "Issue Type"):
        return
    for name in _ISSUE_TYPES:
        if frappe.db.exists("Issue Type", name):
            continue
        frappe.get_doc({"doctype": "Issue Type", "name": name}).insert(
            ignore_permissions=True
        )


def _seed_issue_priorities():
    """Creates each missing Issue Priority master used by the Salis driver portal."""
    if not frappe.db.exists("DocType", "Issue Priority"):
        return
    for name in _ISSUE_PRIORITIES:
        if frappe.db.exists("Issue Priority", name):
            continue
        frappe.get_doc({"doctype": "Issue Priority", "name": name}).insert(
            ignore_permissions=True
        )


def _pick_holiday_list():
    """Return the site's own Holiday List to hang the SLA on, or None if it has none."""
    company = frappe.defaults.get_global_default("company") or frappe.db.get_value(
        "Company", {}, "name"
    )
    if company:
        hl = frappe.db.get_value("Company", company, "default_holiday_list")
        if hl and frappe.db.exists("Holiday List", hl):
            return hl
    return frappe.db.get_value("Holiday List", {}, "name")


def _ensure_holiday_list():
    """Return a Holiday List for the SLA, creating the fallback one if the site has none.

    ``Service Level Agreement.holiday_list`` is a REQUIRED core ERPNext Link and
    nothing on a fresh site creates a Holiday List — neither the ERPNext setup
    wizard nor hrms — so waiting for one meant the default Issue SLA was never
    created on any new deployment. An existing list always wins, so this changes
    nothing on a configured site.
    """
    existing = _pick_holiday_list()
    if existing:
        return existing
    if not frappe.db.exists("DocType", "Holiday List"):
        return None
    doc = frappe.new_doc("Holiday List")
    doc.holiday_list_name = _SLA_HOLIDAY_LIST
    doc.from_date = _SLA_HOLIDAY_WINDOW[0]
    doc.to_date = _SLA_HOLIDAY_WINDOW[1]
    doc.insert(ignore_permissions=True)
    return doc.name


def _seed_sla():
    """Creates the default Salis Support SLA on Issue with per-priority response and resolve targets."""
    if not frappe.db.exists("DocType", "Service Level Agreement"):
        return
    if frappe.db.exists("Service Level Agreement", {"name": _SLA_NAME}) or frappe.db.exists(
        "Service Level Agreement", {"service_level": _SLA_NAME}
    ):
        return
    if not frappe.db.exists("DocType", "Issue"):
        return
    holiday_list = _ensure_holiday_list()
    if not holiday_list:
        frappe.logger().info(
            "apex issue_seed: skipped Salis Support SLA (no Holiday List on site)"
        )
        return

    if frappe.db.exists("DocType", "Support Settings"):
        if not frappe.db.get_single_value("Support Settings", "track_service_level_agreement"):
            frappe.db.set_single_value("Support Settings", "track_service_level_agreement", 1)

    doc = frappe.new_doc("Service Level Agreement")
    doc.service_level = _SLA_NAME
    doc.document_type = "Issue"
    doc.default_service_level_agreement = 1
    doc.enabled = 1
    doc.apply_sla_for_resolution = 1
    doc.holiday_list = holiday_list

    for priority, response, resolution, is_default in _SLA_PRIORITIES:
        if not frappe.db.exists("Issue Priority", priority):
            continue
        doc.append(
            "priorities",
            {
                "priority": priority,
                "response_time": response,
                "resolution_time": resolution,
                "default_priority": is_default,
            },
        )

    for day in _WORKDAYS:
        doc.append(
            "support_and_resolution",
            {"workday": day, "start_time": "00:00:00", "end_time": "23:59:59"},
        )

    for status in ("Resolved", "Closed"):
        doc.append("sla_fulfilled_on", {"status": status})

    doc.insert(ignore_permissions=True)


def _grant_issue_role_perms():
    """Grant the Salis role DocPerms on the core "Issue" DocType (Custom DocPerm
    rows only — never edits core JSON). Idempotent: add_permission is a no-op if
    the (role, permlevel) row already exists; we then set each flag explicitly so
    a re-run converges to the intended state. Role-existence guarded so an unmet
    role is skipped, never fatal."""
    if not frappe.db.exists("DocType", "Issue"):
        return

    from frappe.permissions import add_permission, update_permission_property

    for role, flags in _ISSUE_ROLE_PERMS:
        if not frappe.db.exists("Role", role):
            continue
        rows = frappe.get_all(
            "Custom DocPerm",
            filters={"parent": "Issue", "role": role, "permlevel": 0},
            pluck="name",
        )
        for extra in rows[1:]:
            frappe.delete_doc("Custom DocPerm", extra, ignore_permissions=True)
        if not rows:
            add_permission("Issue", role, ptype="read", permlevel=0)
        for ptype, value in flags.items():
            update_permission_property("Issue", role, 0, ptype, value)


def seed_salis_issue_masters():
    """Create the Salis Issue Types, Issue Priorities and one default SLA on
    Issue if absent. Idempotent + existence-guarded — safe to run on every
    install and migrate."""
    for fn in (_seed_issue_types, _seed_issue_priorities, _seed_sla, _grant_issue_role_perms):
        sp = "salis_issue_seed"
        frappe.db.savepoint(sp)
        try:
            fn()
        except Exception:
            frappe.log_error(
                title=f"seed_salis_issue_masters: {fn.__name__} failed",
                message=frappe.get_traceback(),
            )
            frappe.db.rollback(save_point=sp)
    frappe.db.commit()
