"""Dev patch: clean up stale and custom DB records to force a fresh install.

Deletes stale DocTypes (renamed/deleted), drops their DB tables,
and deletes all workspaces, reports, print formats, and web forms in the Habitat module
to force a clean reload from the codebase files during migrate.
"""
import os
import json
import frappe

def execute():
    frappe.logger().info("apex_habitat patch: starting stale and custom DB cleanup")
    
    # 1. Clean up stale DocTypes
    active_doctypes = []
    doctype_dir = frappe.get_app_path("apex_habitat", "habitat", "doctype")
    if os.path.exists(doctype_dir):
        for folder in os.listdir(doctype_dir):
            folder_path = os.path.join(doctype_dir, folder)
            if os.path.isdir(folder_path):
                json_path = os.path.join(folder_path, f"{folder}.json")
                if os.path.exists(json_path):
                    try:
                        with open(json_path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            if "name" in data:
                                active_doctypes.append(data["name"])
                    except Exception as e:
                        frappe.logger().error(f"Error parsing JSON in {json_path}: {e}")
                        
    db_doctypes = frappe.get_all("DocType", filters={"module": "Habitat"}, pluck="name")
    stale_doctypes = [d for d in db_doctypes if d not in active_doctypes]
    
    for dt in stale_doctypes:
        frappe.logger().info(f"apex_habitat patch: cleaning stale DocType {dt}")
        # Drop table if exists
        table_name = f"tab{dt}"
        frappe.db.sql_ddl(f"DROP TABLE IF EXISTS `{table_name}`")
        
        # Delete metadata
        frappe.db.delete("DocType", {"name": dt})
        frappe.db.delete("Docfield", {"parent": dt})
        frappe.db.delete("DocPerm", {"parent": dt})
        frappe.db.delete("Custom Field", {"dt": dt})
        frappe.db.delete("Property Setter", {"doc_type": dt})
        frappe.db.delete("Workflow", {"document_type": dt})
        frappe.db.delete("Workflow State", {"parent": dt})
        frappe.db.delete("Workflow Action", {"parent": dt})

    # 2. Clean up all Workspaces of Habitat module (forces fresh reload from JSON)
    frappe.logger().info("apex_habitat patch: deleting workspaces to reload clean")
    # Delete child tables of workspaces
    frappe.db.sql("DELETE FROM `tabWorkspace Link` WHERE parent IN (SELECT name FROM `tabWorkspace` WHERE module='Habitat')")
    frappe.db.sql("DELETE FROM `tabWorkspace Shortcut` WHERE parent IN (SELECT name FROM `tabWorkspace` WHERE module='Habitat')")
    frappe.db.sql("DELETE FROM `tabWorkspace Chart` WHERE parent IN (SELECT name FROM `tabWorkspace` WHERE module='Habitat')")
    frappe.db.sql("DELETE FROM `tabWorkspace Number Card` WHERE parent IN (SELECT name FROM `tabWorkspace` WHERE module='Habitat')")
    frappe.db.sql("DELETE FROM `tabWorkspace Quick List` WHERE parent IN (SELECT name FROM `tabWorkspace` WHERE module='Habitat')")
    # Delete workspace documents
    frappe.db.delete("Workspace", {"module": "Habitat"})

    # 3. Clean up all Reports of Habitat module
    frappe.logger().info("apex_habitat patch: deleting reports to reload clean")
    frappe.db.delete("Report", {"module": "Habitat"})

    # 4. Clean up all Print Formats of Habitat module
    frappe.logger().info("apex_habitat patch: deleting print formats to reload clean")
    frappe.db.delete("Print Format", {"module": "Habitat"})

    # 5. Clean up all Web Forms of Habitat module
    frappe.logger().info("apex_habitat patch: deleting web forms to reload clean")
    web_forms = frappe.get_all("Web Form", filters={"module": "Habitat"}, pluck="name")
    if web_forms:
        frappe.db.delete("Web Form Field", {"parent": ["in", web_forms]})
    frappe.db.delete("Web Form", {"module": "Habitat"})
        
    frappe.clear_cache()
    frappe.logger().info("apex_habitat patch: finished stale and custom DB cleanup")
