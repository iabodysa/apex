import frappe

# Hide the stock ERPNext / HRMS public workspaces so the desk sidebar foregrounds
# the Apex workspaces (Habitat, Salis, and shared Core/Setup areas) only.
#
# Why a patch and not a core edit: a public Workspace is hidden by setting its
# own `is_hidden` flag (the same flag the "Edit > hide" toggle in Workspace
# Settings writes). We never touch erpnext/frappe source. On migrate, Frappe
# preserves a workspace's existing `is_hidden` value (frappe/modules/import_file.py
# `ignore_values["Workspace"] = ["is_hidden"]`), so re-importing the stock JSON
# fixtures will NOT un-hide these — the setting sticks.
#
# Note for admins: users holding the "Workspace Manager" role (e.g. Administrator)
# still SEE hidden public workspaces in the sidebar by design — see
# frappe/desk/desktop.py get_workspace_sidebar_items(): a public page shows when
# `(has_access or not page.is_hidden)`. The hide therefore takes visible effect
# for standard (non-manager) users; managers keep visibility so they can manage them.
#
# Conservative + reversible: only the explicit non-Apex stock workspaces below are
# touched, only by name, only if they exist, and only if not already hidden.
# To reverse, set `is_hidden = 0` on the same names (or untick in Workspace Settings).

# Clearly non-Apex stock ERPNext / HRMS / Payroll public workspaces. Deliberately
# excludes Apex areas (Habitat/Salis modules) and shared Core/Setup workspaces
# (Home, Users, Build, Welcome Workspace, ERPNext/Integration settings hubs are
# left for the owner to decide separately).
STOCK_WORKSPACES = (
    # Accounts
    "Accounting",
    "Payables",
    "Receivables",
    "Financial Reports",
    # Trade / supply chain
    "Buying",
    "Selling",
    "Stock",
    "Assets",
    # Manufacturing & quality
    "Manufacturing",
    "Quality",
    # Delivery / sales ops
    "CRM",
    "Support",
    "Projects",
    # HR
    "HR",
    "Recruitment",
    "Employee Lifecycle",
    "Performance",
    "Shift & Attendance",
    "Expense Claims",
    "Leaves",
    # Payroll
    "Payroll",
    "Salary Payout",
    "Tax & Benefits",
)


def execute():
    if not frappe.db.exists("DocType", "Workspace"):
        return

    hidden = []
    for name in STOCK_WORKSPACES:
        # Only touch a real, public workspace that is not already hidden.
        ws = frappe.db.get_value(
            "Workspace", name, ["public", "is_hidden"], as_dict=True
        )
        if not ws or not ws.public or ws.is_hidden:
            continue
        # Set the flag directly: avoids the Workspace controller's developer_mode
        # export-to-files side effect, and is exactly the value migrate preserves.
        frappe.db.set_value("Workspace", name, "is_hidden", 1, update_modified=False)
        hidden.append(name)

    if hidden:
        frappe.db.commit()
        frappe.clear_cache()
