"""Set role restrictions on all Habitat workspaces."""

import frappe


def execute():
    workspace_roles = {
        "Setup": ["Accommodation Manager"],
        "Accommodation Lifecycle": ["Accommodation Manager", "Resident Supervisor"],
        "Operations Command Center": ["Accommodation Manager", "Resident Supervisor"],
        "Lease, Utilities & Cost Control": ["Finance Manager", "Accommodation Manager"],
        "Maintenance & Remediation": ["Accommodation Manager", "Resident Supervisor"],
        "Safety & Compliance": ["Accommodation Manager", "Resident Supervisor"],
        "Custody & Asset Control": ["Accommodation Manager", "Resident Supervisor"],
        "Daily & Scheduled Tasks": ["Accommodation Manager", "Resident Supervisor"],
        "Client Audit & Evidence": ["Internal Auditor", "Accommodation Manager"],
    }

    for workspace_name, roles in workspace_roles.items():
        if not frappe.db.exists("Workspace", workspace_name):
            continue
        ws = frappe.get_doc("Workspace", workspace_name)
        ws.roles = []
        for role in roles:
            ws.append("roles", {"role": role})
        ws.save(ignore_permissions=True)

    frappe.db.commit()
