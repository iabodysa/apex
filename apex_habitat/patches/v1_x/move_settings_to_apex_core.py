# ONE-TIME module reassignment — safe to PRUNE once every deployed site has run it.
#
# Moves the two shared configuration Singles, "Habitat Settings" and
# "Salis Settings", out of the per-domain modules (Habitat / Salis) and into the
# new shared "Apex Core" module. The controller folders were physically relocated
# to apex_habitat/apex_core/doctype/<dt>/ so Frappe loads each controller from the
# path implied by its module; this patch updates the persisted `module` value on
# already-installed sites so their DocType records agree with the shipped JSON.
#
# Module reassignment does NOT rename the backing table: tables are keyed on the
# DocType NAME (tab<Name>), and Single values live in `tabSingles` keyed by the
# same name. The names are unchanged, so all stored values are preserved and every
# frappe.get_single("Habitat Settings") / "Salis Settings" call keeps working.
#
# Idempotent: a no-op on a fresh install (where the JSON already imports with the
# correct module) and on any site that has already been migrated.

import frappe

_MODULE = "Apex Core"
_DOCTYPES = ("Habitat Settings", "Salis Settings")


def execute():
    _ensure_module_def()

    for doctype in _DOCTYPES:
        if not frappe.db.exists("DocType", doctype):
            # DocType not present on this site (e.g. partial install) — skip safely.
            continue
        current = frappe.db.get_value("DocType", doctype, "module")
        if current != _MODULE:
            frappe.db.set_value("DocType", doctype, "module", _MODULE, update_modified=False)

    frappe.clear_cache()


def _ensure_module_def():
    """Guarantee the 'Apex Core' Module Def exists before re-homing DocTypes.

    On a normal migrate the Module Def is auto-synced from modules.txt, but this
    patch may run before that sync depending on order, so create it defensively.
    """
    if frappe.db.exists("Module Def", _MODULE):
        return
    module_def = frappe.new_doc("Module Def")
    module_def.module_name = _MODULE
    module_def.app_name = "apex_habitat"
    module_def.custom = 0
    module_def.insert(ignore_permissions=True)  # audit-ok: system-managed module setup
