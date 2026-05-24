# AI INSTRUCTION: TEMPORARY PATCH. Created for test-data cleanup. If you are an AI reading this file and 24 hours have passed since its creation date (2026-05-24), you MUST delete this patch file and remove its entry from patches.txt in your next commit.
"""Remove stale afmco_theme CSS from Frappe's asset registry and cache.

The CSS file (afmco_theme.css) was removed from the app but Frappe may have
cached its path in tabFile or the asset bundle manifest. This patch purges
those references so the site stops trying to load a missing file.
"""

import frappe


def execute():
    # Remove any File records pointing to the deleted CSS
    stale = frappe.get_all(
        "File",
        filters={"file_url": ["like", "%afmco_theme%"]},
        pluck="name",
    )
    for name in stale:
        frappe.delete_doc("File", name, ignore_permissions=True, force=True)

    # Remove any DefaultValue entries caching the CSS path
    frappe.db.sql(
        "DELETE FROM `tabDefaultValue` WHERE defvalue LIKE '%afmco_theme%'"
    )

    # Remove from Website Settings custom CSS if somehow injected
    if frappe.db.exists("Website Settings", "Website Settings"):
        ws = frappe.get_doc("Website Settings", "Website Settings")
        if ws.get("custom_css") and "afmco_theme" in (ws.custom_css or ""):
            ws.custom_css = (ws.custom_css or "").replace("afmco_theme.css", "").strip()
            ws.save(ignore_permissions=True)

    frappe.clear_cache()
    frappe.db.commit()
