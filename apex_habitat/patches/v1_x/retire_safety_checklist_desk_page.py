import frappe


def execute():
    """Retire the superseded Safety Checklist desk Page (T-290).

    The /safety Vue portal (1.54.29) replaced the desk Page. Its on-disk standard
    files were removed, but the Page record and its 'Record a Safety Inspection'
    onboarding step persist as DB orphans on existing sites (Frappe never
    auto-deletes removed standard records), and clicking the page 500s in
    Page.load_assets on the now-missing directory. Delete both orphans here so
    every deployed site is cleaned on migrate. Idempotent; no-op on fresh
    installs / re-run.
    """
    for doctype, name in (
        ("Page", "safety-checklist"),
        ("Onboarding Step", "Record a Safety Inspection"),
    ):
        if frappe.db.exists(doctype, name):
            frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
