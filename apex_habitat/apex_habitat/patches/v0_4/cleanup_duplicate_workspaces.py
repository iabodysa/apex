# Temporary patch — delete after v0.5 release.
# Removes workspace records that were imported under old names or as duplicate
# browser-saved copies alongside the standard app workspaces.  Re-import from
# JSON happens automatically on the next bench migrate / after this patch runs.

import frappe

APP_WORKSPACE_LABELS = {
    "Accommodation Lifecycle",
    "Client Audit Evidence",
    "Custody & Asset Control",
    "Daily Scheduled Tasks",
    "Lease, Utilities & Cost Control",
    "Maintenance & Remediation",
    "Operations Command Center",
    "Safety & Compliance",
    "Setup",
}

APP_WORKSPACE_NAMES = {
    "Accommodation Lifecycle",
    "Client Audit Evidence",
    "Custody Asset Control",
    "Daily Scheduled Tasks",
    "Lease Utilities Cost Control",
    "Maintenance Remediation",
    "Operations Command Center",
    "Safety Compliance",
    "Setup",
}


def execute():
    # Find all workspace records whose label matches one of ours.
    all_ws = frappe.get_all(
        "Workspace",
        fields=["name", "label", "is_standard"],
        order_by="name",
    )

    to_delete = []
    label_seen = {}

    for ws in all_ws:
        label = (ws.label or "").strip()
        if label not in APP_WORKSPACE_LABELS:
            continue

        if label not in label_seen:
            label_seen[label] = ws.name
        else:
            # Duplicate label — keep the one whose name matches our canonical
            # app workspace name; delete the other.
            existing_name = label_seen[label]
            current_name = ws.name

            if current_name in APP_WORKSPACE_NAMES and existing_name not in APP_WORKSPACE_NAMES:
                to_delete.append(existing_name)
                label_seen[label] = current_name
            else:
                to_delete.append(current_name)

    for name in to_delete:
        frappe.db.delete("Workspace", {"name": name})
        frappe.db.delete("Workspace Shortcut", {"parent": name})
        frappe.db.delete("Workspace Link", {"parent": name})
        frappe.db.delete("Workspace Chart", {"parent": name})
        frappe.db.delete("Workspace Number Card", {"parent": name})
        frappe.db.delete("Workspace Quick List", {"parent": name})
        frappe.logger().info(f"apex_habitat patch: deleted duplicate workspace '{name}'")

    frappe.clear_cache()
