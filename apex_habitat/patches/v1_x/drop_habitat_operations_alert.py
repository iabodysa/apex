# ONE-TIME cleanup — safe to PRUNE once every deployed site has run it.
#
# Drops the deprecated "Habitat Operations Alert" DocType, its backing table and
# its companion "Unresolved Alerts" Number Card. It was superseded by the Salis
# "Operations Alert" DocType: scheduler tasks now surface warnings through native
# Frappe Notifications (see habitat/notifications_seed.py) instead of inserting
# custom alert rows, so the old DocType has no writer or reader left. The stored
# rows had no reader, so they are discarded with the DocType (no migration).
#
# The "Unresolved Alerts" Number Card is re-pointed (by the shipped fixture) at
# "Operations Alert"; this patch only removes the Card if it is still bound to the
# dropped DocType on an installed site, so the apex_core workspace tile keeps
# working off the refreshed fixture.
#
# Idempotent: a no-op on a fresh install or once already dropped.

import frappe


def execute():
    # --- Number Card: drop only if still bound to the deprecated DocType. ---
    if frappe.db.exists("Number Card", "Unresolved Alerts"):
        try:
            bound_to = frappe.db.get_value(
                "Number Card", "Unresolved Alerts", "document_type"
            )
            if bound_to == "Habitat Operations Alert":
                frappe.delete_doc(
                    "Number Card",
                    "Unresolved Alerts",
                    force=1,
                    ignore_missing=True,
                    ignore_permissions=True,  # audit-ok: system-managed cleanup patch
                )
                frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            frappe.log_error(
                title="drop_habitat_operations_alert: number card cleanup failed",
                message=frappe.get_traceback(),
            )

    # --- DocType + backing table. ---
    has_doctype = frappe.db.exists("DocType", "Habitat Operations Alert")
    has_table = "tabHabitat Operations Alert" in frappe.db.get_tables()

    if not (has_doctype or has_table):
        return  # fresh install or already dropped

    try:
        # force=1 drops the table too; ignore_missing keeps this idempotent.
        frappe.delete_doc(
            "DocType",
            "Habitat Operations Alert",
            force=1,
            ignore_missing=True,
            ignore_permissions=True,  # audit-ok: system-managed schema cleanup patch
        )
        # Drop a stray table left behind if the DocType record was already gone.
        if "tabHabitat Operations Alert" in frappe.db.get_tables():
            frappe.db.sql_ddl("DROP TABLE IF EXISTS `tabHabitat Operations Alert`")

        frappe.db.commit()
        frappe.logger().info(
            "apex_habitat patch: dropped deprecated DocType "
            "'Habitat Operations Alert' and its 'Unresolved Alerts' Number Card"
        )
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            title="drop_habitat_operations_alert: failed to drop DocType",
            message=frappe.get_traceback(),
        )
