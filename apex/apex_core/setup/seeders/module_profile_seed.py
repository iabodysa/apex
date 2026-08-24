# Copyright (c) 2026, afmcoltd

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
    kept = set(MODULE_PROFILES[profile_name])
    blocked = set(ADMINISTRATION_MODULES) | {m for m in BACK_OFFICE_MODULES if m not in kept}
    return sorted(blocked)


def seed_module_profiles():
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
