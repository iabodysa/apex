# Copyright (c) 2026, AFMCO and contributors
"""Runtime proof: the four B5 task-first daily role workspaces (P-159).

For each role (Resident Supervisor / Fleet Supervisor / Safety Officer /
Maintenance Technician) this asserts the imported Workspace loads, is public +
role-gated to that role, sorts first via sequence_id, and every Today's-Actions
shortcut / link / number-card / chart target resolves to a live record — a
migrate-import failure, a dropped tile (label != name), or a dangling link_to
would all fail here where a static json.load would not.

Also exercises the default-workspace provisioning patch
(set_role_default_workspace): it stamps a role-holder whose default_workspace is
empty and never clobbers a user's own choice.
"""

import json
import unittest

import frappe

from apex.patches.v2_0.set_role_default_workspace import ROLE_WORKSPACE, execute

# role -> (workspace name, expected sequence_id)
ROLE_WORKSPACES = {
    "Resident Supervisor": ("Resident Supervisor", 1.0),
    "Fleet Supervisor": ("Fleet Supervisor", 1.1),
    "Safety Officer": ("Safety Officer", 1.2),
    "Maintenance Technician": ("Maintenance Technician", 1.3),
}


class TestB5RoleWorkspaces(unittest.TestCase):

    def test_workspaces_load_role_gated_and_resolve(self):
        for role, (ws, seq) in ROLE_WORKSPACES.items():
            with self.subTest(role=role):
                self.assertTrue(
                    frappe.db.exists("Workspace", ws),
                    f"workspace '{ws}' did not import",
                )
                doc = frappe.get_doc("Workspace", ws)
                self.assertEqual(doc.public, 1)
                self.assertEqual(doc.is_hidden, 0)
                self.assertEqual(doc.sequence_id, seq)

                # role-gated: the daily workspace is visible to its role
                roles = [r.role for r in doc.roles]
                self.assertIn(role, roles, f"'{ws}' not gated to '{role}'")

                # content blob parses (Today's-Actions layout intact)
                blocks = json.loads(doc.content)
                self.assertGreater(len(blocks), 0)

                # every shortcut target resolves
                for s in doc.shortcuts:
                    if s.type == "DocType":
                        self.assertTrue(
                            frappe.db.exists("DocType", s.link_to),
                            f"{ws}: shortcut '{s.label}' -> missing DocType '{s.link_to}'",
                        )
                    elif s.type == "Page":
                        self.assertTrue(
                            frappe.db.exists("Page", s.link_to),
                            f"{ws}: shortcut '{s.label}' -> missing Page '{s.link_to}'",
                        )
                    elif s.type == "Report":
                        self.assertTrue(
                            frappe.db.exists("Report", s.link_to),
                            f"{ws}: shortcut '{s.label}' -> missing Report '{s.link_to}'",
                        )

                # every link target resolves
                for link in doc.links:
                    if not link.link_to:
                        continue
                    if link.link_type == "DocType":
                        self.assertTrue(
                            frappe.db.exists("DocType", link.link_to),
                            f"{ws}: link '{link.label}' -> missing DocType '{link.link_to}'",
                        )
                    elif link.link_type == "Report":
                        self.assertTrue(
                            frappe.db.exists("Report", link.link_to),
                            f"{ws}: link '{link.label}' -> missing Report '{link.link_to}'",
                        )
                    elif link.link_type == "Page":
                        self.assertTrue(
                            frappe.db.exists("Page", link.link_to),
                            f"{ws}: link '{link.label}' -> missing Page '{link.link_to}'",
                        )

                # metric tiles resolve (a missing card silently drops at runtime)
                for nc in doc.number_cards:
                    self.assertTrue(
                        frappe.db.exists("Number Card", nc.number_card_name),
                        f"{ws}: missing Number Card '{nc.number_card_name}'",
                    )
                for ch in doc.charts:
                    self.assertTrue(
                        frappe.db.exists("Dashboard Chart", ch.chart_name),
                        f"{ws}: missing Dashboard Chart '{ch.chart_name}'",
                    )

    def test_fleet_fuel_request_shortcut_stats_filter_queryable(self):
        # P-144: the Fleet Supervisor "Fuel Request" shortcut filtered on
        # workflow_state, but the Fuel Request Workflow reuses the `status`
        # field (no workflow_state column) -> the shortcut count raised
        # "Field not permitted in query: workflow_state" on every open. Assert
        # the shipped filter is now {status: Pending} and actually executes.
        doc = frappe.get_doc("Workspace", "Fleet Supervisor")
        shortcut = next(s for s in doc.shortcuts if s.label == "Fuel Request")
        stats = json.loads(shortcut.stats_filter)
        self.assertNotIn("workflow_state", stats, "shortcut still filters on workflow_state")
        self.assertEqual(stats, {"status": "Pending"})
        # the count runs cleanly with the shipped filter (no permitted-field error)
        frappe.db.count("Fuel Request", stats)

    def test_patch_stamps_empty_and_preserves_choice(self):
        role = "Safety Officer"
        ws = ROLE_WORKSPACE[role]

        empty_user = frappe.get_doc(
            {
                "doctype": "User",
                "email": "b5-empty@example.com",
                "first_name": "B5 Empty",
                "roles": [{"role": role}],
            }
        ).insert(ignore_permissions=True)

        chosen_user = frappe.get_doc(
            {
                "doctype": "User",
                "email": "b5-chosen@example.com",
                "first_name": "B5 Chosen",
                "default_workspace": "Fleet Supervisor",
                "roles": [{"role": role}],
            }
        ).insert(ignore_permissions=True)

        execute()

        self.assertEqual(
            frappe.db.get_value("User", empty_user.name, "default_workspace"),
            ws,
            "patch did not stamp the empty role-holder",
        )
        self.assertEqual(
            frappe.db.get_value("User", chosen_user.name, "default_workspace"),
            "Fleet Supervisor",
            "patch clobbered a user's own default_workspace choice",
        )

        frappe.delete_doc("User", empty_user.name, force=True, ignore_permissions=True)
        frappe.delete_doc("User", chosen_user.name, force=True, ignore_permissions=True)


if __name__ == "__main__":
    unittest.main()
