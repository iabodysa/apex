# Copyright (c) 2026, AFMCO and contributors
"""Named Module Profiles that keep the other apps' workspaces off an Apex desk.

Apex's nine Workspaces each declare a roles table. The ones frappe, erpnext and hrms
ship declare none, so every desk user sees them: an accommodation supervisor holding
Accommodation Manager, Resident Supervisor, Desk User and Employee opened a sidebar of
31 entries, 26 of them another app's, Users and Build among them.

THE MECHANISM IS NATIVE AND ACTS ON THE USER, never on another app's records.
``get_workspace_sidebar_items`` reads the session user's ``get_blocked_modules()``
(``frappe/desk/desktop.py:431``) and filters the Workspace query on
``{"module": ["not in", blocked_modules]}`` (``:439``).
``User.validate_allowed_modules`` copies a linked profile's rows into
``User.block_modules`` on every save (``frappe/core/doctype/user/user.py:217-222``),
and ``ModuleProfile.update_all_users`` pushes a later edit out to everyone holding it
(``frappe/core/doctype/module_profile/module_profile.py:44-62``). This app ships only
the profile; an administrator links it on the User form. Adding a roles row to another
app's Workspace was the alternative and is wrong -- those records re-import from their
own app's JSON on every migrate, so the edit is silently dropped.

NOBODY IS LOCKED OUT BY SHIPPING THIS: nothing here links a profile to any user, so
every existing account keeps the sidebar it had. Two administrator facts, both measured.
Administrator holds every role including Workspace Manager,
and the filter is cleared outright for that role (``frappe/desk/desktop.py:428,
435-436``), so a profile could hide nothing from them. A plain System Manager does NOT
hold it and has no bypass -- linking a profile to one took their sidebar from 40
entries to 19. Never link one to an administration account, and never to Administrator
for a second reason: ``frappe/config/__init__.py:8`` reads Administrator's blocked
modules as the site's GLOBAL block list.

NEVER BLOCKED: Apex's four modules, so role gating on the Apex Workspaces stays the
only thing deciding which a persona sees; and HR and Payroll, which carry the person's
own leave, attendance, expense-claim and salary-slip records that Apex does not
replace. Hiding a module someone needs hides the product, the worse failure.

BLOCKING IS NAVIGATION, NOT PERMISSION. It drops the module's Workspaces from the
sidebar (``frappe/desk/desktop.py:439``), its Desktop Icons (``desktop_icon.py:135``)
and its entry in the Dashboard / Number Card module list
(``frappe/config/__init__.py:5-11``), and writes no DocPerm at all.

CREATE-ONLY, ON PURPOSE. A fixture re-imports and overwrites on every migrate, undoing
an administrator's edit, and Module Profile's ``on_update`` locks the document
(``frappe/model/document.py:1589-1590``) -- the lock that forced this app's Role
fixture out. Writing only when absent keeps a hand edit and still reaches old sites.
"""

import frappe

APEX_MODULES = ("Apex Core", "Habitat", "Logistay", "Salis")

EMPLOYMENT_MODULES = ("HR", "Payroll")

ADMINISTRATION_MODULES = (
    "Automation",
    "Core",
    "ERPNext Integrations",
    "Integrations",
    "Setup",
    "Website",
)

BACK_OFFICE_MODULES = (
    "Accounts",
    "Assets",
    "Buying",
    "CRM",
    "Manufacturing",
    "Projects",
    "Quality Management",
    "Selling",
    "Stock",
    "Support",
)

MODULE_PROFILES = {
    "Apex Operations Desk": (),
    "Apex Procurement Desk": ("Buying", "Stock"),
    "Apex Finance Desk": ("Accounts", "Assets", "Projects"),
}


def blocked_modules_for(profile_name: str) -> list[str]:
    """Return the module names one named profile hides, in stored row order.

    Every profile hides the administration and developer surfaces. Each then keeps
    the back-office modules its persona transacts in: procurement needs Buying and
    Stock, finance and audit need Accounts, Assets and Projects, and operations
    needs none of them.

    ``Block Module.module`` is a Data field, not a Link
    (``frappe/core/doctype/block_module/block_module.json``), so a name that no app
    on this site owns is inert rather than invalid — which is what lets one fixed
    list serve a site with erpnext and one without.
    """
    kept = set(MODULE_PROFILES[profile_name])
    blocked = set(ADMINISTRATION_MODULES) | {m for m in BACK_OFFICE_MODULES if m not in kept}
    return sorted(blocked)


def seed_module_profiles():
    """Create each named Module Profile once, leaving an existing one untouched.

    ``insert`` runs ``on_update``, which calls ``queue_action`` and therefore locks
    the document (``frappe/model/document.py:1589-1590``). The lock is released by
    ``execute_action`` in the worker (``:1722``), which a worker-less migrate never
    reaches, so the lock is dropped here instead -- the same pattern
    ``apex.setup.create_role_profiles`` uses for the identical Role Profile lock.

    One savepoint per profile: a record that fails must not abort the migrate.
    """
    for profile_name in MODULE_PROFILES:
        if frappe.db.exists("Module Profile", profile_name):
            continue
        savepoint = "module_profile_seed"
        frappe.db.savepoint(savepoint)
        try:
            doc = frappe.new_doc("Module Profile")
            doc.module_profile_name = profile_name
            for module in blocked_modules_for(profile_name):
                doc.append("block_modules", {"module": module})
            doc.insert(ignore_permissions=True)  # audit-ok — install/migrate seed, no user session
            doc.unlock()
        except Exception:
            frappe.db.rollback(save_point=savepoint)
            frappe.log_error(f"Module Profile seed failed for {profile_name}")
