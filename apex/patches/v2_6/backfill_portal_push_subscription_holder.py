import frappe


def execute():
    if not frappe.db.table_exists("Portal Push Subscription"):
        return
    frappe.db.sql(
        """
        update `tabPortal Push Subscription`
           set holder_type = 'Driver', employee = null
         where ifnull(driver, '') != ''
        """
    )
