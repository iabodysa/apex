"""Seed the native ERPNext Issue masters that back the Salis (movement/fleet)
support-ticket experience after Support Ticket was retired in favour of Issue +
SLA.

Mirrors ``salis/notifications_seed.py``: every step is idempotent (created only
if absent, so admins can freely edit afterwards) and existence-guarded on the
DocType it touches, so running it twice — or before ERPNext is fully migrated —
never raises and never aborts ``bench migrate``.

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
   the *default* SLA for Issue so every new portal Issue is auto-tracked.

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

# Issue Type categories — replace Support Ticket.category. Stable English names.
_ISSUE_TYPES = ["Vehicle", "Fuel", "Attendance", "Salary", "Other"]

# Issue Priority masters — replace Support Ticket.priority. Created only if
# absent so we never clobber an ERPNext-shipped priority.
_ISSUE_PRIORITIES = ["Low", "Medium", "High", "Urgent"]

# SLA targets per priority, in seconds (response_time, resolution_time).
# Response must never exceed resolution (the SLA controller enforces this).
_SLA_NAME = "Salis Support SLA"
_SLA_PRIORITIES = [
    # priority, response (s), resolution (s), is_default
    ("Urgent", 1 * 3600, 4 * 3600, 0),
    ("High", 2 * 3600, 8 * 3600, 0),
    ("Medium", 4 * 3600, 24 * 3600, 1),  # default priority
    ("Low", 8 * 3600, 72 * 3600, 0),
]

_WORKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# Role DocPerms to grant on the core "Issue" DocType so Salis drivers can see
# their own Issues and fleet staff can manage them on the desk. The portal
# itself works via ignore_permissions; these are for the desk. Granting via
# frappe.permissions.add_permission creates *Custom DocPerm* rows — it never
# edits the core Issue JSON, so it is upgrade-safe. Each grant is role-existence
# guarded. permlevel 0 throughout.
#   role -> dict of permission flags to enable (besides "read", always implied).
_ISSUE_ROLE_PERMS = [
    # Driver: create + read own only (if_owner). Scoped so a driver only ever
    # sees the Issues they raised.
    ("Driver", {"read": 1, "create": 1, "if_owner": 1}),
    # Fleet staff manage Issues: read + write (no create restriction needed).
    ("Fleet Manager", {"read": 1, "write": 1}),
    ("Fleet Supervisor", {"read": 1, "write": 1}),
    ("Fleet Project Manager", {"read": 1, "write": 1}),
    # Oversight: read-only.
    ("Finance Manager", {"read": 1}),
    ("Internal Auditor", {"read": 1}),
]


def _seed_issue_types():
    if not frappe.db.exists("DocType", "Issue Type"):
        return
    for name in _ISSUE_TYPES:
        if frappe.db.exists("Issue Type", name):
            continue
        frappe.get_doc({"doctype": "Issue Type", "name": name}).insert(
            ignore_permissions=True
        )  # audit-ok — system master seed


def _seed_issue_priorities():
    if not frappe.db.exists("DocType", "Issue Priority"):
        return
    for name in _ISSUE_PRIORITIES:
        if frappe.db.exists("Issue Priority", name):
            continue
        frappe.get_doc({"doctype": "Issue Priority", "name": name}).insert(
            ignore_permissions=True
        )  # audit-ok — system master seed


def _pick_holiday_list():
    """A Service Level Agreement requires a Holiday List. Return one to use, or
    None if the site has none (in which case the SLA seed is skipped — it is not
    worth fabricating a holiday list here)."""
    # Prefer the default Company's holiday list — the real business calendar the
    # SLA timers should pause on. Fall back to the HR Settings default (its field
    # name varies by HRMS version, so read it best-effort), then to ANY Holiday
    # List so a fresh ERPNext site still gets a usable SLA.
    company = frappe.defaults.get_global_default("company") or frappe.db.get_value(
        "Company", {}, "name"
    )
    if company:
        hl = frappe.db.get_value("Company", company, "default_holiday_list")
        if hl and frappe.db.exists("Holiday List", hl):
            return hl
    try:
        default = frappe.db.get_single_value("HR Settings", "default_holiday_list")
        if default and frappe.db.exists("Holiday List", default):
            return default
    except Exception:
        pass
    return frappe.db.get_value("Holiday List", {}, "name")


def _seed_sla():
    if not frappe.db.exists("DocType", "Service Level Agreement"):
        return
    if frappe.db.exists("Service Level Agreement", {"name": _SLA_NAME}) or frappe.db.exists(
        "Service Level Agreement", {"service_level": _SLA_NAME}
    ):
        return
    # The targeted DocType + its priorities must exist before we can link them.
    if not frappe.db.exists("DocType", "Issue"):
        return
    holiday_list = _pick_holiday_list()
    if not holiday_list:
        # No Holiday List on this site — an SLA cannot be saved without one.
        # Skip silently; an admin can create the SLA once a Holiday List exists.
        frappe.logger().info(
            "apex_habitat issue_seed: skipped Salis Support SLA (no Holiday List on site)"
        )
        return

    # Tracking must be enabled for an Issue SLA to validate/save.
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

    # 24x7 service window — full-day coverage every weekday.
    for day in _WORKDAYS:
        doc.append(
            "support_and_resolution",
            {"workday": day, "start_time": "00:00:00", "end_time": "23:59:59"},
        )

    # The SLA is fulfilled once the Issue reaches a terminal state.
    for status in ("Resolved", "Closed"):
        doc.append("sla_fulfilled_on", {"status": status})

    doc.insert(ignore_permissions=True)  # audit-ok — system SLA seed


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
            continue  # role not seeded on this site — skip, never fatal
        # Create the Custom DocPerm row at permlevel 0 if absent (no-op if present).
        add_permission("Issue", role, ptype="read", permlevel=0)
        # Converge every flag explicitly (read/create/write/if_owner) so a re-run
        # is self-healing and matches the documented intent.
        for ptype, value in flags.items():
            update_permission_property("Issue", role, 0, ptype, value)


def seed_salis_issue_masters():
    """Create the Salis Issue Types, Issue Priorities and one default SLA on
    Issue if absent. Idempotent + existence-guarded — safe to run on every
    install and migrate."""
    # Per-step savepoint: a failure in one step (e.g. the SLA, which needs a
    # Holiday List) must NOT roll back the others (Issue Types / Priorities /
    # perms). Log first, then undo only that step.
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
