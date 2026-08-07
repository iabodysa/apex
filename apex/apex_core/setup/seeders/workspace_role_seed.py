# Copyright (c) 2026, afmcoltd
import frappe

ALWAYS_PUBLIC = {"Home"}
EXCLUDED_ROLES = {"All", "Guest", "Employee", "Administrator", "Desk User"}


def seed_workspace_roles():
    """Restricts each roleless public Workspace to the roles that can read its linked doctypes.

    Runs from ``after_install`` as well as ``after_migrate``, and at install time a
    Workspace can legitimately reference a Number Card that does not exist yet:
    ``sync.IMPORTABLE_DOCTYPES`` carries no ``number_card`` entry, so an app's cards
    are created by ``sync_dashboards`` during migrate, which has not run yet. Saving
    the record would then fail link validation on rows this function never touched
    and abort the whole install, so links are skipped the way ``import_file`` skips
    them for the same reason.
    """
    for ws_name in frappe.get_all("Workspace", filters={"public": 1}, pluck="name"):
        if ws_name in ALWAYS_PUBLIC:
            continue
        ws = frappe.get_doc("Workspace", ws_name)
        if ws.roles:
            continue
        doctypes = {row.link_to for row in ws.links if row.link_type == "DocType" and row.link_to}
        doctypes |= {row.link_to for row in ws.shortcuts if row.type == "DocType" and row.link_to}
        reports = {row.link_to for row in ws.links if row.link_type == "Report" and row.link_to}
        reports |= {row.link_to for row in ws.shortcuts if row.type == "Report" and row.link_to}
        roles = set()
        for report in reports:
            report_roles = frappe.get_all(
                "Has Role", filters={"parenttype": "Report", "parent": report}, pluck="role"
            )
            if report_roles:
                roles.update(report_roles)
                continue
            ref = frappe.db.get_value("Report", report, "ref_doctype")
            if ref:
                doctypes.add(ref)
        for doctype in doctypes:
            if not frappe.db.exists("DocType", doctype):
                continue
            for perm in frappe.get_all(
                "DocPerm",
                filters={
                    "parent": doctype,
                    "parenttype": "DocType",
                    "permlevel": 0,
                    "read": 1,
                    "if_owner": 0,
                },
                pluck="role",
            ):
                roles.add(perm)
        roles -= EXCLUDED_ROLES
        if not roles:
            continue
        for role in sorted(roles):
            ws.append("roles", {"role": role})
        ws.flags.ignore_permissions = True
        ws.flags.ignore_links = True
        ws.save()
