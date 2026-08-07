# Copyright (c) 2026, AFMCO and contributors
import frappe

ALWAYS_PUBLIC = {"Home"}
EXCLUDED_ROLES = {"All", "Guest", "Employee", "Administrator", "Desk User"}


def seed_workspace_roles():
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
        ws.flags.ignore_permissions = True  # audit-ok — install/migrate seeder restricting stock workspace visibility
        ws.save()
