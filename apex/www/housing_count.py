# Copyright (c) 2026, AFMCO and contributors
"""Legacy Housing Inventory count portal served at /housing-count.
Now redirects to the unified /housing SPA.
"""
import frappe

def get_context(context):
	frappe.local.flags.redirect_location = "/housing#/count"
	raise frappe.Redirect
