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
  Go to Page                     -> path non-empty; a plain single-segment path
                                    (no "/", no "app/" route, not a workspace)
                                    must resolve either to a Page record OR to a
                                    bare DocType-slug route -- frappe's router
                                    maps every DocType's lower-cased,
                                    space-to-hyphen slug straight to that
                                    DocType's list view with no Page record
                                    involved (frappe/public/js/frappe/router.js:126,
                                    :580-582). "notification" is one: it is the
                                    slug of the standard "Notification" DocType,
                                    not a custom Page. Route/list paths (e.g.
                                    "List/Safety Task Catalog") only get the
                                    non-empty check, so list routes do not
                                    false-fail while a dangling Page name does.
"""

import glob
import json

import frappe
from frappe.tests.utils import FrappeTestCase

APP = frappe.get_app_path("apex")

# The (role, workspace, onboarding, step, target) contract names the domain
# workspace that embeds each onboarding and gates the role. "Housing" and "Safety"
# both fold into "Housing and Safety" and its "Housing and Safety Go-Live"
# onboarding; "Custody" is "Custody and Costs"; "Salis Fuel Setup" never exists as
# its own record -- the vehicle-handover step ships under "Fleet Go-Live".
DAILY_FLOW_CONTRACT = (
    (
        "Resident Supervisor",
        "Housing and Safety",
        "Housing and Safety Go-Live",
        "Record a Housing Assignment",
        "Housing Assignment",
    ),
    (
        "Resident Supervisor",
        "Custody and Costs",
        "Custody and Costs Go-Live",
        "Issue Custody",
        "Custody Issue",
    ),
    (
        "Fleet Supervisor",
        "Fleet",
        "Fleet Go-Live",
        "Record a Vehicle Handover",
        "Vehicle Handover",
    ),
    (
        "Safety Officer",
        "Housing and Safety",
        "Housing and Safety Go-Live",
        "Record a Safety Round",
        "Safety Round",
    ),
    (
        "Safety Officer",
        "Housing and Safety",
        "Housing and Safety Go-Live",
        "Report a Safety Incident",
        "Safety Incident",
    ),
    (
        "Maintenance Technician",
        "Housing and Safety",
        "Housing and Safety Go-Live",
        "Complete a Maintenance Work Order",
        "Maintenance Work Order",
    ),
)


def _source_records(record_type, folder):
    records = {}
    pattern = f"{APP}/**/{folder}/*/*.json"
    for path in glob.glob(pattern, recursive=True):
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        if data.get("doctype") == record_type:
            records[data["name"]] = data
    return records


def _names_a_page(path):
    if not path or "/" in path or path.startswith("app"):
        return False
    return True


class TestOnboardingSteps(FrappeTestCase):
    def _make_maintenance_technician(self, *, with_building_permission):
        suffix = frappe.generate_hash(length=12).lower()
        email = f"onboarding-technician-{suffix}@example.com"
        user = frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": "Onboarding Technician",
                "enabled": 1,
                "roles": [{"role": "Maintenance Technician"}],
            }
        ).insert(ignore_permissions=True)
        company = frappe.db.get_value("Company", {}, "name")
        employee = frappe.get_doc(
            {
                "doctype": "Employee",
                "first_name": "Onboarding Technician",
                "company": company,
                "status": "Active",
                "gender": "Male",
                "date_of_birth": "1990-01-01",
                "date_of_joining": "2026-01-01",
                "user_id": user.name,
            }
        ).insert(ignore_permissions=True)
        building = frappe.get_doc(
            {
                "doctype": "Building",
                "building_name": f"ONBOARDING-{suffix}",
                "total_capacity": 4,
            }
        ).insert(ignore_permissions=True, ignore_links=True)
        if with_building_permission:
            frappe.get_doc(
                {
                    "doctype": "User Permission",
                    "user": user.name,
                    "allow": "Building",
                    "for_value": building.name,
                }
            ).insert(ignore_permissions=True)
        return user, employee, building

    def test_onboarding_step_targets_resolve(self):
        bad = []
        seen_actions = set()
        # frappe.router.js:126 registers every DocType's slug() as a bare route to
        # its list view, independent of the Page doctype -- a single-segment path
        # can legitimately name one of those instead of a Page.
        doctype_slugs = {
            doctype.lower().replace(" ", "-") for doctype in frappe.get_all("DocType", pluck="name")
        }
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
                elif (
                    _names_a_page(path)
                    and path not in doctype_slugs
                    and not frappe.db.exists("Page", path)
                ):
                    bad.append(f"{name} (Go to Page): Page {path} missing")
            else:
                bad.append(f"{name}: unhandled action {action!r}")
        self.assertEqual(bad, [], f"onboarding step targets that do not resolve: {bad}")

    def test_module_onboarding_steps_exist(self):
        bad = []
        source_steps = _source_records("Onboarding Step", "onboarding_step")
        for j in glob.glob(f"{APP}/**/module_onboarding/*/*.json", recursive=True):
            d = json.load(open(j, encoding="utf-8"))
            if d.get("doctype") != "Module Onboarding":
                continue
            name = d.get("name")
            for row in d.get("steps", []):
                step = row.get("step")
                if not step:
                    bad.append(f"{name}: empty step reference")
                elif step not in source_steps and not frappe.db.exists("Onboarding Step", step):
                    bad.append(f"{name} -> Onboarding Step {step} missing")
        self.assertEqual(bad, [], f"module onboarding step links that do not resolve: {bad}")

    def test_daily_role_tours_visible_to_their_role(self):
        # A list, not a dict: the Safety Officer and Maintenance Technician go-lives
        # collapse onto the same "Housing and Safety Go-Live" record as the
        # Resident Supervisor one, so one name carries more than one role check.
        expected = [
            ("Housing and Safety Go-Live", "Resident Supervisor"),
            ("Fleet Go-Live", "Fleet Supervisor"),
            ("Housing and Safety Go-Live", "Safety Officer"),
            ("Housing and Safety Go-Live", "Maintenance Technician"),
        ]
        bad = []
        for name, role in expected:
            doc = frappe.get_doc("Module Onboarding", name)
            roles = doc.get_allowed_roles()
            if role not in roles:
                bad.append(f"{name}: {roles} missing '{role}'")
        self.assertEqual(bad, [], f"daily-role tours not visible to their role: {bad}")

    def test_six_daily_form_tours_are_reachable_by_role(self):
        modules = _source_records("Module Onboarding", "module_onboarding")
        steps = _source_records("Onboarding Step", "onboarding_step")
        tours = _source_records("Form Tour", "form_tour")
        workspaces = _source_records("Workspace", "workspace")
        bad = []

        for role, workspace_name, module_name, step_name, target in DAILY_FLOW_CONTRACT:
            module_data = modules.get(module_name)
            step_data = steps.get(step_name)
            tour_data = tours.get(target)
            workspace_data = workspaces.get(workspace_name)
            if not workspace_data:
                bad.append(f"{workspace_name}: Workspace source missing")
            else:
                workspace_roles = {row.get("role") for row in workspace_data.get("roles", [])}
                if role not in workspace_roles:
                    bad.append(f"{workspace_name}: role {role} cannot open workspace")
                content = json.loads(workspace_data.get("content") or "[]")
                onboardings = {
                    block.get("data", {}).get("onboarding_name")
                    for block in content
                    if block.get("type") == "onboarding"
                }
                if module_name not in onboardings:
                    bad.append(f"{workspace_name}: onboarding {module_name} is not embedded")
            if not module_data:
                bad.append(f"{module_name}: Module Onboarding source missing")
                continue
            allowed_roles = frappe.get_doc(module_data).get_allowed_roles()
            if role not in allowed_roles:
                bad.append(f"{module_name}: role {role} cannot open onboarding")
            linked_steps = {row.get("step") for row in module_data.get("steps", [])}
            if step_name not in linked_steps:
                bad.append(f"{module_name}: step {step_name} not linked")
            if not step_data:
                bad.append(f"{step_name}: Onboarding Step source missing")
                continue
            if step_data.get("reference_document") != target:
                bad.append(f"{step_name}: expected target {target}")
            if target == "Maintenance Work Order":
                if step_data.get("action") != "Go to Page":
                    bad.append(f"{step_name}: technician must open the safe List route")
                if step_data.get("path") != "List/Maintenance Work Order/List":
                    bad.append(f"{step_name}: unsafe work-order route {step_data.get('path')}")
                tour_data = tours.get("Maintenance Work Order Queue")
            else:
                if step_data.get("action") not in {"Create Entry", "Show Form Tour"}:
                    bad.append(f"{step_name}: unsupported form action {step_data.get('action')}")
                if step_data.get("show_form_tour") != 1 or step_data.get("form_tour") != target:
                    bad.append(f"{step_name}: Form Tour {target} not enabled")
            if not tour_data:
                bad.append(f"{target}: Form Tour source missing")
                continue
            if tour_data.get("reference_doctype") != target:
                bad.append(f"{target}: tour opens {tour_data.get('reference_doctype')}")
            if not frappe.db.exists("DocType", target):
                bad.append(f"{target}: runtime DocType missing")
                continue
            meta = frappe.get_meta(target)
            role_can_read = any(row.role == role and row.read for row in meta.permissions)
            if not role_can_read:
                bad.append(f"{target}: role {role} cannot open the guided target")
            if frappe.new_doc(target).doctype != target:
                bad.append(f"{target}: runtime form cannot be instantiated")
            if target == "Maintenance Work Order":
                continue
            for tour_step in tour_data.get("steps", []):
                step_meta = meta
                if tour_step.get("is_table_field"):
                    step_meta = frappe.get_meta(tour_step.get("child_doctype"))
                if not step_meta.has_field(tour_step.get("fieldname")):
                    bad.append(f"{target}: tour field {tour_step.get('fieldname')} missing")

        self.assertEqual(bad, [], f"daily Form Tours are not reachable: {bad}")

    def test_non_submit_daily_roles_finish_with_draft_handoff(self):
        steps = _source_records("Onboarding Step", "onboarding_step")
        tours = _source_records("Form Tour", "form_tour")
        bad = []

        for role, _workspace_name, _module_name, step_name, target in DAILY_FLOW_CONTRACT:
            meta = frappe.get_meta(target)
            role_can_submit = any(row.role == role and row.submit for row in meta.permissions)
            if role_can_submit:
                continue
            step = steps.get(step_name, {})
            description = step.get("description", "").lower()
            role_can_create = any(row.role == role and row.create for row in meta.permissions)
            if role_can_create:
                if step.get("action") != "Show Form Tour":
                    bad.append(f"{step_name}: must finish after the guided draft, not submit")
                if "draft" not in description or "authorized submitter" not in description:
                    bad.append(f"{step_name}: draft submitter handoff is not explained")
            else:
                tour = tours.get(target, {})
                if step.get("action") != "Go to Page":
                    bad.append(f"{step_name}: must open the safe assigned-work list")
                if tour.get("first_document"):
                    bad.append(f"{step_name}: must never fall back to a new unauthorized record")
                if "assigned" not in description or "authorized creator" not in description:
                    bad.append(f"{step_name}: assigned-record creator handoff is not explained")

        self.assertEqual(bad, [], f"non-submit onboarding boundaries are unclear: {bad}")

    def test_maintenance_queue_tour_is_native_safe_and_direction_neutral(self):
        steps = _source_records("Onboarding Step", "onboarding_step")
        tours = _source_records("Form Tour", "form_tour")
        step = steps["Complete a Maintenance Work Order"]
        tour = tours.get("Maintenance Work Order Queue", {})

        self.assertEqual(step.get("action"), "Go to Page")
        self.assertEqual(step.get("path"), "List/Maintenance Work Order/List")
        self.assertFalse(step.get("show_form_tour"))
        self.assertFalse(step.get("form_tour"))
        self.assertNotIn("new", step.get("path", "").lower())
        self.assertEqual(tour.get("ui_tour"), 1)
        self.assertEqual(tour.get("reference_doctype"), "Maintenance Work Order")
        self.assertEqual(json.loads(tour.get("page_route", "[]")), ["List", "Maintenance Work Order", "List"])
        self.assertEqual(tour.get("view_name"), "List")
        selectors = {row.get("element_selector") for row in tour.get("steps", [])}
        self.assertEqual(selectors, {".page-title", ".filter-button", ".result"})
        for row in tour.get("steps", []):
            self.assertNotIn(row.get("position"), {"Left", "Right"})

    def test_maintenance_technician_queue_shows_an_assigned_in_scope_record(self):
        user, employee, building = self._make_maintenance_technician(
            with_building_permission=True
        )
        work_order = frappe.get_doc(
            {
                "doctype": "Maintenance Work Order",
                "naming_series": "MWO-.YYYY.-.####",
                "maintenance_request": f"ONBOARDING-{frappe.generate_hash(length=12)}",
                "building": building.name,
                "assigned_to": employee.name,
                "status": "Planned",
                "planned_start_date": "2026-07-19",
                "work_description": "Verify the assigned onboarding queue.",
            }
        ).insert(ignore_permissions=True, ignore_links=True)

        try:
            frappe.set_user(user.name)
            rows = frappe.get_list(
                "Maintenance Work Order", fields=["name", "assigned_to", "status"]
            )
            self.assertIn(work_order.name, {row.name for row in rows})
            row = next(row for row in rows if row.name == work_order.name)
            self.assertEqual(row.assigned_to, employee.name)
            self.assertEqual(row.status, "Planned")
            self.assertTrue(frappe.has_permission("Maintenance Work Order", "read", doc=work_order))
            self.assertFalse(frappe.has_permission("Maintenance Work Order", "create"))
        finally:
            frappe.set_user("Administrator")

    def test_maintenance_technician_queue_stays_empty_without_building_scope(self):
        user, _employee, _building = self._make_maintenance_technician(
            with_building_permission=False
        )

        try:
            frappe.set_user(user.name)
            self.assertEqual(frappe.get_list("Maintenance Work Order", pluck="name"), [])
            self.assertFalse(frappe.has_permission("Maintenance Work Order", "create"))
        finally:
            frappe.set_user("Administrator")

    def test_each_daily_role_has_at_least_two_native_tours(self):
        modules = _source_records("Module Onboarding", "module_onboarding")
        steps = _source_records("Onboarding Step", "onboarding_step")
        tours = _source_records("Form Tour", "form_tour")
        role_modules = {
            "Resident Supervisor": {"Housing and Safety Go-Live", "Custody and Costs Go-Live"},
            "Fleet Supervisor": {"Fleet Go-Live"},
            "Safety Officer": {"Housing and Safety Go-Live"},
            "Maintenance Technician": {"Housing and Safety Go-Live"},
        }
        bad = []

        for role, module_names in role_modules.items():
            reachable = set()
            for module_name in module_names:
                for row in modules[module_name].get("steps", []):
                    step = steps[row.get("step")]
                    if (
                        step.get("action") in {"Create Entry", "Show Form Tour"}
                        and step.get("show_form_tour") == 1
                        and step.get("form_tour") in tours
                    ):
                        reachable.add(step["form_tour"])
                    elif step.get("action") == "Go to Page":
                        route = step.get("path")
                        reachable.update(
                            name
                            for name, tour in tours.items()
                            if tour.get("ui_tour") == 1
                            and json.loads(tour.get("page_route", "[]")) == route.split("/")
                        )
            if len(reachable) < 2:
                bad.append(f"{role}: only {sorted(reachable)}")

        self.assertEqual(bad, [], f"daily roles with fewer than two native tours: {bad}")

    def test_all_form_tours_load_and_targets_resolve(self):
        # A shipped tour that will not load, or a step whose field/selector no longer
        # resolves, silently breaks onboarding -- fail here the moment either regresses.
        tours = _source_records("Form Tour", "form_tour")
        bad = []

        for name, tour in tours.items():
            try:
                frappe.get_doc("Form Tour", name)
            except Exception as exc:
                bad.append(f"{name}: Form Tour does not load at runtime ({exc})")
                continue
            reference_doctype = tour.get("reference_doctype")
            for index, step in enumerate(tour.get("steps", []), start=1):
                fieldname = step.get("fieldname")
                if step.get("is_table_field"):
                    child_doctype = step.get("child_doctype")
                    if not (child_doctype and frappe.get_meta(child_doctype).has_field(fieldname)):
                        bad.append(f"{name} step {index}: table field {child_doctype}.{fieldname} missing")
                elif tour.get("ui_tour") or step.get("element_selector"):
                    if not step.get("element_selector"):
                        bad.append(f"{name} step {index}: empty element_selector")
                elif not frappe.get_meta(reference_doctype).has_field(fieldname):
                    bad.append(f"{name} step {index}: field {reference_doctype}.{fieldname} missing")

        self.assertEqual(bad, [], f"form tours that do not load or resolve their targets: {bad}")

    def test_daily_role_tour_popovers_are_safe_in_ltr_and_rtl(self):
        tours = _source_records("Form Tour", "form_tour")
        bad = []

        for name in tours:
            for index, row in enumerate(tours[name].get("steps", []), start=1):
                position = (row.get("position") or "Bottom").lower()
                if "left" in position or "right" in position:
                    bad.append(f"{name} step {index}: directional position {position}")

        self.assertEqual(bad, [], f"shipped tour popovers can clip in RTL/LTR: {bad}")

    def test_guided_check_in_and_custody_issue_can_save_complete_drafts(self):
        tours = _source_records("Form Tour", "form_tour")
        required_tours = ("Housing Assignment", "Custody Issue")
        bad = []

        for name in required_tours:
            tour = tours[name]
            if tour.get("save_on_complete") != 1:
                bad.append(f"{name}: tour does not save on completion")
            covered = {row.get("fieldname") for row in tour.get("steps", [])}
            meta = frappe.get_meta(tour["reference_doctype"])
            uncovered = {
                field.fieldname
                for field in meta.fields
                if field.reqd and field.fieldtype not in {"Section Break", "Column Break", "Tab Break"}
                and not field.default and field.fieldname not in covered
            }
            if uncovered:
                bad.append(f"{name}: mandatory fields not guided {sorted(uncovered)}")

        self.assertEqual(bad, [], f"guided draft completion is incomplete: {bad}")

    def test_housing_assignment_tour_covers_required_project(self):
        tours = _source_records("Form Tour", "form_tour")
        fieldnames = {step.get("fieldname") for step in tours["Housing Assignment"].get("steps", [])}
        project = frappe.get_meta("Housing Assignment").get_field("project")

        self.assertTrue(project.reqd, "Housing Assignment.project must remain mandatory")
        self.assertIn("project", fieldnames, "Housing Assignment tour must guide the mandatory Project field")

    def test_scan_is_non_vacuous(self):
        steps = {
            json.load(open(j, encoding="utf-8")).get("name")
            for j in glob.glob(f"{APP}/**/onboarding_step/*/*.json", recursive=True)
        }
        modules = {
            json.load(open(j, encoding="utf-8")).get("name")
            for j in glob.glob(f"{APP}/**/module_onboarding/*/*.json", recursive=True)
        }
        self.assertIn("Close a Rental Settlement", steps, "expected onboarding step JSON not found -- glob is broken")
        self.assertIn(
            "Custody and Costs Go-Live", modules, "expected module onboarding JSON not found -- glob is broken"
        )
        self.assertGreaterEqual(len(steps), 20, f"too few onboarding steps scanned ({len(steps)}) -- glob is broken")
