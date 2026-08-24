# Copyright (c) 2026, Apex contributors
import frappe

def get_context(context):
    frappe.local.flags.redirect_location = "/housing#/count"
    raise frappe.Redirect
