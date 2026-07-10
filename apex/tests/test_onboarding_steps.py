# Copyright (c) 2026, AFMCO and contributors
"""Onboarding-step render integrity: every shipped step must open a real target.

Each Onboarding Step record drives the onboarding widget: clicking it opens a
target derived from its `action` (a DocType form, a Report, or a Desk Page). If
that target was renamed or removed the step opens nothing -- a silent break with
no error. This scans the is_standard JSON and checks the DB so CI fails the
moment a step's target (or a Module Onboarding -> step link) stops resolving.

Mirrors test_schema_integrity.py: glob the shipped JSON, build a `bad` list, and
make one assertEqual per concern. Targets are checked by `action`:
  Create Entry / Update Settings -> reference_document must be an existing DocType
  View Report                    -> reference_report must be an existing Report
  Go to Page                     -> path non-empty; a plain Page name (no "/",
                                    no "app/" route, not a workspace) must exist
                                    as a Page record. Route/list paths (e.g.
                                    "List/Safety Task Catalog") only get the
                                    non-empty check, so list routes do not
                                    false-fail while a dangling Page name does.
"""

import glob
import json

import frappe
from frappe.tests.utils import FrappeTestCase

APP = frappe.get_app_path("apex")


def _names_a_page(path):
    # A Go to Page `path` references a Desk Page record only when it is a bare
    # slug -- not a "/" list/view route, not an "app/..." route, not a workspace.
    if not path or "/" in path or path.startswith("app"):
        return False
    return True


class TestOnboardingSteps(FrappeTestCase):
    def test_onboarding_step_targets_resolve(self):
        # Resolve each shipped step's click target by its `action`; a target that
        # does not exist means the step opens nothing.
        bad = []
        seen_actions = set()
        for j in glob.glob(f"{APP}/**/onboarding_step/*/*.json", recursive=True):
            d = json.load(open(j, encoding="utf-8"))
            if d.get("doctype") != "Onboarding Step":
                continue
            name = d.get("name")
            action = d.get("action")
            seen_actions.add(action)
            if action in ("Create Entry", "Update Settings", "Show Form Tour"):
                ref = d.get("reference_document")
                if not ref:
                    bad.append(f"{name} ({action}): empty reference_document")
                elif not frappe.db.exists("DocType", ref):
                    bad.append(f"{name} ({action}): DocType {ref} missing")
            elif action == "View Report":
                rep = d.get("reference_report")
                if not rep:
                    bad.append(f"{name} (View Report): empty reference_report")
                elif not frappe.db.exists("Report", rep):
                    bad.append(f"{name} (View Report): Report {rep} missing")
            elif action == "Go to Page":
                path = d.get("path")
                if not path:
                    bad.append(f"{name} (Go to Page): empty path")
                elif _names_a_page(path) and not frappe.db.exists("Page", path):
                    bad.append(f"{name} (Go to Page): Page {path} missing")
            else:
                bad.append(f"{name}: unhandled action {action!r}")
        self.assertEqual(bad, [], f"onboarding step targets that do not resolve: {bad}")

    def test_module_onboarding_steps_exist(self):
        # Every step referenced by a Module Onboarding must exist as a shipped /
        # DB Onboarding Step, else the onboarding widget renders a dangling row.
        bad = []
        for j in glob.glob(f"{APP}/**/module_onboarding/*/*.json", recursive=True):
            d = json.load(open(j, encoding="utf-8"))
            if d.get("doctype") != "Module Onboarding":
                continue
            name = d.get("name")
            for row in d.get("steps", []):
                step = row.get("step")
                if not step:
                    bad.append(f"{name}: empty step reference")
                elif not frappe.db.exists("Onboarding Step", step):
                    bad.append(f"{name} -> Onboarding Step {step} missing")
        self.assertEqual(bad, [], f"module onboarding step links that do not resolve: {bad}")

    def test_daily_role_tours_visible_to_their_role(self):
        # P-144: each B5 daily-role Module Onboarding must grant its role via
        # allow_roles, else get_allowed_roles() returns only ["System Manager"]
        # and desktop.get_onboarding_doc hides the Getting-Started tour from the
        # very role that needs it. Assert the role is now allowed at runtime.
        expected = {
            "Accommodation Go-Live": "Resident Supervisor",
            "Salis Fuel Setup": "Fleet Supervisor",
            "Safety Readiness": "Safety Officer",
            "Maintenance Daily Flow": "Maintenance Technician",
        }
        bad = []
        for name, role in expected.items():
            doc = frappe.get_doc("Module Onboarding", name)
            roles = doc.get_allowed_roles()
            if role not in roles:
                bad.append(f"{name}: {roles} missing '{role}'")
        self.assertEqual(bad, [], f"daily-role tours not visible to their role: {bad}")

    def test_scan_is_non_vacuous(self):
        # A broken glob must not pass by scanning nothing: assert known records
        # are present on disk so the checks above ran against real data.
        steps = {
            json.load(open(j, encoding="utf-8")).get("name")
            for j in glob.glob(f"{APP}/**/onboarding_step/*/*.json", recursive=True)
        }
        modules = {
            json.load(open(j, encoding="utf-8")).get("name")
            for j in glob.glob(f"{APP}/**/module_onboarding/*/*.json", recursive=True)
        }
        self.assertIn("Close a Rental Settlement", steps, "expected onboarding step JSON not found -- glob is broken")
        self.assertIn("Custody Go-Live", modules, "expected module onboarding JSON not found -- glob is broken")
        self.assertGreaterEqual(len(steps), 20, f"too few onboarding steps scanned ({len(steps)}) -- glob is broken")
