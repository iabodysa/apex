"""Move the two app-wide finance settings from Habitat Settings to Apex Settings.

``default_payment_method`` and ``enable_gl_posting`` were relocated out of the
housing-scoped Habitat Settings single into the app-wide Apex Settings single
(they serve both Habitat and Salis). On a site that already set either value on
Habitat Settings, that value still lingers as an orphan row in ``tabSingles``
(removing a field from a Single's JSON does not delete its stored value). This
patch copies any such value into Apex Settings, then deletes the orphan rows so
nothing stale remains.

ONE-TIME, idempotent, install-safe:
  * reads the OLD value straight from ``tabSingles`` via the query builder — NOT
    ``get_single_value``, which now throws because the field is gone from the
    Habitat Settings meta;
  * only fills Apex Settings when its value is still the factory default / unset,
    so it never clobbers a value an admin set directly on Apex Settings;
  * deletes the Habitat Settings orphan rows, so a second run is a pure no-op;
  * a no-op on fresh installs (no orphan rows exist).
PRUNE (remove module + the patches.txt line) once every deployed site has run it.
"""

import frappe

# field -> the Apex Settings factory default to treat as "unset / safe to overwrite"
MOVED_FIELDS = {
    "default_payment_method": "Payment Entry",
    "enable_gl_posting": "0",
}


def execute():
    try:
        if not frappe.db.exists("DocType", "Apex Settings"):
            return

        singles = frappe.qb.Table("tabSingles")
        apex = frappe.get_single("Apex Settings")
        changed = False

        for field, factory_default in MOVED_FIELDS.items():
            # Read the lingering value straight from tabSingles. The field is no
            # longer in the Habitat Settings meta, so get_single_value() would
            # throw "Field ... does not exist"; the query builder does not.
            rows = (
                frappe.qb.from_(singles)
                .select(singles.value)
                .where((singles.doctype == "Habitat Settings") & (singles.field == field))
                .run()
            )
            if not rows:
                continue

            old_value = rows[0][0]

            # Only adopt the old value if Apex Settings is still at its factory
            # default (i.e. an admin has not already set it on the new home).
            current = apex.get(field)
            current_str = "" if current is None else str(current)
            if old_value not in (None, "") and current_str == str(factory_default):
                apex.set(field, old_value)
                changed = True

        if changed:
            apex.save(ignore_permissions=True)  # audit-ok

        # Delete the orphan rows so the dropped fields leave no residue and a
        # re-run is a pure no-op.
        frappe.qb.from_(singles).delete().where(
            (singles.doctype == "Habitat Settings")
            & (singles.field.isin(list(MOVED_FIELDS)))
        ).run()
        frappe.db.commit()
    except Exception:
        # A migration patch must NEVER crash migrate — log and continue.
        frappe.db.rollback()
        frappe.log_error(
            title="move_finance_settings_to_apex_settings failed",
            message=frappe.get_traceback(),
        )
