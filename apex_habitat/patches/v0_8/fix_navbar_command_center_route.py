"""Fix the navbar Help-dropdown link that pointed at the pre-rename workspace route
(/app/operations-command-center) to the new /app/habitat. Idempotent.
"""

import frappe


def execute():
    try:
        if not frappe.db.exists("DocType", "Navbar Settings"):
            return
        settings = frappe.get_single("Navbar Settings")
        changed = False
        for row in settings.help_dropdown:
            if row.route == "/app/operations-command-center":
                row.route = "/app/habitat"
                changed = True
        if changed:
            settings.save(ignore_permissions=True)  # audit-ok
            frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        frappe.log_error(title="fix_navbar_command_center_route failed", message=frappe.get_traceback())
