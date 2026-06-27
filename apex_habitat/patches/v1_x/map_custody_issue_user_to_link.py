"""ONE-TIME data map: reconcile Custody Issue.issued_to_user values to valid User
names now that the field is a Link -> User (was a free Data field).

While issued_to_user was Data, the controller mirrored it from Employee.user_id (a
Link to User), so most rows already hold a valid User name. But a Data field could
also hold a raw email, a stale value, or a username that no longer maps to a live
User. A Link field rejects a value that is not a real User docname, so this patch
reconciles each existing value before the Link constraint can bite an edit/save:

- If the value is already a valid User name -> leave it (no write).
- Else if it matches a User by email (User.email) -> remap to that User's name.
- Else -> blank it (cannot resolve; leaving an invalid value would block any later
  save with a LinkValidationError). Data is preserved everywhere it is resolvable;
  only truly orphan values are cleared.

Idempotency / safety guards:
- Only reads rows with a non-empty issued_to_user; valid values are skipped.
- Writes via frappe.db.set_value (update_modified=False) to avoid save/validation
  churn and re-firing notifications on historical rows.
- Safe to re-run (resolved rows become no-ops) and a no-op on fresh installs.

PRUNE from patches.txt once every deployed site has run it (check tabPatch Log).
"""

from __future__ import annotations

import frappe

_DOCTYPE = "Custody Issue"


def execute():
    rows = frappe.get_all(
        _DOCTYPE,
        filters={"issued_to_user": ["is", "set"]},
        fields=["name", "issued_to_user"],
    )
    if not rows:
        return

    valid_users = set(frappe.get_all("User", pluck="name"))
    # Resolve a non-name value to a User name via its email, once per distinct value.
    resolved_cache: dict[str, str | None] = {}
    remapped = 0
    cleared = 0

    for row in rows:
        value = (row.issued_to_user or "").strip()
        if not value or value in valid_users:
            continue

        if value not in resolved_cache:
            resolved_cache[value] = frappe.db.get_value(
                "User", {"email": value}, "name"
            )
        target = resolved_cache[value]

        if target:
            frappe.db.set_value(
                _DOCTYPE, row.name, "issued_to_user", target, update_modified=False
            )
            remapped += 1
        else:
            frappe.db.set_value(
                _DOCTYPE, row.name, "issued_to_user", None, update_modified=False
            )
            cleared += 1

    frappe.logger().info(
        f"map_custody_issue_user_to_link: remapped={remapped}, cleared={cleared}"
    )
