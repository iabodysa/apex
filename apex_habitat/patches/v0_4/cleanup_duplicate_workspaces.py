# Temporary patch — delete after v0.5 release.
# 1. Renames the DB column monthly_rent_sar → rent_amount_sar on tabAccommodation Lease.
# 2. Removes workspace records that were imported under old names or as duplicate
#    browser-saved copies alongside the standard app workspaces.  Re-import from
#    JSON happens automatically on the next bench migrate / after this patch runs.

import frappe

# Canonical workspace names AND labels are identical in the shipped JSON, and both
# include "&" and commas. Keep these two sets in sync with the workspace JSON `name`
# fields under habitat/workspace/ — a mismatch here makes the dedup logic below fail
# to protect the canonical record and risk deleting the wrong copy.
APP_WORKSPACE_LABELS = {
    "Accommodation Lifecycle",
    "Client Audit & Evidence",
    "Custody & Asset Control",
    "Daily & Scheduled Tasks",
    "Lease, Utilities & Cost Control",
    "Maintenance & Remediation",
    "Operations Command Center",
    "Safety & Compliance",
    "Setup",
}

APP_WORKSPACE_NAMES = set(APP_WORKSPACE_LABELS)


def execute():
    _rename_rent_column()
    _cleanup_duplicate_workspaces()
    frappe.clear_cache()


def _rename_rent_column():
    """Rename monthly_rent_sar → rent_amount_sar on existing installations."""
    columns = frappe.db.sql(
        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() "
        "  AND TABLE_NAME = 'tabAccommodation Lease' "
        "  AND COLUMN_NAME = 'monthly_rent_sar'"
    )
    if not columns:
        return  # fresh install or already renamed

    frappe.db.sql(
        "ALTER TABLE `tabAccommodation Lease` "
        "CHANGE `monthly_rent_sar` `rent_amount_sar` "
        "decimal(21,9) NOT NULL DEFAULT 0"
    )
    frappe.logger().info("apex_habitat patch: renamed column monthly_rent_sar → rent_amount_sar")


def _cleanup_duplicate_workspaces():
    # is_standard column may not exist in all Frappe v15 builds — use raw SQL
    all_ws = frappe.db.sql(
        "SELECT name, label FROM `tabWorkspace` ORDER BY name",
        as_dict=True,
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
            existing_name = label_seen[label]
            current_name = ws.name
            # Keep the record whose name matches our canonical app workspace names;
            # delete the other (browser-saved custom copy or old import).
            if current_name in APP_WORKSPACE_NAMES and existing_name not in APP_WORKSPACE_NAMES:
                to_delete.append(existing_name)
                label_seen[label] = current_name
            else:
                to_delete.append(current_name)

    for name in to_delete:
        try:
            frappe.db.delete("Workspace", {"name": name})
            for child in ("Workspace Shortcut", "Workspace Link", "Workspace Chart",
                          "Workspace Number Card", "Workspace Quick List"):
                frappe.db.delete(child, {"parent": name})
            frappe.logger().info(f"apex_habitat patch: deleted duplicate workspace '{name}'")
        except Exception:
            frappe.db.rollback()
            frappe.log_error(
                title="cleanup_duplicate_workspaces: failed to delete workspace",
                message=f"workspace={name}\n{frappe.get_traceback()}",
            )
            continue
