# Copyright (c) 2026, AFMCO and contributors
"""Move the app-wide ``enable_gl_posting`` finance gate from Habitat Settings to
Apex Settings.

``enable_gl_posting`` was relocated out of the housing-scoped Habitat Settings
single into the app-wide Apex Settings single (it serves both Habitat and Salis).
On a site that already set the value on Habitat Settings, it still lingers as an
orphan row in ``tabSingles`` (removing a field from a Single's JSON does not delete
its stored value). This patch copies any such value into Apex Settings, then
deletes the orphan row so nothing stale remains.

The companion ``default_payment_method`` was NOT moved onto Apex Settings — it was
retired in favour of the Payment Routing Settings router; its migration + orphan
cleanup are owned by ``retire_default_payment_method``.

ONE-TIME, idempotent, install-safe:
  * reads the OLD value straight from ``tabSingles`` via the query builder — NOT
    ``get_single_value``, which now throws because the field is gone from the
    Habitat Settings meta;
  * only fills Apex Settings when its value is still the factory default / unset,
    so it never clobbers a value an admin set directly on Apex Settings;
  * deletes the Habitat Settings orphan row, so a second run is a pure no-op;
  * a no-op on fresh installs (no orphan rows exist).
PRUNE (remove module + the patches.txt line) once every deployed site has run it.
"""

import frappe

# [#n1agup]
MOVED_FIELDS = {
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
            # [#sfqxge]
            rows = (
                frappe.qb.from_(singles)
                .select(singles.value)
                .where((singles.doctype == "Habitat Settings") & (singles.field == field))
                .run()
            )
            if not rows:
                continue

            old_value = rows[0][0]

            # [#fel8e3]
            current = apex.get(field)
            current_str = "" if current is None else str(current)
            if old_value not in (None, "") and current_str == str(factory_default):
                apex.set(field, old_value)
                changed = True

        if changed:
            apex.save(ignore_permissions=True)  # audit-ok

        # [#9rt94w]
        frappe.qb.from_(singles).delete().where(
            (singles.doctype == "Habitat Settings")
            & (singles.field.isin(list(MOVED_FIELDS)))
        ).run()
        frappe.db.commit()
    except Exception:
        # [#19ji2j]
        frappe.db.rollback()
        frappe.log_error(
            title="move_finance_settings_to_apex_settings failed",
            message=frappe.get_traceback(),
        )
