# Copyright (c) 2026, AFMCO and contributors
"""What the Resident Request Coordinator role can reach on Resident Request, asked
of the framework.

WHY THIS ASKS THE FRAMEWORK RATHER THAN THE FILE. The previous version opened the
DocType JSON and asserted the permissions block contained what the permissions
block contained -- a change detector, not a check of what a user holding the role
can actually do. The behaviour a coordinator meets is decided by
`frappe.has_permission` and `frappe.model.get_permitted_fields`, which read DocPerm
rows, Custom DocPerm rows and User Permissions together -- none of which the JSON
alone can answer for.

So this asks the live question once per role, as that role, and the four
JSON-shape methods become behaviour: triage rights, the confidential field the
permlevel-1 row unlocks, and that the roles which already opened the document
before the Coordinator grant still do.
"""

from __future__ import annotations

import frappe
from frappe.model import get_permitted_fields
from frappe.tests.utils import FrappeTestCase

from apex.tests._helpers import _user, as_user

DOCTYPE = "Resident Request"
ROLE = "Resident Request Coordinator"
COORDINATOR = "resident_request_coordinator_perms@example.com"

# The field the permlevel-1 row unlocks. apex/habitat/doctype/resident_request/resident_request.json.
CONFIDENTIAL_FIELD = "mobile_number"

# Roles that opened the document before the Coordinator grant existed; the grant must not
# have cost them anything.
OTHER_OPENERS = ("System Manager", "Accommodation Manager", "Resident Supervisor")


class TestResidentRequestCoordinatorPermissions(FrappeTestCase):
    """What the Resident Request Coordinator role can and cannot do, asked of the framework."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.coordinator = _user(COORDINATOR, ROLE)

    def test_the_coordinator_can_triage_but_not_destroy(self):
        """Shaped for triage work without record-destroying power: read/write/create,
        no delete, no submit (the DocType is not submittable to begin with)."""
        with as_user(self.coordinator):
            for action in ("read", "write", "create"):
                self.assertTrue(
                    frappe.has_permission(DOCTYPE, action),
                    f"the coordinator must be able to {action}",
                )
            for action in ("delete", "submit"):
                self.assertFalse(
                    frappe.has_permission(DOCTYPE, action),
                    f"the coordinator must NOT be able to {action}",
                )

    def test_the_coordinator_reaches_the_confidential_field(self):
        """The permlevel-1 row exists to unlock exactly this field for the role."""
        with as_user(self.coordinator):
            fields = get_permitted_fields(DOCTYPE, permission_type="write")
        self.assertIn(
            CONFIDENTIAL_FIELD,
            fields,
            "the permlevel-1 row no longer unlocks the confidential field for the coordinator",
        )

    def test_the_existing_openers_keep_both_their_access_and_the_field(self):
        """Adding the Coordinator's rows must not disturb what System Manager,
        Accommodation Manager and Resident Supervisor already had at either
        permlevel."""
        for role in OTHER_OPENERS:
            with self.subTest(role=role):
                user = _user(
                    role.lower().replace(" ", "_") + "_rrc_perms@example.com", role
                )
                with as_user(user):
                    for action in ("read", "write"):
                        self.assertTrue(
                            frappe.has_permission(DOCTYPE, action),
                            f"{role} lost {action} on {DOCTYPE}",
                        )
                    fields = get_permitted_fields(DOCTYPE, permission_type="write")
                self.assertIn(
                    CONFIDENTIAL_FIELD,
                    fields,
                    f"{role} lost its permlevel-1 reach to {CONFIDENTIAL_FIELD}",
                )

    def test_system_manager_still_holds_delete(self):
        """The one privileged bit most at risk of being silently dropped by a
        careless permission-block edit."""
        manager = _user("system_manager_rrc_perms@example.com", "System Manager")
        with as_user(manager):
            self.assertTrue(
                frappe.has_permission(DOCTYPE, "delete"),
                "System Manager delete on Resident Request must remain",
            )
