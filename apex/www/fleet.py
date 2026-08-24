# Copyright (c) 2026, Apex contributors

import frappe
from apex.apex_core.utils.portal_bootstrap import guest_redirect, publish_portal_context
from apex.salis.api.fleet_employee import get_context as get_fleet_context


def get_context(context):
    guest_redirect("/fleet")
    frappe.local.lang = "ar"

    fleet_context = get_fleet_context()
    grants = ["fleet.self.read"]
    for key in ("handover", "fuel", "incident", "complaint"):
        if fleet_context.get("capabilities", {}).get(key):
            grants.append(f"fleet.self.{key}")
    return publish_portal_context(
        context,
        entry="fleet-self-service",
        public_path="/fleet",
        initial_route="/",
        capabilities=grants,
        subject=frappe.session.user,
    )
