# ONE-TIME cleanup — safe to PRUNE once every deployed site has run it.
#
# Removes the two dead "alert_type" Select options on the Salis "Operations Alert"
# DocType: "No Fuel" and "Incomplete Handover". Neither value was ever written by
# any scheduler task, engine or API (the fuel-shortage detector raises
# "Forgotten Request"/"Excessive Topup" instead, and no handover flow exists), and
# nothing reads or filters on them. The shipped fixture has been updated to drop
# them from the field options; the schema sync re-imports those options on migrate.
#
# This patch is a defensive backstop: if any legacy row still carries one of the
# removed values it is normalised to "General" so it stays selectable in the new
# (narrower) option set. It does not touch any other field or row.
#
# Idempotent, existence-guarded on table + column (no schema error during
# migrate), and a no-op on a fresh install.

import frappe

_DEAD = ("No Fuel", "Incomplete Handover")
_FALLBACK = "General"


def execute():
    if "tabOperations Alert" not in frappe.db.get_tables():
        return  # fresh install (Salis not yet migrated) or already gone

    columns = frappe.db.get_table_columns("Operations Alert")
    if "alert_type" not in columns:
        return  # column not present yet — let schema sync create it

    try:
        stale = frappe.get_all(
            "Operations Alert",
            filters={"alert_type": ["in", _DEAD]},
            pluck="name",
        )
        if not stale:
            return  # nothing carries a dead value — common path

        for name in stale:
            frappe.db.set_value(
                "Operations Alert",
                name,
                "alert_type",
                _FALLBACK,
                update_modified=False,
            )

        frappe.db.commit()
        frappe.logger().info(
            "apex_habitat patch: normalised %d Operations Alert row(s) off the "
            "removed alert_type options %s" % (len(stale), _DEAD)
        )
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            title="drop_dead_operations_alert_options: normalisation failed",
            message=frappe.get_traceback(),
        )
