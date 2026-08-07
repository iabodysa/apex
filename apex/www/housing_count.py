# Copyright (c) 2026, afmcoltd
"""Legacy Housing Inventory count portal served at /housing-count.
Now redirects to the unified /housing SPA.

Pairs with the sibling ``housing-count.html`` marker and CANNOT work without it:
Frappe resolves a www route by template file only, so a template-less controller is
never imported and the route 404s instead of redirecting (see the marker's own
comment, and www/test_www_controller_has_template.py for the guard that holds it).
"""
import frappe

def get_context(context):
    """Redirects the legacy housing-count route to the unified housing portal's count view."""
    frappe.local.flags.redirect_location = "/housing#/count"
    raise frappe.Redirect
