# Copyright (c) 2026, AFMCO and contributors
"""Domain-only navigation: the per-role landing pages are retired.

The owner-approved consolidation removed the four per-role landing Workspaces
(Resident Supervisor / Fleet Supervisor / Safety Officer / Maintenance Technician)
and folded their unique content into the business-domain workspaces. This proves:

1. the four role workspaces no longer exist (the delete + orphan-row patch worked);
2. every retired role still reaches a domain workspace gated to it;
3. every retired role reaches that workspace THROUGH ITS PARENT CHAIN — a gated child
   whose ancestor the persona cannot see is never drawn in the sidebar;
4. every domain-workspace shortcut / link / number-card / chart target resolves to a
   live record (a dangling migrated link_to or a dropped tile would fail here);
5. each element migrated forward actually landed on its new domain home, including the
   maintenance onboarding entry point.

A migrate-import failure, a re-appearing role page, or a lost entry point all fail here
where a static json.load would not.

Check 3 is the gap two separate sidebar regressions fell through: gating a workspace to a
role proves nothing if an ancestor drops out of that persona's sidebar. The scan lives in
``tests/workspace_reachability.py`` — a non-``test_`` module, because
``tests/test_no_cross_test_imports.py`` forbids importing a sibling ``test_*`` module —
so this suite and ``test_workspace_sidebar_reachability.py`` share one implementation
instead of two copies that can drift apart.
"""

import json
import unittest

import frappe

from apex.tests.workspace_reachability import (
    blocking_ancestors,
    workspaces as workspaces_on_disk,
)

REMOVED_ROLE_WORKSPACES = [
    "Resident Supervisor",
    "Fleet Supervisor",
    "Safety Officer",
    "Maintenance Technician",
]

# each retired role -> the domain workspace(s) that now carry its navigation
ROLE_DOMAIN_WORKSPACES = {
    "Fleet Supervisor": ["Fleet", "Salis"],
    "Resident Supervisor": ["Housing and Safety", "Custody and Costs"],
    "Safety Officer": ["Housing and Safety"],
    "Maintenance Technician": ["Housing and Safety"],
}

# domain workspaces whose every navigation target must resolve
DOMAIN_WORKSPACES = ["Fleet", "Salis", "Housing and Safety", "Custody and Costs"]


class TestDomainOnlyWorkspaces(unittest.TestCase):

    def test_role_persona_workspaces_removed(self):
        for ws in REMOVED_ROLE_WORKSPACES:
            self.assertFalse(
                frappe.db.exists("Workspace", ws),
                f"retired role workspace '{ws}' still present",
            )

    def test_each_role_reaches_a_gated_domain_workspace(self):
        for role, workspaces in ROLE_DOMAIN_WORKSPACES.items():
            with self.subTest(role=role):
                reached = False
                for ws in workspaces:
                    if not frappe.db.exists("Workspace", ws):
                        continue
                    doc = frappe.get_doc("Workspace", ws)
                    if role in [r.role for r in doc.roles]:
                        reached = True
                        break
                self.assertTrue(
                    reached,
                    f"role '{role}' reaches no domain workspace gated to it",
                )

    def test_each_role_reaches_a_domain_workspace_through_its_parent_chain(self):
        # gating a child to a role is useless if an ancestor hides it
        pages = workspaces_on_disk()
        for role, titles in ROLE_DOMAIN_WORKSPACES.items():
            with self.subTest(role=role):
                reached, blocked = [], []
                for title in titles:
                    page = pages.get(title)
                    if not page or role not in page["roles"]:
                        continue
                    chain = blocking_ancestors(pages, title, role)
                    if chain is None:
                        blocked.append(f"{title} (broken or cyclic parent chain)")
                    elif chain:
                        blocked.append(f"{title} (hidden behind ancestor {chain[0]!r})")
                    else:
                        reached.append(title)
                self.assertTrue(
                    reached,
                    f"retired persona '{role}' is ORPHANED: no domain workspace is reachable "
                    f"through its parent chain — {'; '.join(blocked) or 'no candidate is gated to it'}",
                )

    def test_domain_workspace_targets_resolve(self):
        for ws in DOMAIN_WORKSPACES:
            with self.subTest(workspace=ws):
                self.assertTrue(
                    frappe.db.exists("Workspace", ws), f"domain workspace '{ws}' missing"
                )
                doc = frappe.get_doc("Workspace", ws)
                self.assertGreater(len(json.loads(doc.content)), 0)

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

    def test_migrated_elements_landed_on_domain_home(self):
        # Fleet Supervisor's only otherwise-unreachable board -> fleet
        fleet = frappe.get_doc("Workspace", "Fleet")
        self.assertIn("Fuel Approval Console", [s.label for s in fleet.shortcuts])
        self.assertTrue(frappe.db.exists("Page", "fuel-approval-console"))

        # Resident Supervisor uniques -> Housing and Safety
        housing = frappe.get_doc("Workspace", "Housing and Safety")
        hs_cards = [nc.number_card_name for nc in housing.number_cards]
        self.assertIn("Rooms Needing Readiness", hs_cards)
        self.assertIn("Idle Residents", hs_cards)
        self.assertIn(
            "Idle Resident Detection",
            [lk.link_to for lk in housing.links if lk.link_type == "Report"],
        )
        self.assertIn("/housing", [s.url for s in housing.shortcuts if s.type == "URL"])

        # Safety Officer + Maintenance Technician uniques -> Housing and Safety
        safety = frappe.get_doc("Workspace", "Housing and Safety")
        sf_cards = [nc.number_card_name for nc in safety.number_cards]
        for card in (
            "Poor Safety Task Executions",
            "Safety Inspections Recorded",
            "Maintenance Work Orders In Progress",
            "Facility Assets Needing Attention",
        ):
            self.assertIn(card, sf_cards)
        # The facility-asset / subcontractor uniques landed on Custody and Costs, not
        # Housing and Safety -- the fold-in split by subject, not by retired role.
        custody = frappe.get_doc("Workspace", "Custody and Costs")
        custody_links = [lk.link_to for lk in custody.links]
        for dt in (
            "Facility Asset",
            "Facility Asset Movement",
            "Subcontractor Service Order",
            "Subcontractor Service Contract",
        ):
            self.assertIn(dt, custody_links)
        self.assertIn(
            "Operational Depreciation Aging",
            [lk.link_to for lk in custody.links if lk.link_type == "Report"],
        )
        # the maintenance onboarding entry point survived the fold-in
        onboarding = [
            b["data"].get("onboarding_name")
            for b in json.loads(safety.content)
            if b["type"] == "onboarding"
        ]
        self.assertIn("Housing and Safety Go-Live", onboarding)


if __name__ == "__main__":
    unittest.main()
