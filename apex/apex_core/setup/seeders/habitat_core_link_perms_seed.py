# Copyright (c) 2026, AFMCO and contributors
"""Picker-level access to the core masters this app's own documents link to.

Apex ships its own roles, so nothing in erpnext or hrms names them. That left the
roles that OWN Housing Assignment unable to resolve three of its own Link fields:
Resident (Dynamic Link -> Employee), Project (mandatory) and Cost Center (fetched
from the Building) — and, for the same reason, left every Salis role unable to resolve
the Project field its own movement documents are anchored on. Two surfaces failed on it,
in ways that did not look related:

  * ``frappe.client.validate_link`` refuses a caller with neither read nor select on
    the target (``frappe/client.py:447``), and the Desk Link control routes every
    selection through it, so picking a Resident or a Project on the form silently
    left the field empty.
  * ``frappe.desk.query_report.run`` asks ``build_match_conditions`` for every Link
    column that carries a value, which raises ``No permission to read {0}``
    (``frappe/model/db_query.py:1014``). Active Resident Register therefore ran clean
    on an empty site and returned 403 as soon as one row existed.

SELECT, NOT READ. ``select`` is exactly what a Link picker and a report's match
conditions consume (both accept ``select or read``); it does not open the Employee
form, its list, or a report over it. Granting ``read`` to reach a picker would hand
these roles every Employee record instead.

BLAST RADIUS. ``add_permission`` calls ``setup_custom_perms``
(``frappe/permissions.py:645``), which on the FIRST custom row for a doctype copies
that doctype's shipped DocPerms into Custom DocPerm. From then on the site's
Employee / Project / Cost Center permissions are site-local and no longer track an
erpnext or hrms upgrade. That is inherent to customising a core doctype's
permissions and is the same trade this app already accepted for Issue in
``salis_issue_seed.py``.

Idempotent and existence-guarded, and wired into after_install AND after_migrate so
a fresh site and an upgraded one converge to the same rows.
"""

import frappe

# The core masters a Habitat document links to but does not own.
CORE_LINK_MASTERS = ("Employee", "Project", "Cost Center")

# The Habitat roles published on Housing Assignment and on its register report.
# System Manager is deliberately absent: it is a platform role, and re-granting core
# HR/accounting masters to it is a site administration decision, not this app's.
HABITAT_LINK_ROLES = ("Accommodation Manager", "Resident Supervisor", "Internal Auditor")

# Salis anchors thirteen of its own DocTypes on Project, and a Project User Permission
# is the key `apex.salis.permissions` scopes every one of those lists by. That scoping
# reads the User Permission table directly, so it works with no DocPerm at all — but the
# Project PICKER on the forms that set the field does not: `validate_link` refuses a
# caller holding neither read nor select (frappe/client.py:447), and Project ships only a
# permlevel-1 Desk User row, which `get_role_permissions` discards (frappe/permissions.py:284).
SALIS_LINK_MASTERS = ("Project",)

# The Salis roles that create or write a Project-anchored Salis document. System Manager
# writes them too and is excluded for the same reason as above.
SALIS_LINK_ROLES = (
    "Fleet Manager",
    "Fleet Project Manager",
    "Fleet Supervisor",
    "Finance Manager",
)

# (masters, roles) per module. One table so a third module adds a line, not a function.
_GRANTS = (
    (CORE_LINK_MASTERS, HABITAT_LINK_ROLES),
    (SALIS_LINK_MASTERS, SALIS_LINK_ROLES),
)


# Custom DocPerm defaults read and export to 1 (``custom_docperm.json:81,170``), so a
# row asked for with ptype="select" is born carrying BOTH — a silent widening past what
# a Link picker needs. They are cleared explicitly on a row this seeder creates.
_DEFAULTED_ON_A_NEW_ROW = ("read", "export")


def _grant_select(doctype: str, roles) -> None:
    from frappe.permissions import add_permission, update_permission_property

    for role in roles:
        # Dict form: the positional spelling returns the name unqueried when it equals
        # its own doctype, so it cannot prove existence in both directions.
        if not frappe.db.exists("Role", {"name": role}):
            continue
        rows = frappe.get_all(
            "Custom DocPerm",
            filters={"parent": doctype, "role": role, "permlevel": 0, "if_owner": 0},
            pluck="name",
        )
        if not rows:
            add_permission(doctype, role, ptype="select", permlevel=0)
            for ptype in _DEFAULTED_ON_A_NEW_ROW:
                update_permission_property(doctype, role, 0, ptype, 0)
        # An existing rule only GAINS select. Its other flags are left alone: they were
        # set by a site administrator or another seeder, and this grant does not own
        # them — re-zeroing them on every migrate would silently revoke that decision.
        update_permission_property(doctype, role, 0, "select", 1)


def seed_habitat_core_link_perms():
    """Grant each module's roles ``select`` on the core masters their documents link to.

    One savepoint per (module, doctype): a master that is absent or refuses must not
    abort the rest of the migrate.
    """
    for masters, roles in _GRANTS:
        for doctype in masters:
            if not frappe.db.exists("DocType", {"name": doctype}):
                continue
            savepoint = "core_link_perms"
            frappe.db.savepoint(savepoint)
            try:
                _grant_select(doctype, roles)
            except Exception:
                frappe.db.rollback(save_point=savepoint)
                frappe.log_error(f"Core link permission seed failed for {doctype}")
