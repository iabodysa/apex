# Copyright (c) 2026, afmcoltd
"""Named Module Profiles that keep the other apps' workspaces off an Apex desk.

``seed_module_profiles`` reaches here only from hooks.py's ``after_install``/
``after_migrate``, so the acting user is always Administrator, who already carries
every permission (frappe/permissions.py:107,273,506).

Apex's nine Workspaces each declare a roles table. The ones frappe, erpnext and hrms
ship declare none, so every desk user sees them: an accommodation supervisor holding
Accommodation Manager, Resident Supervisor, Desk User and Employee opened a sidebar of
31 entries, 26 of them another app's, Users and Build among them.

NEVER BLOCKED: Apex's four modules, so role gating on the Apex Workspaces stays the
only thing deciding which a persona sees; and HR and Payroll, which carry the person's
own leave, attendance, expense-claim and salary-slip records that Apex does not
replace. Hiding a module someone needs hides the product, the worse failure.

Blocked from a fixture by the write-triggers-a-lock property: ``on_update`` queues
``update_all_users`` behind a document lock (frappe/core/doctype/module_profile/
module_profile.py:29-34; frappe/model/document.py:1590), so a fixture's forced
reimport on every migrate risks ``DocumentLockedError`` (frappe/model/document.py:1623)
that this seeder avoids by creating once and calling ``doc.unlock()`` itself.
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
    """
    kept = set(MODULE_PROFILES[profile_name])
    blocked = set(ADMINISTRATION_MODULES) | {m for m in BACK_OFFICE_MODULES if m not in kept}
    return sorted(blocked)


def seed_module_profiles():
    """Create each named Module Profile once, leaving an existing one untouched.

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
            doc.insert()
            doc.unlock()
        except Exception:
            frappe.db.rollback(save_point=savepoint)
            frappe.log_error(f"Module Profile seed failed for {profile_name}")
