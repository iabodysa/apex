import frappe
import os
from frappe.modules.import_file import import_file_by_path

def execute():
    # Force sync the web form from the JSON file to ensure fields are populated
    app_path = frappe.get_app_path("apex_habitat")
    web_form_path = os.path.join(app_path, "habitat", "web_form", "accommodation_resident_request", "accommodation_resident_request.json")
    
    if os.path.exists(web_form_path):
        import_file_by_path(web_form_path, force=True, ignore_version=True)
        frappe.db.commit()
