"""Fix the "Review the Safety Task Catalog" onboarding step.

It shipped with action="View List", which is not a valid Onboarding Step action
(valid: Watch Video, Create Entry, Show Form Tour, Update Settings, View Report,
Go to Page). Frappe's onboarding widget builds actions[step.action](step); an
unknown action is undefined -> silent TypeError, so the button did nothing.
Switch it to "Go to Page" pointing at the catalog list. Idempotent.
"""

import frappe

STEP = "Review the Safety Task Catalog"


def execute():
    if not frappe.db.exists("Onboarding Step", STEP):
        return
    frappe.db.set_value(
        "Onboarding Step",
        STEP,
        {"action": "Go to Page", "path": "List/Safety Task Catalog"},
    )
