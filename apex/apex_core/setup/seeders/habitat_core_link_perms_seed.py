# Copyright (c) 2026, AFMCO and contributors
"""Picker-level access to the core masters Habitat's own documents link to.

Habitat ships its own roles, so nothing in erpnext or hrms names them. That left the
roles that OWN Housing Assignment unable to resolve three of its own Link fields:
Resident (Dynamic Link -> Employee), Project (mandatory) and Cost Center (fetched
from the Building). Two surfaces failed on it, in ways that did not look related:

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


# Custom DocPerm defaults read and export to 1 (``custom_docperm.json:81,170``), so a
# row asked for with ptype="select" is born carrying BOTH — a silent widening past what
# a Link picker needs. They are cleared explicitly on a row this seeder creates.
_DEFAULTED_ON_A_NEW_ROW = ("read", "export")


def _grant_select(doctype: str) -> None:
    from frappe.permissions import add_permission, update_permission_property

    for role in HABITAT_LINK_ROLES:
        if not frappe.db.exists("Role", role):
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
    """Grant the Habitat roles ``select`` on the core masters their documents link to.

    One savepoint per doctype: a master that is absent or refuses must not abort the
    rest of the migrate.
    """
    for doctype in CORE_LINK_MASTERS:
        if not frappe.db.exists("DocType", doctype):
            continue
        savepoint = "habitat_core_link_perms"
        frappe.db.savepoint(savepoint)
        try:
            _grant_select(doctype)
        except Exception:
            frappe.db.rollback(save_point=savepoint)
            frappe.log_error(f"Habitat core link permission seed failed for {doctype}")
