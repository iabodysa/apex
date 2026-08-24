# Copyright (c) 2026, afmcoltd

import frappe


def seed_auto_email_reports_for(reports):
    admin_email = frappe.db.get_value("User", "Administrator", "email") or "admin@example.com"
    for cfg in reports:
        if frappe.db.exists("Auto Email Report", {"report": cfg["report"]}):
            continue
        if not frappe.db.exists("Report", cfg["report"]):
            continue
        report_type = frappe.db.get_value("Report", cfg["report"], "report_type")
        doc = frappe.get_doc({
            "doctype": "Auto Email Report",
            "report": cfg["report"],
            "report_type": report_type,
            "user": "Administrator",
            "enabled": 0,
            "email_to": admin_email,
            "format": "HTML",
            "frequency": cfg["frequency"],
            "data_modified_till": 0,
            "no_of_rows": 100,
        })
        doc.insert()
    frappe.db.commit()
