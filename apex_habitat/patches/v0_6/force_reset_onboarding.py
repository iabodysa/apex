import frappe

def execute():
    """Force reset the onboarding steps so the Wizard appears for the user again."""
    onboarding_name = "Habitat Operations Setup"
    
    # 1. Reset the Module Onboarding to incomplete
    if frappe.db.exists("Module Onboarding", onboarding_name):
        frappe.db.set_value("Module Onboarding", onboarding_name, "is_complete", 0)
        
    # 2. Delete tracking records (so Frappe thinks the user hasn't seen/dismissed them)
    # Frappe tracks the completion of each step per user in 'Onboarding Step Status' or similar.
    # In some Frappe versions, it's just 'User Onboarding Status' or 'Onboarding Status'.
    # We'll clear known caching tracking tables to ensure a fresh start.
    if frappe.db.exists("DocType", "User Onboarding Status"):
        frappe.db.sql("DELETE FROM `tabUser Onboarding Status` WHERE onboarding = %s", onboarding_name)
        
    if frappe.db.exists("DocType", "Onboarding Step Status"):
        # delete any status linked to our steps
        frappe.db.sql("""
            DELETE FROM `tabOnboarding Step Status`
            WHERE onboarding_step IN (
                SELECT name FROM `tabOnboarding Step` WHERE name LIKE '%%Habitat%%' OR name IN (
                    'Configure Habitat Settings',
                    'Create an Accommodation Site',
                    'Create an Accommodation Building',
                    'Add Rooms and Beds',
                    'Review the Safety Task Catalog',
                    'Record an Accommodation Assignment'
                )
            )
        """)

    # 3. Clear cache
    frappe.clear_cache()
