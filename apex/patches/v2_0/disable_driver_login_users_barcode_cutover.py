# Copyright (c) 2026, AFMCO and contributors
import frappe

# v2.0.0 — barcode cutover: drivers enter the /driver portal by QR with NO Frappe User.
# This patch DISABLES (never deletes) the login/portal Website-User accounts that used to
# back the driver portal, so a decommissioned driver User can no longer log in once the
# barcode path is live.
#
# HARD SAFETY GUARDS (why this can never lock out a working driver):
#   1. A driver's User is disabled ONLY once that driver already holds an ENABLED
#      Driver-holder Masar Worker Token — i.e. the barcode path is proven live for them.
#      No token => the User is left enabled (still logs in the old way).
#   2. Only ``user_type == "Website User"`` accounts are touched — a System/desk user is
#      never disabled, even if they happen to be linked to a driver.
#   3. Users holding any elevated role (a desk operator who is also a driver) are skipped.
#   4. Administrator / Guest are always skipped.
#
# REVERSIBLE: this only flips ``User.enabled`` 0 (no delete). To roll back, re-enable the
# affected Users (``frappe.db.set_value("User", <user>, "enabled", 1)``).
# IDEMPOTENT: a re-run finds the Users already disabled and is a no-op. No-op on fresh
# installs (no driver tokens yet). post_model_sync: reads the new
# ``Masar Worker Token.driver`` column, which must already be synced.

_ELEVATED_ROLES = {
    "System Manager",
    "Fleet Manager",
    "Fleet Project Manager",
    "Fleet Supervisor",
    "Finance Manager",
    "HR User",
    "HR Manager",
    "Accommodation Manager",
}


def execute():
    # Guard 1: only drivers who can already enter by barcode (a live token) are cut over.
    tokened_drivers = set(
        frappe.get_all(
            "Masar Worker Token",
            filters={"holder_type": "Driver", "enabled": 1},
            pluck="driver",
        )
    )
    if not tokened_drivers:
        # Barcode path not live for any driver yet — do nothing (safe, idempotent).
        return

    disabled = 0
    for driver in tokened_drivers:
        user = frappe.db.get_value("Salis Driver", driver, "driver_user")
        if not user or user in ("Administrator", "Guest"):
            continue
        info = frappe.db.get_value(
            "User", user, ["enabled", "user_type"], as_dict=True
        )
        if not info or not info.enabled:
            continue
        # Guard 2: never disable a System/desk user.
        if info.user_type != "Website User":
            continue
        # Guard 3: never disable a user who also holds an elevated role.
        if set(frappe.get_roles(user)) & _ELEVATED_ROLES:
            continue

        frappe.db.set_value("User", user, "enabled", 0, update_modified=False)
        disabled += 1

    if disabled:
        frappe.db.commit()  # patch context — persist the cutover
