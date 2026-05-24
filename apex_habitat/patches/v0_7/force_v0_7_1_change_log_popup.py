"""Force the v0.7.1 Frappe change-log popup once for existing users."""

import json

import frappe
from frappe.utils.change_log import get_versions


def execute():
    """Set last-known app versions so Frappe shows Apex Habitat v0.7.1 notes.

    Frappe's official Desk popup reads files from `change_log/` only when the
    user's stored app version is older than the installed app version. Some
    users opened v0.7 before the official change-log file existed, so this
    patch marks Apex Habitat as last seen at v0.7.0 while preserving the
    current version for every other installed app.
    """
    current_versions = get_versions()
    if "apex_habitat" not in current_versions:
        return

    current_versions["apex_habitat"]["version"] = "0.7.0"

    for user in frappe.get_all("User", filters={"enabled": 1}, pluck="name"):
        if user == "Guest":
            continue

        raw_versions = frappe.db.get_value("User", user, "last_known_versions") or "{}"
        try:
            known_versions = json.loads(raw_versions)
        except json.JSONDecodeError:
            known_versions = {}

        for app, app_info in current_versions.items():
            known_versions.setdefault(app, app_info)

        known_versions["apex_habitat"] = current_versions["apex_habitat"]

        frappe.db.set_value(
            "User",
            user,
            "last_known_versions",
            json.dumps(known_versions),
            update_modified=False,
        )
