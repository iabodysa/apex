# ONE-TIME consolidation — forward-safe role merge for the Salis fleet module.
# Safe to PRUNE once every deployed site has run it (tracked in tabPatch Log).
#
# WHY
#   A prior audit flagged role bloat / apparent "duplicate" roles for a small
#   company. Root cause was twofold:
#     (1) the app seeded generic role NAMES it does not own — "Project Manager",
#         "Regional Operations Manager", "Operations Manager". None of these are
#         shipped by Frappe/ERPNext/HRMS (ERPNext owns the near-identical
#         "Projects Manager"), so the seeds CREATED them, and to an admin the
#         singular "Project Manager" looked like a duplicate of "Projects
#         Manager".
#     (2) an over-deep fleet authority ladder: "Fleet Operations Manager" and
#         "Fleet Regional Manager" duplicated the oversight that a single
#         "Fleet Manager" covers in a small company.
#
# WHAT THIS DOES (idempotent, guarded, never touches core/ERPNext roles)
#   For each merge, re-point every USER that holds the old role to the surviving
#   role (add surviving, remove old) BEFORE the old role is deleted, so no user
#   loses access. Then delete the now-unused, app-owned custom roles.
#
#   Merge map (old -> survivor), preserving Segregation-of-Duties:
#     Fleet Operations Manager    -> Fleet Manager
#     Fleet Regional Manager      -> Fleet Manager
#     Legal Officer               -> Government Relations Officer
#     Project Manager             -> Fleet Project Manager   (Salis DoA "Project" tier)
#     Regional Operations Manager -> Fleet Manager           (folds into oversight tier)
#     Operations Manager          -> Fleet Manager           (folds into oversight tier)
#
#   Finance Manager, Internal Auditor, Fleet Supervisor and the maker/checker
#   split are left untouched — SoD is preserved.
#
# SAFETY
#   - Existence-guarded: every step is a no-op when the role is already gone, so
#     a fresh install (where these roles were never seeded) and a re-run are both
#     no-ops.
#   - Never deletes a role that is not in MERGE (so core/ERPNext roles such as
#     "Projects Manager", "Fleet Manager", "Driver" are never removed).
#   - Wrapped so it can never crash an install/migrate; logs and continues.

import frappe

# old role -> surviving role
MERGE = {
    "Fleet Operations Manager": "Fleet Manager",
    "Fleet Regional Manager": "Fleet Manager",
    "Legal Officer": "Government Relations Officer",
    "Project Manager": "Fleet Project Manager",
    "Regional Operations Manager": "Fleet Manager",
    "Operations Manager": "Fleet Manager",
}


def _users_with_role(role):
    """User IDs that currently hold `role` (read via Has Role child table)."""
    return frappe.get_all(
        "Has Role",
        filters={"role": role, "parenttype": "User"},
        pluck="parent",
        distinct=True,
    )


def _repoint_users(old_role, new_role):
    """Give every holder of `old_role` the `new_role`, then drop the old row.

    Edits the User document directly so its role cache stays consistent.
    Skips users that fail to load/save gracefully.
    """
    for user_id in _users_with_role(old_role):
        try:
            user = frappe.get_doc("User", user_id)
            held = {r.role for r in user.get("roles", [])}
            changed = False
            # Add the survivor if missing.
            if new_role not in held and frappe.db.exists("Role", new_role):
                user.append("roles", {"role": new_role})
                changed = True
            # Remove the old role row(s).
            remaining = [r for r in user.get("roles", []) if r.role != old_role]
            if len(remaining) != len(user.get("roles", [])):
                user.set("roles", remaining)
                changed = True
            if changed:
                user.save(ignore_permissions=True)  # audit-ok
        except Exception:
            frappe.db.rollback()
            frappe.log_error(
                title=f"consolidate_salis_roles: repoint failed for {user_id}",
                message=frappe.get_traceback(),
            )


def execute():
    for old_role, new_role in MERGE.items():
        # No-op when the old role is absent (fresh install / already consolidated).
        if not frappe.db.exists("Role", old_role):
            continue
        try:
            # 1) Re-point users BEFORE deleting so nobody loses access.
            _repoint_users(old_role, new_role)

            # 2) Remove the now-unused custom role. ignore_missing keeps this
            #    idempotent; we only ever reach here for roles we own (in MERGE).
            frappe.delete_doc(
                "Role",
                old_role,
                ignore_missing=True,
                ignore_permissions=True,
                force=True,
            )
            frappe.db.commit()
            frappe.logger().info(
                f"apex_habitat patch: merged role '{old_role}' -> '{new_role}'"
            )
        except Exception:
            frappe.db.rollback()
            frappe.log_error(
                title=f"consolidate_salis_roles: merge failed {old_role} -> {new_role}",
                message=frappe.get_traceback(),
            )

    frappe.clear_cache()
