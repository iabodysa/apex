# Copyright (c) 2026, afmcoltd
"""Picker-level access to the core masters this app's own documents link to.

Apex ships its own roles, so nothing in erpnext or hrms names them. That left the
roles that OWN Housing Assignment unable to resolve three of its own Link fields:
Resident (Dynamic Link -> Employee), Project (mandatory) and Cost Center (fetched
from the Building) — and, for the same reason, left every Salis role unable to resolve
the Project field its own movement documents are anchored on. Two surfaces failed on it,
in ways that did not look related.

SELECT, NOT READ. ``select`` is exactly what a Link picker and a report's match
conditions consume (both accept ``select or read``); it does not open the Employee
form, its list, or a report over it. Granting ``read`` to reach a picker would hand
these roles every Employee record instead.

Idempotent and existence-guarded, and wired into after_install AND after_migrate so
a fresh site and an upgraded one converge to the same rows.
"""

import frappe

CORE_LINK_MASTERS = ("Employee", "Project", "Cost Center")

HABITAT_LINK_ROLES = ("Accommodation Manager", "Resident Supervisor", "Internal Auditor")

SALIS_LINK_MASTERS = ("Project",)

SALIS_LINK_ROLES = (
    "Fleet Manager",
    "Fleet Project Manager",
    "Fleet Supervisor",
    "Finance Manager",
)

_GRANTS = (
    (CORE_LINK_MASTERS, HABITAT_LINK_ROLES),
    (SALIS_LINK_MASTERS, SALIS_LINK_ROLES),
)


_DEFAULTED_ON_A_NEW_ROW = ("read", "export")


def _grant_select(doctype: str, roles) -> None:
    """Give each role ``select`` on ``doctype``, and nothing wider.

    ``_DEFAULTED_ON_A_NEW_ROW`` is cleared explicitly because Custom DocPerm defaults
    read and export to 1 (``custom_docperm.json:81,170``), so a row asked for with
    ptype="select" is born carrying BOTH — a silent widening past what a Link picker
    needs.
    """
    from frappe.permissions import add_permission, update_permission_property

    for role in roles:
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
