# ONE-TIME module reassignment — safe to PRUNE once every deployed site has run it.
#
# Moves the "Masar Worker Token" DocType out of the per-domain "Salis" module and
# into the shared "Apex Core" module (owner decision). The controller folder was
# physically relocated to apex_habitat/apex_core/doctype/masar_worker_token/ so
# Frappe loads its controller from the path implied by its module; this patch
# updates the persisted `module` value on already-installed sites so their DocType
# record agrees with the shipped JSON.
#
# Module reassignment does NOT rename the backing table (tables are keyed on the
# DocType NAME, tab<Name>), so all stored token rows are preserved and every
# lookup by name ("Masar Worker Token") — e.g. salis/api/masar._resolve_worker —
# keeps working unchanged.
#
# Idempotent: a no-op on a fresh install (where the JSON already imports with the
# correct module) and on any site that has already been migrated.

import frappe

_MODULE = "Apex Core"
_DOCTYPE = "Masar Worker Token"


def execute():
    if not frappe.db.exists("DocType", _DOCTYPE):
        # DocType not present on this site (e.g. partial install) — skip safely.
        return
    current = frappe.db.get_value("DocType", _DOCTYPE, "module")
    if current != _MODULE:
        frappe.db.set_value("DocType", _DOCTYPE, "module", _MODULE, update_modified=False)
    frappe.clear_cache()
