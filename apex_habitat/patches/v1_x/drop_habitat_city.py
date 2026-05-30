# ONE-TIME cleanup — safe to PRUNE once every deployed site has run it.
#
# Drops the empty, deprecated "Habitat City" DocType and its backing table. Its
# rows were already migrated to the "City" DocType by the date-gated
# v0_7.rename_habitat_city_to_city patch, and the source fixture has since been
# removed (only stale compiled artifacts remained). On an installed site the
# renamed-away DocType record / table may still linger, so this removes them.
#
# Idempotent: a no-op on a fresh install or once already dropped.

import frappe


def execute():
    has_doctype = frappe.db.exists("DocType", "Habitat City")
    has_table = "tabHabitat City" in frappe.db.get_tables()

    if not (has_doctype or has_table):
        return  # fresh install or already dropped / renamed away

    try:
        # force=1 drops the table too; ignore_missing keeps this idempotent.
        frappe.delete_doc(
            "DocType",
            "Habitat City",
            force=1,
            ignore_missing=True,
            ignore_permissions=True,  # audit-ok: system-managed schema cleanup patch
        )
        # Drop a stray table left behind if the DocType record was already gone.
        if "tabHabitat City" in frappe.db.get_tables():
            frappe.db.sql_ddl("DROP TABLE IF EXISTS `tabHabitat City`")

        frappe.db.commit()
        frappe.logger().info(
            "apex_habitat patch: dropped deprecated empty DocType 'Habitat City'"
        )
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            title="drop_habitat_city: failed to drop DocType",
            message=frappe.get_traceback(),
        )
