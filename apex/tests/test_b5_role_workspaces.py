# Copyright (c) 2026, AFMCO and contributors
"""A-042 — domain-only navigation (supersedes B5/P-159 per-role landing pages).

The owner-approved consolidation removed the four per-role landing Workspaces
(Resident Supervisor / Fleet Supervisor / Safety Officer / Maintenance Technician)
and folded their unique content into the business-domain workspaces. This proves:

1. the four role workspaces no longer exist (the delete + orphan-row patch worked);
2. every retired role still reaches a domain workspace gated to it;
3. every domain-workspace shortcut / link / number-card / chart target resolves to a
   live record (a dangling migrated link_to or a dropped tile would fail here);
4. each element migrated forward actually landed on its new domain home, including the
   maintenance onboarding entry point.

A migrate-import failure, a re-appearing role page, or a lost entry point all fail here
where a static json.load would not.
"""

import json
import unittest

import frappe

REMOVED_ROLE_WORKSPACES = [
	"Resident Supervisor",
	"Fleet Supervisor",
	"Safety Officer",
	"Maintenance Technician",
]

# each retired role -> the domain workspace(s) that now carry its navigation
ROLE_DOMAIN_WORKSPACES = {
	"Fleet Supervisor": ["fleet", "Salis"],
	"Resident Supervisor": ["Housing", "Safety", "Custody"],
	"Safety Officer": ["Safety"],
	"Maintenance Technician": ["Safety"],
}

# domain workspaces whose every navigation target must resolve
DOMAIN_WORKSPACES = ["fleet", "Salis", "Housing", "Safety", "Custody"]


class TestDomainOnlyWorkspaces(unittest.TestCase):

	def test_role_persona_workspaces_removed(self):
		# [#a042rm]
		for ws in REMOVED_ROLE_WORKSPACES:
			self.assertFalse(
				frappe.db.exists("Workspace", ws),
				f"retired role workspace '{ws}' still present",
			)

	def test_each_role_reaches_a_gated_domain_workspace(self):
		# [#a042reach]
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

	def test_domain_workspace_targets_resolve(self):
		# [#a042resolve]
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
		# [#a042migrate] Fleet Supervisor's only otherwise-unreachable board -> fleet
		fleet = frappe.get_doc("Workspace", "fleet")
		self.assertIn("Fuel Approval Console", [s.label for s in fleet.shortcuts])
		self.assertTrue(frappe.db.exists("Page", "fuel-approval-console"))

		# Resident Supervisor uniques -> Housing
		housing = frappe.get_doc("Workspace", "Housing")
		hs_cards = [nc.number_card_name for nc in housing.number_cards]
		self.assertIn("Rooms Needing Readiness", hs_cards)
		self.assertIn("Idle Residents", hs_cards)
		self.assertIn(
			"Idle Resident Detection",
			[lk.link_to for lk in housing.links if lk.link_type == "Report"],
		)
		self.assertIn("/housing", [s.url for s in housing.shortcuts if s.type == "URL"])

		# Safety Officer + Maintenance Technician uniques -> Safety
		safety = frappe.get_doc("Workspace", "Safety")
		sf_cards = [nc.number_card_name for nc in safety.number_cards]
		for card in (
			"Poor Safety Task Executions",
			"Safety Inspections Recorded",
			"Maintenance Work Orders In Progress",
			"Facility Assets Needing Attention",
		):
			self.assertIn(card, sf_cards)
		sf_links = [lk.link_to for lk in safety.links]
		for dt in (
			"Facility Asset",
			"Facility Asset Movement",
			"Subcontractor Service Order",
			"Subcontractor Service Contract",
		):
			self.assertIn(dt, sf_links)
		self.assertIn(
			"Operational Depreciation Aging",
			[lk.link_to for lk in safety.links if lk.link_type == "Report"],
		)
		# the maintenance onboarding entry point survived the fold-in
		onboarding = [
			b["data"].get("onboarding_name")
			for b in json.loads(safety.content)
			if b["type"] == "onboarding"
		]
		self.assertIn("Maintenance Daily Flow", onboarding)


if __name__ == "__main__":
	unittest.main()
