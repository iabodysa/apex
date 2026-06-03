# Copyright (c) 2026, AFMCO and contributors
# For license information, please see license.txt
"""My Work Center (Path A) — shape + the permission-safety property that matters:
a user's worklist shows ONLY their own documents, even for a user who could read
others (the `owner == session user` filter, not a role gate)."""

import frappe

from apex_habitat.tests.test_utils import ApexHabitatTestCase
from apex_habitat.apex_core.my_work_center import (
    get_my_work,
    get_submitted_by_me_count,
    get_approved_last_48h_count,
)


def _h(n=6):
    return frappe.generate_hash(length=n)


class TestMyWorkCenter(ApexHabitatTestCase):
    def test_shape(self):
        w = get_my_work()
        for k in ("awaiting_action", "my_open_submitted", "my_recent_closed", "my_notifications"):
            self.assertIn(k, w)
        self.assertIsInstance(w["my_open_submitted"], list)
        self.assertIsInstance(w["my_recent_closed"], list)
        self.assertIsInstance(w["my_notifications"], list)
        self.assertIn("workflow_actions", w["awaiting_action"])
        self.assertIn("value", get_submitted_by_me_count())
        self.assertIn("value", get_approved_last_48h_count())

    def test_owner_isolation(self):
        """The core permission property: a non-owner who CAN read the DocType still
        must not see another user's submitted document in their worklist."""
        cat = (frappe.get_meta("Accommodation Resident Request")
               .get_field("request_category").options.split("\n")[0].strip())
        doc = frappe.get_doc({
            "doctype": "Accommodation Resident Request",
            "request_category": cat,
            "description": "worklist-test " + _h(),
        }).insert(ignore_permissions=True)  # owner = Administrator (the test user), status default = active

        # The owner sees their own active submitted document.
        mine = {r["name"] for r in get_my_work()["my_open_submitted"]}
        self.assertIn(doc.name, mine, "owner must see their own active submitted document")

        # A different user with System Manager (can read everything) but who did NOT
        # create it must NOT see it — proves the filter is by owner, not by role.
        other_email = "wl_other_" + _h() + "@example.com"
        if not frappe.db.exists("User", other_email):
            frappe.get_doc({
                "doctype": "User", "email": other_email, "first_name": "WL Other",
                "roles": [{"role": "System Manager"}],
            }).insert(ignore_permissions=True)
        frappe.set_user(other_email)
        try:
            theirs = {r["name"] for r in get_my_work()["my_open_submitted"]}
        finally:
            frappe.set_user("Administrator")
        self.assertNotIn(
            doc.name, theirs,
            "a non-owner (even able to read all) must NOT see another user's submitted doc",
        )
