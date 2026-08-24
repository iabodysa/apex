# Copyright (c) 2026, afmcoltd

import frappe


STEP = "Review Apex Integration Settings"


def execute():
    if frappe.db.exists("Onboarding Step", STEP):
        frappe.delete_doc("Onboarding Step", STEP, ignore_missing=True)
